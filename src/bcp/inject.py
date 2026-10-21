"""Transcription error injection.

Each mechanism takes the recorded value and returns the wrong one, or None if it
does not apply.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import config as C

EPOCH = dt.date(1970, 1, 1)


def _written(value: float, dec: int) -> str:
    return f"{abs(value):.{dec}f}"


def transpose_digits(value: float, dec: int, rng: np.random.Generator) -> float | None:
    """Swap two adjacent digits that differ. The decimal point stays put, and a swap that would
    only move it (100 -> 010, 0.5 -> 5.0) or leave a leading zero (10.5 -> 01.5) is not a
    transposition but a decimal slip, so it is never produced."""
    s = _written(value, dec)
    point = s.find(".")
    digits = list(s.replace(".", ""))
    options = []
    for i in range(len(digits) - 1):
        if digits[i] == digits[i + 1] or (i == 0 and digits[1] == "0"):
            continue
        d = digits.copy()
        d[i], d[i + 1] = d[i + 1], d[i]
        out = "".join(d) if point < 0 else "".join(d[:point]) + "." + "".join(d[point:])
        new = float(out)
        if new > 0 and new != value and not any(np.isclose(new, value * k) for k in (10, 0.1)):
            options.append(new)
    if not options:
        return None
    return options[rng.integers(len(options))]


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


def previous_values(cells: pd.DataFrame) -> pd.Series:
    """Same field at the patient's previous recorded visit (NaN if none)."""
    c = cells.sort_values(["subject_id", "field", "visit_idx"])
    return c.groupby(["subject_id", "field"]).value.shift(1).reindex(cells.index)


def swap_pairs(cells: pd.DataFrame, group: pd.Series, eligible: np.ndarray, n_pairs: int,
               rng: np.random.Generator) -> list[tuple[int, int]]:
    """Pairs of cells to swap: same field and visit, same split, different patients, different values."""
    pool = cells[eligible].assign(group=lambda d: d.subject_id.map(group))
    by_key = {k: list(g.index) for k, g in pool.groupby(["field", "visit", "group"])}
    used: set[int] = set()
    pairs = []
    for a in rng.permutation(pool.index):
        if len(pairs) == n_pairs:
            break
        if a in used:
            continue
        ra = pool.loc[a]
        cand = [b for b in by_key[(ra.field, ra.visit, ra.group)]
                if b not in used and b != a and pool.at[b, "subject_id"] != ra.subject_id and pool.at[b, "value"] != ra.value]
        if cand:
            b = cand[rng.integers(len(cand))]
            pairs.append((a, b))
            used.update((a, b))
    return pairs


def allocate(n_cells: int, rate: float, types=C.ERROR_TYPES) -> dict[str, int]:
    """Planned number of errors per type: the total split into equal shares."""
    total = int(round(rate * n_cells))
    base, extra = divmod(total, len(types))
    return {t: base + (i < extra) for i, t in enumerate(types)}


def inject(cells: pd.DataFrame, group: pd.Series, rate: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Corrupt a copy of the cells. Returns (corrupted cells, ground truth, planned vs injected counts)."""
    rng = np.random.default_rng(seed)
    cells = cells.reset_index(drop=True)
    value = cells.value.to_numpy().copy()
    is_date = cells.modality.eq("date").to_numpy()
    spec = C.VALUE_FIELDS
    taken = np.zeros(len(cells), bool)
    truth = []

    def record(i, etype, new, mech, partner=-1):
        truth.append(dict(cell_id=int(cells.cell_id.iat[i]), error_type=etype, mechanism=mech,
                          original=float(cells.value.iat[i]), injected=float(new),
                          partner_cell_id=int(cells.cell_id.iat[partner]) if partner >= 0 else -1))
        value[i] = new
        taken[i] = True

    planned = allocate(len(cells), rate)
    prev = previous_values(cells).to_numpy()
    for etype, k in planned.items():
        done = 0
        if etype == "patient_swap":
            for a, b in swap_pairs(cells, group, ~is_date & ~taken, k // 2, rng):
                va, vb = cells.value.iat[a], cells.value.iat[b]
                record(a, etype, vb, "swapped", b)
                record(b, etype, va, "swapped", a)
            continue
        if etype == "wrong_date":
            pool = np.flatnonzero(is_date & ~taken)
        elif etype == "copy_previous":
            pool = np.flatnonzero(~is_date & ~taken & ~np.isnan(prev) & (prev != cells.value.to_numpy()))
        else:
            pool = np.flatnonzero(~is_date & ~taken)
        for i in rng.permutation(pool):
            if done == k:
                break
            v, field = cells.value.iat[i], cells.field.iat[i]
            if etype == "wrong_date":
                out = wrong_date(int(v), rng)
                new, mech = out if out else (None, None)
            elif etype == "copy_previous":
                new, mech = prev[i], "copied from previous visit"
            elif etype == "unit_error":
                new, mech = unit_error(v, spec[field]["alt"]), "alternative unit"
            elif etype == "decimal_slip":
                new = decimal_slip(v, spec[field]["dec"], rng)
                mech = None if new is None else ("x10" if new > v else "/10")
            else:
                new, mech = transpose_digits(v, spec[field]["dec"], rng), "adjacent digits exchanged"
            if new is not None:
                record(i, etype, new, mech)
                done += 1

    truth = pd.DataFrame(truth, columns=["cell_id", "error_type", "mechanism", "original", "injected", "partner_cell_id"])
    corrupted = cells.assign(value=value)
    counts = {t: dict(planned=planned[t], injected=int((truth.error_type == t).sum())) for t in planned}
    return corrupted, truth, counts
