import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("download", Path(__file__).parents[1] / "data" / "download_mimic_demo.py")
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)

FULL = bytes(range(256)) * 40
SHA = hashlib.sha256(FULL).hexdigest()


class FakeResponse:
    def __init__(self, status, body, length):
        self.status, self.headers, self._body = status, {"Content-Length": str(length)}, body

    def read(self, n):
        out, self._body = self._body[:n], self._body[n:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def serve(monkeypatch, responses):
    """Hand out the responses in turn and record the Range header of each request."""
    ranges = []

    def urlopen(req, timeout):
        ranges.append(req.get_header("Range"))
        return responses[len(ranges) - 1](ranges[-1])

    monkeypatch.setattr(D.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    return ranges


def test_short_read_resumes_from_where_it_stopped(monkeypatch, tmp_path):
    cut = 3000
    ranges = serve(monkeypatch, [
        lambda rng: FakeResponse(200, FULL[:cut], len(FULL)),       # connection closes early
        lambda rng: FakeResponse(206, FULL[cut:], len(FULL) - cut),
    ])
    dest = tmp_path / "x.csv.gz"
    D.fetch("x.csv.gz", dest, SHA)
    assert dest.read_bytes() == FULL
    assert ranges == [None, f"bytes={cut}-"]
    assert not dest.with_suffix(".gz.part").exists()


def test_wrong_checksum_starts_again(monkeypatch, tmp_path):
    bad = b"x" + FULL[1:]
    ranges = serve(monkeypatch, [
        lambda rng: FakeResponse(200, bad, len(bad)),
        lambda rng: FakeResponse(200, FULL, len(FULL)),
    ])
    dest = tmp_path / "x.csv.gz"
    D.fetch("x.csv.gz", dest, SHA)
    assert dest.read_bytes() == FULL
    assert ranges == [None, None]


def test_gives_up_after_the_last_attempt(monkeypatch, tmp_path):
    bad = b"x" + FULL[1:]
    serve(monkeypatch, [lambda rng: FakeResponse(200, bad, len(bad))] * 3)
    dest = tmp_path / "x.csv.gz"
    with pytest.raises(RuntimeError):
        D.fetch("x.csv.gz", dest, SHA, retries=3)
    assert not dest.exists()
