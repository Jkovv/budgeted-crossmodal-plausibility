"""Evaluation on held-out patients: budget metrics, ablation, conformal false-query control and the
index-of-individuality test. Reads results/cells/, writes aggregate tables only."""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import config as C
from . import stats as S
from .delta import robust_sd
from .features import model_scale

DETECTORS = ["rules", "delta", "model_full", "combined"]
LABELS = {"rules": "Range rules", "delta": "Delta check", "model_full": "Plausibility model", "combined": "Combined"}


def load(analysis: str, reps) -> list[tuple[int, pd.DataFrame, pd.DataFrame]]:
    out = []
    for r in reps:
        test = pd.read_parquet(C.CELLS_DIR / f"{analysis}_r{r:02d}_test.parquet")
        calib = pd.read_parquet(C.CELLS_DIR / f"{analysis}_r{r:02d}_calib.parquet")
        out.append((r, test, calib))
    return out


# masks
def size_labels(test: pd.DataFrame, clean: pd.DataFrame, train_ids) -> np.ndarray:
    """Error size bin of every injected error (robust sd units on the model scale; dates in days)."""
    lab = np.full(len(test), None, dtype=object)
    err = test.error_type.notna().to_numpy()
    is_date = test.modality.eq("date").to_numpy()
    days = np.abs(test.value - test.original).to_numpy()
    lab[err & is_date & (days <= C.DATE_SIZE_BIN)] = f"date <= {C.DATE_SIZE_BIN} days"
    lab[err & is_date & (days > C.DATE_SIZE_BIN)] = f"date > {C.DATE_SIZE_BIN} days"
    tr = clean[clean.subject_id.isin(train_ids) & clean.modality.ne("date")]
    sd = {}
    for f, g in tr.groupby("field"):
        y = model_scale(f, g.value)
        s = robust_sd(y)
        sd[f] = s if s > 0 else (float(np.std(y)) or 1.0)      # some doses barely vary in training
    lo, hi = C.SIZE_BINS
    for f in test.field[err & ~is_date].unique():
        m = err & ~is_date & (test.field == f).to_numpy()
        size = np.abs(model_scale(f, test.value[m]) - model_scale(f, test.original[m])) / sd[f]
        lab[np.flatnonzero(m)] = np.where(size < lo, f"< {lo} sd", np.where(size <= hi, f"{lo}-{hi} sd", f"> {hi} sd"))
    return lab


def masks_for(test: pd.DataFrame, sizes: np.ndarray) -> dict[str, np.ndarray]:
    et = test.error_type
    m = {"err": et.notna().to_numpy()}
    for t in C.ERROR_TYPES:
        m[f"type:{t}"] = et.eq(t).to_numpy()
    for s in pd.unique(sizes[sizes != np.array(None)]):
        m[f"size:{s}"] = sizes == s
    return m


def queryable(test: pd.DataFrame, det: str) -> np.ndarray:
    s = test[det].to_numpy(float).copy()
    if det == "rules":
        s[s <= 0] = np.nan                       # only violations can be queried
    return s


# budgets
class Setup:
    """Held-out patients, their patient-visits and the shared bootstrap resamples."""

    def __init__(self, data: dict, split: pd.Series, n_boot: int = C.N_BOOTSTRAP):
        visits = data["visits"]
        test_ids = np.sort(split.index[split.eq("test")])
        self.patients = test_ids
        self.pos = {s: i for i, s in enumerate(test_ids)}
        self.visits_per_patient = visits[visits.subject_id.isin(test_ids)].groupby("subject_id").size() \
            .reindex(test_ids).fillna(0).to_numpy(float)
        self.W = S.patient_weights(len(test_ids), n_boot, np.random.default_rng(C.SEED + 1))
        self.clean = data["cells"]
        self.train_ids = split.index[split.eq("train")]


def tie_seed(rep: int, det: str) -> int:
    return C.SEED + 100 * rep + (DETECTORS.index(det) if det in DETECTORS else 9)


def counts_for(setup: Setup, test: pd.DataFrame, det: str, rep: int, masks) -> dict[str, np.ndarray]:
    order = S.rank_order(queryable(test, det), np.random.default_rng(tie_seed(rep, det)))
    patient = test.subject_id.map(setup.pos).to_numpy()
    return S.budget_counts(order, patient, masks, setup.visits_per_patient, C.BUDGETS, setup.W)


def metric_draws(counts: dict, masks) -> dict[str, np.ndarray]:
    """Per-resample metrics (resamples x budgets) from one replicate's counts."""
    with np.errstate(invalid="ignore", divide="ignore"):
        out = {"yield": counts["tp_err"] / counts["Q"], "precision": counts["tp_err"] / counts["raised"],
               "queries_raised": counts["raised"], "recall": counts["tp_err"] / counts["n_err"]}
        for k in masks:
            if k != "err":
                out[f"recall|{k}"] = counts[f"tp_{k}"] / counts[f"n_{k}"]
    return out


