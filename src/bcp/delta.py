"""Delta check baseline: change since the previous recorded value of the same field."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _changes(cells: pd.DataFrame) -> pd.Series:
    c = cells[cells.modality != "date"].sort_values(["subject_id", "field", "visit_idx"])
    return (c.value - c.groupby(["subject_id", "field"]).value.shift(1)).reindex(cells.index)


def robust_sd(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return 1.4826 * float(np.median(np.abs(x - np.median(x)))) if len(x) else np.nan


class DeltaCheck:
    name = "delta check"

    def fit(self, train_cells: pd.DataFrame, **_) -> "DeltaCheck":
        d = _changes(train_cells)
        self.sd = {f: robust_sd(d[train_cells.field == f]) for f in train_cells.field.unique()}
        return self

    def score(self, cells: pd.DataFrame, **_) -> np.ndarray:
        """|change| / robust sd of changes; NaN (not scored) without a previous value and for dates."""
        sd = cells.field.map(self.sd).to_numpy(float)
        sd = np.where(sd > 0, sd, np.nan)
        return np.abs(_changes(cells).to_numpy()) / sd
