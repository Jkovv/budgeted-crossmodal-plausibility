"""EDC-style checks: a fixed range per field, a visit window per form date."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def range_scores(cells: pd.DataFrame) -> np.ndarray:
    """Severity of each cell's violation, 0 when it passes.

    Values: distance outside the range / range width. Dates: days outside the visit window
    / window, or days before the previous visit's date for the same form / window.
    """
    score = np.zeros(len(cells))
    is_date = cells.modality.eq("date").to_numpy()
    v = cells.value.to_numpy()

    vals = cells[~is_date]
    lo = vals.field.map({f: d["edc"][0] for f, d in C.VALUE_FIELDS.items()}).to_numpy(float)
    hi = vals.field.map({f: d["edc"][1] for f, d in C.VALUE_FIELDS.items()}).to_numpy(float)
    x = v[~is_date]
    score[~is_date] = np.maximum.reduce([lo - x, x - hi, np.zeros_like(x)]) / (hi - lo)

    d = cells[is_date]
    w = d.window_days.to_numpy(float)
    off = (d.value - d.nominal_date).to_numpy()
    outside = np.maximum(np.abs(off) - w, 0) / w
    order = d.sort_values(["subject_id", "field", "visit_idx"])
    prev = order.groupby(["subject_id", "field"]).value.shift(1).reindex(d.index).to_numpy()
    before = np.where(np.isnan(prev), 0, np.maximum(prev - d.value.to_numpy(), 0)) / w
    score[is_date] = np.maximum(outside, before)
    return score


class RangeRules:
    name = "range rules"

    def fit(self, train_cells: pd.DataFrame, **_) -> "RangeRules":
        return self

    def score(self, cells: pd.DataFrame, **_) -> np.ndarray:
        return range_scores(cells)