def average_over_replicates(per_rep: list[dict]) -> dict[str, np.ndarray]:
    keys = dict.fromkeys(k for d in per_rep for k in d)     # first-seen order, not hash order
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # precision is NaN when nothing is raised
        return {k: np.nanmean(np.stack([d[k] for d in per_rep if k in d]), axis=0) for k in keys}


def summarise(draws: dict[str, np.ndarray], det: str, extra: dict | None = None) -> list[dict]:
    rows = []
    for k, a in draws.items():
        lo, hi = S.percentile_ci(a[1:])
        for j, b in enumerate(C.BUDGETS):
            rows.append(dict(detector=det, budget=b, metric=k, estimate=a[0, j], lo=lo[j], hi=hi[j], **(extra or {})))
    return rows


def budget_analysis(setup: Setup, reps, detectors=DETECTORS, reference="rules") -> tuple[pd.DataFrame, dict]:
    per_det: dict[str, list[dict]] = {d: [] for d in detectors}
    for rep, test, _ in reps:
        sizes = size_labels(test, setup.clean, setup.train_ids)
        masks = masks_for(test, sizes)
        for d in detectors:
            per_det[d].append(metric_draws(counts_for(setup, test, d, rep, masks), masks))
    avg = {d: average_over_replicates(v) for d, v in per_det.items()}
    rows = []
    for d in detectors:
        rows += summarise(avg[d], d)
        if d != reference:
            diff = {f"diff_vs_{reference}|{k}": avg[d][k] - avg[reference][k]
                    for k in ("yield", "precision", "recall", "queries_raised")}
            rows += summarise(diff, d)
    return pd.DataFrame(rows), avg


# ablation
def ablation_analysis(setup: Setup, reps, variants) -> pd.DataFrame:
    cols = [f"model_{v}" for v in variants]
    per = {c: [] for c in cols}
    for rep, test, _ in reps:
        masks = masks_for(test, size_labels(test, setup.clean, setup.train_ids))
        for c in cols:
            order = S.rank_order(test[c].to_numpy(float), np.random.default_rng(tie_seed(rep, c)))
            patient = test.subject_id.map(setup.pos).to_numpy()
            counts = S.budget_counts(order, patient, masks, setup.visits_per_patient, C.BUDGETS, setup.W)
            per[c].append(metric_draws(counts, masks))
    avg = {c: average_over_replicates(v) for c, v in per.items()}
    rows = []
    for c in cols:
        rows += summarise({k: v for k, v in avg[c].items() if k.startswith(("yield", "precision", "recall"))}, c)
        if c != "model_full":
            diff = {f"diff_vs_full|{k}": avg[c][k] - avg["model_full"][k] for k in avg[c] if k.startswith(("yield", "recall"))}
            rows += summarise(diff, c)
    return pd.DataFrame(rows)


# conformal false-query control
def pseudo_sites(patients) -> dict:
    order = np.random.default_rng(C.SEED + 2).permutation(len(patients))
    return {p: int(k % C.N_SITES) for p, k in zip(np.asarray(patients)[order], range(len(patients)))}


def conformal_analysis(setup: Setup, reps, detectors=DETECTORS) -> pd.DataFrame:
    """Benjamini-Hochberg on conformal p-values within each pseudo-site.

    Intervals are the 2.5 and 97.5 percentiles over replicates. The patient bootstrap is not used
    here: duplicated patients bring duplicated p-values, and BH then rejects more than it would on
    real data, so resampled counts are biased upward.
    """
    site_of = pseudo_sites(setup.patients)
    ones = np.ones((1, len(setup.patients)))
    V = float(setup.visits_per_patient.sum())
    per = {(d, a): [] for d in detectors for a in C.FDR_TARGETS}
    for rep, test, calib in reps:
        err = test.error_type.notna().to_numpy()
        patient = test.subject_id.map(setup.pos).to_numpy()
        site = test.subject_id.map(site_of).to_numpy()
        for d in detectors:
            first = f"{d}_first" if f"{d}_first" in test else d          # same score as the calibration set
            p = S.conformal_pvalues(calib[d].to_numpy(float), test[first].to_numpy(float))
            for a in C.FDR_TARGETS:
                raised = tp = 0.0
                site_fdp = []
                for k in range(C.N_SITES):
                    m = site == k
                    r = S.bh_counts(p[m], {"err": err[m]}, a, ones[:, patient[m]])
                    raised += r["raised"][0]
                    tp += r["tp_err"][0]
                    site_fdp.append(1 - r["tp_err"][0] / r["raised"][0] if r["raised"][0] > 0 else 0.0)
                per[(d, a)].append({"queries_raised": raised, "queries_per_patient_visit": raised / V,
                                    "errors_caught": tp, "false_query_rate": 1 - tp / raised if raised > 0 else 0.0,
                                    "mean_site_false_query_rate": float(np.mean(site_fdp)),
                                    "recall": tp / err.sum()})
    rows = []
    for (d, a), lst in per.items():
        for k in lst[0]:
            vals = np.array([x[k] for x in lst])
            rows.append(dict(detector=d, target=a, metric=k, estimate=vals.mean(),
                             lo=np.quantile(vals, 0.025), hi=np.quantile(vals, 0.975)))
    return pd.DataFrame(rows)


