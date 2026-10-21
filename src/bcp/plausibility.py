"""Cross-modal plausibility model: per field, a robust z of the recorded value given the patient's other data."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from . import config as C
from . import features as F
from .delta import robust_sd

# lightgbm names array columns itself, sklearn then complains at predict time
warnings.filterwarnings("ignore", message="X does not have valid feature names")


def _floor(field: str, center: float, scale: float) -> float:
    """Smallest sigma, in standardised units: half the recorded resolution, at least 0.1."""
    if field in C.DATE_FIELDS:
        step = 1.0
    else:
        d = C.VALUE_FIELDS[field]
        step = 10.0 ** -d["dec"]
        if d["tf"] == "log":
            step = step / np.exp(center)
    return max(0.1, 0.5 * step / scale)


class FieldModel:
    """Location and scale model for one field, or a population robust z when data are scarce."""

    def __init__(self, field, cols, seed):
        self.field, self.cols, self.seed = field, cols, seed

    def fit(self, X: pd.DataFrame, y: np.ndarray, folds: np.ndarray) -> np.ndarray:
        X = X.to_numpy(float)
        self.center = float(np.median(y))
        sd = robust_sd(y)
        self.scale = sd if sd > 0 else (float(np.std(y)) or 1.0)
        self.floor = _floor(self.field, self.center, self.scale)
        ys = (y - self.center) / self.scale
        self.simple = len(y) < C.MIN_TRAIN_CELLS or len(self.cols) == 0
        if self.simple:
            return ys / max(1.0, self.floor)
        mu_oof = np.full(len(y), np.nan)
        for k in np.unique(folds):
            tr, te = folds != k, folds == k
            mu_oof[te] = self._mu().fit(X[tr], ys[tr]).predict(X[te])
        absres = np.abs(ys - mu_oof)
        sig_oof = np.full(len(y), np.nan)
        for k in np.unique(folds):
            tr, te = folds != k, folds == k
            sig_oof[te] = 1.4826 * self._sigma().fit(X[tr], absres[tr]).predict(X[te])
        self.mu = self._mu().fit(X, ys)
        self.sigma = self._sigma().fit(X, absres)
        return (ys - mu_oof) / np.maximum(sig_oof, self.floor)

    def predict_z(self, X: pd.DataFrame, y: np.ndarray) -> np.ndarray:
        X = X.to_numpy(float)
        ys = (y - self.center) / self.scale
        if self.simple:
            return ys / max(1.0, self.floor)
        sig = np.maximum(1.4826 * self.sigma.predict(X), self.floor)
        return (ys - self.mu.predict(X)) / sig

    def _mu(self):
        return LGBMRegressor(**C.MU_PARAMS, random_state=self.seed)

    def _sigma(self):
        return LGBMRegressor(**C.SIGMA_PARAMS, random_state=self.seed)


class PlausibilityModel:
    name = "plausibility model"

    def __init__(self, variant: str = "full", seed: int = C.SEED):
        self.variant, self.seed = variant, seed
        self.drops = F.ABLATION_DROPS[variant]

    def fit(self, cells: pd.DataFrame, baseline: pd.DataFrame, visit_ctx: pd.DataFrame) -> "PlausibilityModel":
        feats = F.build(cells, baseline, visit_ctx)
        subjects = np.random.default_rng(self.seed).permutation(np.sort(feats.subject_id.unique()))
        fold_of = {s: i % C.N_FOLDS for i, s in enumerate(subjects)}
        self.models: dict[str, FieldModel] = {}
        oof = pd.Series(np.nan, index=feats.cell_id.to_numpy())
        for field, rows in feats.groupby("field"):
            cols = F.columns_for(feats, field, self.drops)
            m = FieldModel(field, cols, self.seed)
            z = m.fit(rows[cols], rows.y.to_numpy(), rows.subject_id.map(fold_of).to_numpy())
            oof[rows.cell_id.to_numpy()] = z
            self.models[field] = m
        self.train_z = oof          # out-of-fold, first pass: the conformal calibration scores
        return self

    def z(self, cells: pd.DataFrame, baseline: pd.DataFrame, visit_ctx: pd.DataFrame,
          masked: np.ndarray | None = None) -> np.ndarray:
        """Signed z for every cell, aligned with ``cells``."""
        feats = F.build(cells, baseline, visit_ctx, masked)
        out = np.full(len(feats), np.nan)
        for field, rows in feats.groupby("field"):
            m = self.models.get(field)
            if m is not None:
                out[rows.index] = m.predict_z(rows[m.cols], rows.y.to_numpy())
        return out
