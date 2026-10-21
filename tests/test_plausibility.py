import numpy as np
import pandas as pd
import pytest

from bcp import plausibility as P


def _cohort(n=60, seed=0):
    """Hemoglobin and hematocrit that track each other within patients, plus a lab date."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n):
        hb0 = rng.normal(10, 1.5)
        for v in range(5):
            hb = round(hb0 + rng.normal(0, 0.3), 1)
            hct = round(3 * hb + rng.normal(0, 0.5), 1)
            for f, val in (("hemoglobin", hb), ("hematocrit", hct)):
                rows.append(dict(subject_id=s, visit=f"D{v + 1}", visit_idx=v, day=v + 1, nominal_date=1000 + v,
                                 window_days=1, modality="lab", field=f, value=val))
            rows.append(dict(subject_id=s, visit=f"D{v + 1}", visit_idx=v, day=v + 1, nominal_date=1000 + v,
                             window_days=1, modality="date", field="lab_date", value=float(1000 + v)))
    c = pd.DataFrame(rows)
    c.insert(0, "cell_id", np.arange(len(c)))
    return c


BASE_COLS = ["subject_id", "age", "female"]


def _ctx(c):
    base = pd.DataFrame({"subject_id": c.subject_id.unique(), "age": 60, "female": 0})
    visits = c[["subject_id", "visit"]].drop_duplicates().assign(med_insulin=0)
    return base, visits


def test_model_flags_an_inconsistent_value_and_not_the_rest():
    train, test = _cohort(60, 0), _cohort(20, 1)
    base, ctx = _ctx(pd.concat([train, test]))
    model = P.PlausibilityModel().fit(train, base, ctx)
    bad = test.index[(test.field == "hemoglobin")][7]
    test.loc[bad, "value"] = test.loc[bad, "value"] + 4          # in range, but off from history and hematocrit
    z = np.abs(model.z(test, base, ctx))
    assert z[bad] > 4
    assert np.median(np.delete(z, bad)) < 1.5


def test_out_of_fold_training_scores_cover_every_cell():
    train = _cohort(40, 2)
    base, ctx = _ctx(train)
    model = P.PlausibilityModel().fit(train, base, ctx)
    assert model.train_z.notna().all() and len(model.train_z) == len(train)


def test_scoring_never_changes_the_data():
    train, test = _cohort(40, 3), _cohort(10, 4)
    base, ctx = _ctx(pd.concat([train, test]))
    before = test.copy()
    P.PlausibilityModel().fit(train, base, ctx).z(test, base, ctx)
    assert test.equals(before)


def test_sparse_fields_fall_back_to_a_population_z():
    train = _cohort(5, 5)                                         # 25 cells per field, under the minimum
    base, ctx = _ctx(train)
    model = P.PlausibilityModel().fit(train, base, ctx)
    assert all(m.simple for m in model.models.values())
    assert np.isfinite(model.z(train, base, ctx)).all()
