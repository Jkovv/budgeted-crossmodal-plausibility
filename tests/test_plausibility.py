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


def test_local_maxima_keeps_the_worst_cell_per_neighbourhood():
    cells = pd.DataFrame({"subject_id": [1, 1, 1, 1, 2], "visit_idx": [0, 0, 1, 2, 0],
                          "field": ["hemoglobin", "hematocrit", "hemoglobin", "hemoglobin", "hemoglobin"]})
    prev, nxt = P.adjacent_positions(cells)
    assert prev.tolist() == [-1, -1, 0, 2, -1] and nxt.tolist() == [2, -1, 3, -1, -1]
    absz = np.array([9.0, 5.0, 6.0, 4.5, 5.0])
    pending = absz > 4
    keep = P.local_maxima(cells, pending, absz, prev, nxt)
    # 1 loses to 0 (same visit), 2 to 0 (adjacent visit), 3 to 2 (adjacent visit), 4 is alone
    assert keep.tolist() == [0, 4]


def test_explaining_away_clears_the_innocent_neighbour():
    train, test = _cohort(80, 6), _cohort(20, 7)
    base, ctx = _ctx(pd.concat([train, test]))
    model = P.PlausibilityModel().fit(train, base, ctx)
    bad = test.index[(test.field == "hemoglobin") & (test.subject_id == 3) & (test.visit_idx == 2)][0]
    test.loc[bad, "value"] += 5
    out = P.score_with_explaining_away(model, test, base, ctx)
    assert abs(out.z[bad]) > 4 and out.confirmed[bad]
    hct = test.index[(test.field == "hematocrit") & (test.subject_id == 3) & (test.visit_idx == 2)][0]
    assert abs(out.z[hct]) <= abs(out.z_first[hct]) + 1e-9


def test_nothing_pending_means_one_pass():
    train = _cohort(40, 8)
    base, ctx = _ctx(train)
    model = P.PlausibilityModel().fit(train, base, ctx)
    out = P.score_with_explaining_away(model, _cohort(10, 9), base, ctx)
    if not (np.abs(out.z_first) > 4).any():
        assert np.allclose(out.z, out.z_first) and out.rounds.iat[0] == 0
