"""Download the MIMIC-IV Clinical Database Demo v2.2 tables this project uses.

    python data/download_mimic_demo.py            # into data/raw/ (or $BCP_DATA_DIR/raw/)

Files already present with the right SHA-256 are skipped. The checksums are the
ones PhysioNet publishes in SHA256SUMS.txt for version 2.2. The demo is open
access under the Open Data Commons Open Database License v1.0 (ODbL); see
data/README.md. Nothing downloaded here is ever committed.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = "https://physionet.org/files/mimic-iv-demo/2.2/"

# path relative to BASE_URL -> SHA-256 published by PhysioNet (SHA256SUMS.txt, v2.2)
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
EXTRA = ["LICENSE.txt", "SHA256SUMS.txt"]   # kept next to the data for reference, not checksummed


def raw_dir() -> Path:
    root = Path(os.environ.get("BCP_DATA_DIR", Path(__file__).resolve().parent))
    return root / "raw"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(rel: str, dest: Path, retries: int = 5) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(BASE_URL + rel, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            tmp.replace(dest)
            return
        except OSError as e:          # PhysioNet occasionally drops slow connections
            print(f"  {rel}: attempt {attempt} failed ({e})", file=sys.stderr)
            time.sleep(5 * attempt)
    raise RuntimeError(f"could not download {rel}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args()
    out = raw_dir()
    ok = True
    for rel, expected in FILES.items():
        dest = out / rel
        if dest.exists() and sha256(dest) == expected:
            print(f"ok       {rel}")
            continue
        print(f"download {rel}")
        fetch(rel, dest)
        if sha256(dest) != expected:
            print(f"CHECKSUM MISMATCH {rel}", file=sys.stderr)
            ok = False
    for rel in EXTRA:
        if not (out / rel).exists():
            fetch(rel, out / rel)
    print(f"raw data in {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
