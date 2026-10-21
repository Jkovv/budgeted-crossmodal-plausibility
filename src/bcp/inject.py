"""Inject realistic transcription errors into the cell table, keeping the ground truth separately.

Each mechanism acts on the value as a site would write it (rounded to the field's
decimals) and returns the erroneous value, or None when it does not apply to that value.
"""
from __future__ import annotations

import numpy as np


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


def decimal_slip(value: float, dec: int, rng: np.random.Generator) -> float | None:
    """Move the decimal point one place: x10 or /10 with equal probability.

    A value divided by ten keeps one more decimal (98 written as 9.8), one multiplied keeps one fewer.
    """
    up = bool(rng.integers(2))
    new = round(value * 10, max(dec - 1, 0)) if up else round(value / 10, dec + 1)
    return new if new > 0 and new != value else None
