"""One replicate: inject, fit on training patients, score held-out patients.

Writes row-level outputs to results/cells/ (not committed):
  <analysis>_r<rep>_test.parquet   held-out cells: scores per detector, injected error if any
  <analysis>_r<rep>_calib.parquet  training cells of clean visits: first-pass scores for conformal p-values
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import config as C
from .delta import DeltaCheck
from .inject import inject
from .plausibility import PlausibilityModel, score_with_explaining_away
from .rules import range_scores

RATE_OFFSET = {C.ERROR_RATE: 0, C.SENSITIVITY_RATES[0]: 10_000, C.SENSITIVITY_RATES[1]: 20_000}
COMBINED_SHIFT = 1e6          # range violations go first in the combined ranking


def split_patients(subjects, seed: int = C.SEED) -> pd.Series:
    subjects = np.sort(np.asarray(subjects))
    order = np.random.default_rng(seed).permutation(len(subjects))
    group = np.where(np.argsort(order) < C.N_TRAIN, "train", "test")
    return pd.Series(group, index=subjects, name="group")


def injection_seed(rate: float, rep: int) -> int:
    return C.SEED + RATE_OFFSET[rate] + rep


def run_replicate(data: dict, split: pd.Series, rate: float, rep: int, variants=("full",),
                  baselines: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    t0 = time.time()
    cells, base, ctx = data["cells"], data["baseline"], data["visit_context"]
    corrupted, truth, counts = inject(cells, split, rate, injection_seed(rate, rep))
    is_train = corrupted.subject_id.map(split).eq("train").to_numpy()
    train = corrupted[is_train].reset_index(drop=True)
    test = corrupted[~is_train].reset_index(drop=True)

    t = truth.set_index("cell_id")
    out = test[["cell_id", "subject_id", "visit", "visit_idx", "modality", "field", "value"]].copy()
    out["error_type"] = out.cell_id.map(t.error_type)
    out["original"] = out.cell_id.map(t.original)

    err_cells = set(truth.cell_id)
    tr = train.assign(has_err=train.cell_id.isin(err_cells))
    clean_visit = ~tr.groupby(["subject_id", "visit"]).has_err.transform("any")
    calib = tr.loc[clean_visit, ["cell_id", "subject_id", "visit", "field"]].copy()

    if baselines:
        out["rules"] = range_scores(test)
        calib["rules"] = range_scores(train)[clean_visit.to_numpy()]
        delta = DeltaCheck().fit(train)
        out["delta"] = delta.score(test)
        calib["delta"] = delta.score(train)[clean_visit.to_numpy()]

    for v in variants:
        model = PlausibilityModel(v, seed=C.SEED + rep).fit(train, base, ctx)
        res = score_with_explaining_away(model, test, base, ctx)
        out[f"model_{v}"] = np.abs(res.z.to_numpy())
        out[f"model_{v}_first"] = np.abs(res.z_first.to_numpy())
        calib[f"model_{v}"] = np.abs(model.train_z.reindex(calib.cell_id).to_numpy())
        if v == "full":
            counts["explaining_away_rounds"] = int(res.rounds.iat[0])

    if baselines and "full" in variants:
        out["combined"] = np.where(out.rules > 0, COMBINED_SHIFT + out.rules, out.model_full)
        out["combined_first"] = np.where(out.rules > 0, COMBINED_SHIFT + out.rules, out.model_full_first)
        calib["combined"] = np.where(calib.rules > 0, COMBINED_SHIFT + calib.rules, calib.model_full)

    counts.update(rep=rep, rate=rate, seconds=round(time.time() - t0, 1), n_test_cells=int(len(test)),
                  n_test_errors=int(out.error_type.notna().sum()), n_calibration_cells=int(len(calib)))
    return out, calib, counts
