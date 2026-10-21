import numpy as np
import pandas as pd

from bcp import features as F


def _cells():
    rows = []
    for s in (1, 2):
        for v in range(3):
            for f, val in (("sodium", 140 + v + s), ("chloride", 100 + v), ("bicarbonate", 24.0), ("sbp", 120 + 5 * v)):
                rows.append(dict(subject_id=s, visit=f"D{v + 1}", visit_idx=v, day=v + 1, nominal_date=1000 + v,
                                 window_days=1, modality="vital" if f == "sbp" else "lab", field=f, value=float(val)))
            rows.append(dict(subject_id=s, visit=f"D{v + 1}", visit_idx=v, day=v + 1, nominal_date=1000 + v,
                             window_days=1, modality="date", field="lab_date", value=1000.0 + v + (v == 2)))
    c = pd.DataFrame(rows)
    c.insert(0, "cell_id", np.arange(len(c)))
    return c


BASE = pd.DataFrame({"subject_id": [1, 2], "age": [60, 70], "female": [0, 1]})
CTX = pd.DataFrame({"subject_id": [1, 1, 1, 2, 2, 2], "visit": ["D1", "D2", "D3"] * 2, "med_insulin": [0, 1, 1, 0, 0, 1]})


def test_own_value_never_in_its_features():
    feats = F.build(_cells(), BASE, CTX)
    for field in ("sodium", "chloride", "sbp", "lab_date"):
        cols = F.columns_for(feats, field)
        rows = feats[feats.field == field]
        for c in cols:
            same = np.isclose(rows[c].to_numpy(float), rows.value.to_numpy(float), equal_nan=False)
            assert not same.all(), (field, c)


def test_own_history_and_relations():
    feats = F.build(_cells(), BASE, CTX).set_index(["subject_id", "visit_idx", "field"])
    r = feats.loc[(1, 1, "sodium")]
    assert r.own_prev == 141 and r.own_next == 143 and r.own_dt_prev == 1 and r.own_n == 2
    assert r.own_loo == 142                                   # median of 141 and 143
    assert r["lab_x:cl_plus_hco3"] == 101 + 24
    assert r["lab_d:chloride"] == 1
    assert r["medcls:insulin"] == 1 and r["base:age"] == 60
    d = feats.loc[(1, 2, "lab_date")]
    assert d.y == 1 and d.own_prev == 0                       # offsets from the nominal date


def test_masked_cells_leave_others_context():
    c = _cells()
    masked = (c.subject_id == 1) & (c.visit_idx == 1) & (c.field == "sodium")
    feats = F.build(c, BASE, CTX, masked=masked.to_numpy()).set_index(["subject_id", "visit_idx", "field"])
    assert feats.loc[(1, 2, "sodium")].own_prev == 141        # skips the masked 142
    assert np.isnan(feats.loc[(1, 1, "chloride")]["lab_x:na_minus_hco3"])
    assert feats.loc[(1, 1, "sodium")].y == 142               # the masked cell keeps its own target


def test_ablation_groups():
    feats = F.build(_cells(), BASE, CTX)
    full = set(F.columns_for(feats, "sodium"))
    own_only = set(F.columns_for(feats, "sodium", F.ABLATION_DROPS["own_history_only"]))
    cross = set(F.columns_for(feats, "sodium", F.ABLATION_DROPS["cross_modal_only"]))
    assert own_only == {c for c in full if c.startswith("own_")} | {"day", "window_days"}
    assert not any(c.startswith("own_") for c in cross)
    assert not any(c.startswith("date:") for c in full)
    assert set(F.columns_for(feats, "lab_date")) <= {c for c in feats if c.startswith(("own_", "date:"))} | {"day", "window_days"}
