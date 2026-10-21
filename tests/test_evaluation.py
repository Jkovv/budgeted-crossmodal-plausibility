import numpy as np
import pandas as pd
import pytest

from bcp import config as C
from bcp import evaluation as E


@pytest.fixture
def setup_and_reps():
    rng = np.random.default_rng(0)
    rows = []
    for s in range(20):
        for v in range(4):
            for f in ("sodium", "potassium"):
                rows.append(dict(cell_id=len(rows), subject_id=s, visit=f"D{v + 1}", visit_idx=v, modality="lab",
                                 field=f, value=140.0 if f == "sodium" else 4.0))
    cells = pd.DataFrame(rows)
    visits = cells[["subject_id", "visit"]].drop_duplicates()
    split = pd.Series({s: "train" if s < 10 else "test" for s in range(20)})
    data = {"cells": cells, "visits": visits}
    setup = E.Setup(data, split, n_boot=50)
    test = cells[cells.subject_id >= 10].reset_index(drop=True).copy()
    err = rng.random(len(test)) < 0.15
    test["error_type"] = np.where(err, "decimal_slip", None)
    test["original"] = np.where(err, test.value, np.nan)
    test.loc[err, "value"] = test.value[err] * 10
    test["rules"] = 0.0
    test["delta"] = rng.random(len(test))
    test["model_full"] = err * 10 + rng.random(len(test))       # perfect ranking
    test["combined"] = test.model_full
    return setup, [(0, test, test.iloc[:0])]


def test_perfect_detector_hits_every_query_until_errors_run_out(setup_and_reps):
    setup, reps = setup_and_reps
    tab, _ = E.budget_analysis(setup, reps)
    est = tab[(tab.detector == "model_full")].set_index(["metric", "budget"]).estimate
    n_err = reps[0][1].error_type.notna().sum()
    V = setup.visits_per_patient.sum()
    for b in C.BUDGETS:
        Q = round(b * V)
        assert est[("yield", b)] == pytest.approx(min(Q, n_err) / Q)
        assert est[("recall", b)] == pytest.approx(min(Q, n_err) / n_err)


def test_detector_with_nothing_to_flag_raises_no_queries(setup_and_reps):
    setup, reps = setup_and_reps
    tab, _ = E.budget_analysis(setup, reps)
    r = tab[(tab.detector == "rules")].set_index(["metric", "budget"]).estimate
    assert all(r[("queries_raised", b)] == 0 and r[("yield", b)] == 0 for b in C.BUDGETS)


def test_size_labels():
    clean = pd.DataFrame(dict(subject_id=np.repeat([1, 2], 20), modality="lab", field="sodium",
                              value=np.r_[np.linspace(130, 150, 20), np.linspace(130, 150, 20)]))
    test = pd.DataFrame(dict(modality=["lab", "lab", "date", "date", "lab"], field=["sodium", "sodium", "lab_date", "lab_date", "sodium"],
                             value=[141.0, 240.0, 1035.0, 1003.0, 140.0], original=[140.0, 140.0, 1000.0, 1000.0, np.nan],
                             error_type=["digit_transposition", "unit_error", "wrong_date", "wrong_date", None]))
    lab = E.size_labels(test, clean, [1, 2])
    assert list(lab) == ["< 0.5 sd", "> 2.0 sd", "date > 7 days", "date <= 7 days", None]


def test_headline_verdict():
    rows = [dict(detector="model_full", budget=0.25, metric="yield", estimate=0.4, lo=0.3, hi=0.5),
            dict(detector="rules", budget=0.25, metric="yield", estimate=0.2, lo=0.1, hi=0.3),
            dict(detector="model_full", budget=0.25, metric="diff_vs_rules|yield", estimate=0.2, lo=0.05, hi=0.3)]
    assert E.headline(pd.DataFrame(rows))["verdict"] == "better"
    rows[2].update(lo=-0.01)
    assert E.headline(pd.DataFrame(rows))["verdict"] == "no clear difference"