# index of individuality
def rank_test(x, y, seed: int) -> tuple[float, float]:
    if len(x) < 3:
        return np.nan, np.nan
    return S.spearman_permutation(x, y, C.N_PERMUTATIONS, np.random.default_rng(seed), alternative="less")


def individuality_analysis(data: dict, split: pd.Series, reps_primary, reps_ablation) -> tuple[pd.DataFrame, dict]:
    cells = data["cells"]
    train = cells[cells.subject_id.map(split).eq("train")]
    fields = [f for f in list(C.LAB_FIELDS) + list(C.VITAL_FIELDS)]
    rows = []
    for f in fields:
        t = train[train.field == f]
        ii = S.index_of_individuality(model_scale(f, t.value), t.subject_id.to_numpy(), C.II_MIN_VISITS)
        row = dict(field=f, modality=C.FIELD_MODALITY[f], index_of_individuality=ii)
        for name, reps, col in (("full", reps_primary, "model_full"), ("own_history_only", reps_ablation, "model_own_history_only")):
            pooled = pd.concat([x[1][x[1].field == f] for x in reps], ignore_index=True)
            keep = pooled.error_type.isna() | pooled.error_type.eq("patient_swap")
            pooled = pooled[keep]
            y = pooled.error_type.eq("patient_swap").to_numpy()
            row[f"n_swapped_{name}"] = int(y.sum())
            row[f"auroc_{name}"] = roc_auc_score(y, pooled[col]) if 0 < y.sum() < len(y) else np.nan
        rows.append(row)
    tab = pd.DataFrame(rows)
    use = tab[(tab.n_swapped_full >= C.II_MIN_SWAPS) & tab.index_of_individuality.notna()]
    rho, p = rank_test(use.index_of_individuality, use.auroc_full, C.SEED + 3)
    ok = use.auroc_own_history_only.notna()
    slope, intercept = (np.polyfit(use.index_of_individuality[ok], use.auroc_own_history_only[ok], 1)
                        if ok.sum() >= 2 else (np.nan, np.nan))     # a quick run may have too few swaps
    tab["line_from_own_history"] = intercept + slope * tab.index_of_individuality
    tab["above_line"] = tab.auroc_full - tab.line_from_own_history
    tab["gain_over_own_history"] = tab.auroc_full - tab.auroc_own_history_only
    tab["in_test"] = tab.field.isin(use.field)
    tab["changed_by_cross_modal_context"] = tab.in_test & (tab.gain_over_own_history >= C.II_GAIN) & (tab.above_line > 0)
    every = tab[tab.auroc_full.notna() & tab.index_of_individuality.notna()]
    rho_all, p_all = rank_test(every.index_of_individuality, every.auroc_full, C.SEED + 4)
    res = dict(spearman_rho=rho, p_one_sided=p, n_fields=int(len(use)), hypothesis_holds=bool(rho < 0 and p < 0.05),
               exploratory_all_fields=dict(spearman_rho=rho_all, p_one_sided=p_all, n_fields=int(len(every))),
               line_slope=float(slope), line_intercept=float(intercept),
               changed_by_cross_modal_context=tab.field[tab.changed_by_cross_modal_context].tolist())
    return tab, res


def swap_recall_by_field(setup: Setup, reps, budget=C.PRIMARY_BUDGET) -> pd.DataFrame:
    """Share of swapped cells raised at the budget, per field (no bootstrap)."""
    hits = []
    for rep, test, _ in reps:
        order = S.rank_order(queryable(test, "model_full"), np.random.default_rng(tie_seed(rep, "model_full")))
        q = int(round(budget * setup.visits_per_patient.sum()))
        sel = np.zeros(len(test), bool)
        sel[order[:q]] = True
        hits.append(test.assign(raised=sel)[test.error_type.eq("patient_swap")])
    h = pd.concat(hits)
    return h.groupby("field").raised.agg(swap_recall="mean", n="size").reset_index()


def headline(budget_tab: pd.DataFrame) -> dict:
    b = C.PRIMARY_BUDGET
    get = lambda det, metric: budget_tab[(budget_tab.detector == det) & (budget_tab.budget == b) & (budget_tab.metric == metric)].iloc[0]
    d = get("model_full", "diff_vs_rules|yield")
    verdict = "better" if d.lo > 0 else "worse" if d.hi < 0 else "no clear difference"
    return dict(budget=b, model_yield=get("model_full", "yield").estimate, rules_yield=get("rules", "yield").estimate,
                difference=d.estimate, difference_lo=d.lo, difference_hi=d.hi, verdict=verdict)


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, default=lambda x: float(x) if isinstance(x, np.floating) else str(x)))
