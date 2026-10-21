"""Download the MIMIC-IV demo v2.2 tables used here.

    python data/download_mimic_demo.py      # into data/raw/ (or $BCP_DATA_DIR/raw/)

Skips files that are already there with the right checksum. Checksums are from
PhysioNet's SHA256SUMS.txt for v2.2. The demo is open data under ODbL 1.0, see
data/README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://physionet.org/files/mimic-iv-demo/2.2/"

# sha256 from physionet's SHA256SUMS.txt
FILES = {
    "hosp/admissions.csv.gz": "910b9f160ffdf1e08ea673585393f347c773ccc87d66875c627584a903ae8493",
    "hosp/d_labitems.csv.gz": "72ea5f020469fd24543bd98ab3bd0a4f645a5a4b7802d9d52af20d736f9d76db",
    "hosp/diagnoses_icd.csv.gz": "958565670c0b3903c0c12825366dc2bae8561d2d55f16feac0c949dd630ed3e4",
    "hosp/labevents.csv.gz": "d51a4cf1ea63245abe7d544b0d50a928e9ee2ec5eb9a5ce85500aed0bd6c6dfc",
    "hosp/omr.csv.gz": "6d7c69dbb2c79b9d1de7d1e68f3424ad248821d7c074dc6537d7290774af39b9",
    "hosp/patients.csv.gz": "59dcc6cd8450ddf03ad32cc7d76e41caa4c9633541715987f590c74835cf6fae",
    "hosp/prescriptions.csv.gz": "33c392ba5b9299b08eca0a61911ba106f0aebdba26ed31b856bb9ffd49fe3654",
    "icu/chartevents.csv.gz": "90f096ad3db847ed1aaec073f8d86053c51fea7b616d3b046410e030f083d560",
    "icu/d_items.csv.gz": "1690467a822345226a041c1149237c418aa60098c6b699fb4cef64d73588a01f",
    "icu/icustays.csv.gz": "e05e81aa52a3022e522b6832a898101a69b84e64c17bb344d819e458d5bc21b3",
}
EXTRA = ["LICENSE.txt", "SHA256SUMS.txt"]   # not checksummed


def raw_dir() -> Path:
    root = Path(os.environ.get("BCP_DATA_DIR", Path(__file__).resolve().parent))
    return root / "raw"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(rel: str, dest: Path, expected: str | None = None, retries: int = 8) -> None:
    """Download into dest. A dropped or timed-out connection resumes where it stopped; a
    file with the wrong checksum is fetched again from the start."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.unlink(missing_ok=True)
    for attempt in range(1, retries + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        req = urllib.request.Request(BASE_URL + rel, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                length, got = int(r.headers.get("Content-Length", -1)), 0
                with open(tmp, "ab" if r.status == 206 else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                        got += len(chunk)
                if got < length:        # read(n) returns short on a closed connection, no exception
                    raise ConnectionError(f"connection closed after {got} of {length} bytes")
        except urllib.error.HTTPError as e:
            if e.code != 416:           # 416: nothing left to resume, check what we have
                print(f"  {rel}: attempt {attempt} failed ({e})", file=sys.stderr)
                time.sleep(5 * attempt)
                continue
        except OSError as e:            # physionet drops connections now and then
            got = tmp.stat().st_size if tmp.exists() else 0
            print(f"  {rel}: attempt {attempt} failed ({e}), {got} bytes so far", file=sys.stderr)
            time.sleep(5 * attempt)
            continue
        if expected is None or sha256(tmp) == expected:
            tmp.replace(dest)
            return
        print(f"  {rel}: attempt {attempt} has the wrong checksum, starting again", file=sys.stderr)
        tmp.unlink()
        time.sleep(5 * attempt)
    raise RuntimeError(f"could not download {rel}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args()
    out = raw_dir()
    for rel, expected in FILES.items():
        dest = out / rel
        if dest.exists() and sha256(dest) == expected:
            print(f"ok       {rel}")
            continue
        print(f"download {rel}", flush=True)
        fetch(rel, dest, expected)
    for rel in EXTRA:
        if not (out / rel).exists():
            fetch(rel, out / rel)
    print(f"raw data in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
