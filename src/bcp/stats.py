"""Statistics: budgeted selection, patient bootstrap, conformal p-values, Benjamini-Hochberg,
a permutation Spearman test and the index of individuality.

Bootstrap resamples enter as weights: a patient drawn k times gets weight k, so every
metric is a weighted count and all resamples can be computed at once.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy import stats as sps


def rank_order(score: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Positions of scored cells from most to least suspicious; ties in random order, NaN dropped."""
    score = np.asarray(score, float)
    ok = np.flatnonzero(~np.isnan(score))
    tie = rng.random(len(ok))
    return ok[np.lexsort((tie, -score[ok]))]


def patient_weights(n_patients: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Row 0 is the original sample (all ones), rows 1.. are bootstrap resamples."""
    draws = rng.multinomial(n_patients, np.full(n_patients, 1 / n_patients), size=n_boot)
    return np.vstack([np.ones(n_patients), draws]).astype(float)


def budget_counts(order: np.ndarray, patient: np.ndarray, masks: dict[str, np.ndarray], visits_per_patient: np.ndarray,
                  budgets, weights: np.ndarray) -> dict[str, np.ndarray]:
    """Weighted counts at each budget, for every row of ``weights`` (resamples x patients).

    order: ranked cell positions. patient: patient index of every cell. masks: boolean arrays over
    cells (for example errors of one type). Returns arrays of shape (resamples, budgets):
    Q (queries allowed), raised, and for each mask the number of raised cells in it ("tp_<name>")
    and its total ("n_<name>").
    """
    w_cells = weights[:, patient[order]]                       # resamples x ranked cells
    cum_w = np.cumsum(w_cells, axis=1)
    V = weights @ visits_per_patient
    Q = np.rint(np.outer(V, budgets))                          # resamples x budgets
    total_w = cum_w[:, -1] if cum_w.shape[1] else np.zeros(len(weights))
    raised = np.minimum(Q, total_w[:, None])
    out = {"Q": Q, "raised": raised}
    for name, m in masks.items():
        cum_m = np.cumsum(w_cells * m[order], axis=1)
        tp = np.zeros_like(Q)
        for j in range(Q.shape[1]):
            tp[:, j] = _take(cum_w, cum_m, raised[:, j])
        out[f"tp_{name}"] = tp
        out[f"n_{name}"] = np.broadcast_to((weights[:, patient] * m).sum(axis=1)[:, None], Q.shape).copy()
    return out


def _take(cum_w: np.ndarray, cum_m: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Weighted count of masked cells among the first q units of ranked weight (fractional at the edge)."""
    if cum_w.shape[1] == 0:
        return np.zeros(len(q))
    k = (cum_w < q[:, None]).sum(axis=1)                       # first position reaching q
    k = np.minimum(k, cum_w.shape[1] - 1)
    rows = np.arange(len(q))
    before_w = np.where(k > 0, cum_w[rows, k - 1], 0.0)
    before_m = np.where(k > 0, cum_m[rows, k - 1], 0.0)
    step_w = cum_w[rows, k] - before_w
    step_m = cum_m[rows, k] - before_m
    frac = np.where(step_w > 0, np.clip((q - before_w) / np.where(step_w > 0, step_w, 1), 0, 1), 0)
    return before_m + frac * step_m


def conformal_pvalues(calibration: np.ndarray, test: np.ndarray) -> np.ndarray:
    """Marginal conformal p-values (Bates et al. 2023): (1 + #{cal >= s}) / (n + 1). NaN scores get 1."""
    cal = np.sort(np.asarray(calibration, float)[~np.isnan(calibration)])
    s = np.asarray(test, float)
    n_ge = len(cal) - np.searchsorted(cal, s, side="left")
    p = (1 + n_ge) / (len(cal) + 1)
    return np.where(np.isnan(s), 1.0, p)


def bh_counts(p: np.ndarray, masks: dict[str, np.ndarray], alpha: float, weights: np.ndarray) -> dict[str, np.ndarray]:
    """Benjamini-Hochberg at level alpha with resampling weights (cell multiplicities).

    Returns, per resample, the number of rejections ("raised") and of rejected cells in each mask.
    """
    order = np.argsort(p, kind="stable")
    ps = p[order]
    w = weights[:, order]
    cum = np.cumsum(w, axis=1)
    m = cum[:, -1:]
    ok = (ps[None, :] <= cum * alpha / np.where(m > 0, m, 1)) & (w > 0)
    any_ok = ok.any(axis=1)
    last = np.where(any_ok, ok.shape[1] - 1 - np.argmax(ok[:, ::-1], axis=1), -1)
    cutoff = np.where(any_ok, ps[np.maximum(last, 0)], -np.inf)
    reject = ps[None, :] <= cutoff[:, None]
    out = {"raised": (w * reject).sum(axis=1)}
    for name, mask in masks.items():
        out[f"tp_{name}"] = (w * reject * mask[order][None, :]).sum(axis=1)
    return out


def spearman_permutation(x, y, n_perm: int, rng: np.random.Generator, alternative: str = "less") -> tuple[float, float]:
    """Spearman rho and a permutation p-value (one-sided by default: rho < 0)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    rho = sps.spearmanr(x, y).statistic
    ry = sps.rankdata(y)
    rx = sps.rankdata(x)
    perms = np.array([np.corrcoef(rx, ry[rng.permutation(len(ry))])[0, 1] for _ in range(n_perm)])
    hits = (perms <= rho) if alternative == "less" else (perms >= rho) if alternative == "greater" else (np.abs(perms) >= abs(rho))
    return float(rho), float((1 + hits.sum()) / (1 + n_perm))


def index_of_individuality(values: np.ndarray, patient: np.ndarray, min_visits: int = 3) -> float:
    """Within-patient SD (median over patients) / SD of patient medians, patients with enough visits."""
    values, patient = np.asarray(values, float), np.asarray(patient)
    sds, meds = [], []
    for p in np.unique(patient):
        v = values[patient == p]
        v = v[~np.isnan(v)]
        if len(v) >= min_visits:
            sds.append(np.std(v, ddof=1))
            meds.append(np.median(v))
    if len(meds) < 3:
        return np.nan
    between = np.std(meds, ddof=1)
    return float(np.median(sds) / between) if between > 0 else np.nan


def percentile_ci(draws: np.ndarray, level: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
    a = (1 - level) / 2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanquantile(draws, a, axis=0), np.nanquantile(draws, 1 - a, axis=0)
