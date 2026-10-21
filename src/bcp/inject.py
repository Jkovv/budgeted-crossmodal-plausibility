"""Inject realistic transcription errors into the cell table, keeping the ground truth separately.

Each mechanism acts on the value as a site would write it (rounded to the field's
decimals) and returns the erroneous value, or None when it does not apply to that value.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

EPOCH = dt.date(1970, 1, 1)


def _written(value: float, dec: int) -> str:
    return f"{abs(value):.{dec}f}"


def transpose_digits(value: float, dec: int, rng: np.random.Generator) -> float | None:
    """Exchange two adjacent, different digits of the written value; the decimal point stays in place."""
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
    """Write the value in the field's common alternative unit. ``alt`` is (factor or "c2f", decimals)
    from config; None means the field has no alternative unit that changes the number."""
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
    """All wrong dates a site could write for a given date, by mechanism (as day numbers)."""
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
    """A wrong date for the cell: mechanism drawn uniformly among those that apply, then a variant."""
    typos = date_typos(day_number)
    if not typos:
        return None
    mech = sorted(typos)[rng.integers(len(typos))]
    options = typos[mech]
    return options[rng.integers(len(options))], mech


def decimal_slip(value: float, dec: int, rng: np.random.Generator) -> float | None:
    """Move the decimal point one place: x10 or /10 with equal probability.

    A value divided by ten keeps one more decimal (98 written as 9.8), one multiplied keeps one fewer.
    """
    up = bool(rng.integers(2))
    new = round(value * 10, max(dec - 1, 0)) if up else round(value / 10, dec + 1)
    return new if new > 0 and new != value else None
