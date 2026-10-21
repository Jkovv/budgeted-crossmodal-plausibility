"""Transcription error injection.

Each mechanism takes the recorded value and returns the wrong one, or None if it
does not apply.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

EPOCH = dt.date(1970, 1, 1)


def _written(value: float, dec: int) -> str:
    return f"{abs(value):.{dec}f}"


def transpose_digits(value: float, dec: int, rng: np.random.Generator) -> float | None:
    """Swap two adjacent digits that differ. The decimal point stays put."""
    s = _written(value, dec)
    point = s.find(".")
    digits = list(s.replace(".", ""))
    pairs = [i for i in range(len(digits) - 1) if digits[i] != digits[i + 1]]
    if not pairs:
        return None
    i = pairs[rng.integers(len(pairs))]
    digits[i], digits[i + 1] = digits[i + 1], digits[i]
    out = "".join(digits) if point < 0 else "".join(digits[:point]) + "." + "".join(digits[point:])
    new = float(out)
    return new if new > 0 and new != value else None


def unit_error(value: float, alt) -> float | None:
    """Value written in the alternative unit from config."""
    if alt is None:
        return None
    factor, dec = alt
    new = round(value * 9 / 5 + 32 if factor == "c2f" else value * factor, dec)
    return new if new > 0 and new != value else None


def _date(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def date_typos(day_number: int) -> dict[str, list[int]]:
    """Possible wrong dates per mechanism, as day numbers."""
    d = EPOCH + dt.timedelta(days=int(day_number))
    out: dict[str, list[dt.date]] = {}
    if d.day <= 12 and d.day != d.month:
        out["day_month_exchanged"] = [_date(d.year, d.day, d.month)]
    dd = f"{d.day:02d}"
    if dd[0] != dd[1]:
        out["day_digits_exchanged"] = [_date(d.year, d.month, int(dd[::-1]))]
    out["month_off_by_one"] = [_date(d.year, d.month + s, d.day) if 1 <= d.month + s <= 12 else None for s in (-1, 1)]
    out["year_off_by_one"] = [_date(d.year + s, d.month, d.day) for s in (-1, 1)]
    clean = {k: [(x - EPOCH).days for x in v if x is not None and x != d] for k, v in out.items()}
    return {k: v for k, v in clean.items() if v}


def wrong_date(day_number: int, rng: np.random.Generator) -> tuple[int, str] | None:
    """Pick a mechanism that applies, then one of its dates."""
    typos = date_typos(day_number)
    if not typos:
        return None
    mech = sorted(typos)[rng.integers(len(typos))]
    options = typos[mech]
    return options[rng.integers(len(options))], mech


def decimal_slip(value: float, dec: int, rng: np.random.Generator) -> float | None:
    """x10 or /10. Dividing keeps one more decimal (98 -> 9.8)."""
    up = bool(rng.integers(2))
    new = round(value * 10, max(dec - 1, 0)) if up else round(value / 10, dec + 1)
    return new if new > 0 and new != value else None
