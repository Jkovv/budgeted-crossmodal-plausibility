import numpy as np
import pytest

from bcp import inject as I


def outcomes(fn, *args, n=200):
    rng = np.random.default_rng(0)
    return {fn(*args, rng) for _ in range(n)}


@pytest.mark.parametrize("value,dec,expected", [
    (142, 0, {124.0, 412.0}),
    (4.6, 1, {6.4}),
    (0.9, 1, {9.0}),
    (1.25, 2, {2.15, 1.52}),
    (37.2, 1, {73.2, 32.7}),
])
def test_transpose_digits(value, dec, expected):
    assert outcomes(I.transpose_digits, value, dec) == expected


@pytest.mark.parametrize("value,dec", [(11, 0), (1.1, 1), (5, 0), (2.22, 2)])
def test_transpose_digits_not_applicable(value, dec):
    assert outcomes(I.transpose_digits, value, dec) == {None}


def test_transpose_digits_keeps_the_decimal_point():
    rng = np.random.default_rng(1)
    for v, dec in [(123.4, 1), (9.87, 2), (45.6, 1), (0.45, 2)]:
        new = I.transpose_digits(v, dec, rng)
        assert new is not None and new != v
        assert len(f"{new:.{dec}f}") == len(f"{v:.{dec}f}")      # point does not move


@pytest.mark.parametrize("value,dec,expected", [
    (4.1, 1, {41.0, 0.41}),
    (98, 0, {980.0, 9.8}),
    (1.25, 2, {12.5, 0.125}),
])
def test_decimal_slip(value, dec, expected):
    assert outcomes(I.decimal_slip, value, dec) == expected


def test_decimal_slip_directions_are_balanced():
    rng = np.random.default_rng(2)
    ups = sum(I.decimal_slip(10.0, 0, rng) == 100.0 for _ in range(4000))
    assert 1850 < ups < 2150


@pytest.mark.parametrize("field,value,expected", [
    ("glucose", 108, 6.0),          # mg/dL written as mmol/L
    ("creatinine", 1.0, 88.0),      # mg/dL written as umol/L
    ("bun", 28, 10.0),              # mg/dL written as mmol/L urea
    ("hemoglobin", 9.8, 98.0),      # g/dL written as g/L
    ("hematocrit", 30.2, 0.3),      # % written as a fraction
    ("temperature", 37.0, 98.6),    # Celsius written as Fahrenheit
    ("weight", 80.0, 176.4),        # kg written as lb
    ("vancomycin", 2000, 2.0),      # mg written as g
])
def test_unit_error(field, value, expected):
    from bcp import config as C
    assert I.unit_error(value, C.VALUE_FIELDS[field]["alt"]) == pytest.approx(expected)


@pytest.mark.parametrize("field", ["sodium", "potassium", "chloride", "bicarbonate", "wbc", "platelets",
                                   "heart_rate", "sbp", "spo2", "heparin_sc"])
def test_unit_error_not_applicable(field):
    from bcp import config as C
    assert I.unit_error(100.0, C.VALUE_FIELDS[field]["alt"]) is None


def _dn(y, m, d):
    import datetime as dt
    return (dt.date(y, m, d) - I.EPOCH).days


def _back(n):
    import datetime as dt
    return I.EPOCH + dt.timedelta(days=n)


def test_date_typos_cover_the_four_mechanisms():
    t = I.date_typos(_dn(2150, 3, 12))
    got = {k: sorted(str(_back(x)) for x in v) for k, v in t.items()}
    assert got == {"day_month_exchanged": ["2150-12-03"],
                   "day_digits_exchanged": ["2150-03-21"],
                   "month_off_by_one": ["2150-02-12", "2150-04-12"],
                   "year_off_by_one": ["2149-03-12", "2151-03-12"]}


def test_date_typos_skip_impossible_dates():
    jan31 = I.date_typos(_dn(2150, 1, 31))
    assert "day_month_exchanged" not in jan31                   # 31 is not a month
    assert [str(_back(x)) for x in jan31["day_digits_exchanged"]] == ["2150-01-13"]
    assert "month_off_by_one" not in jan31                      # no month 0, no 31 february
    assert "month_off_by_one" not in I.date_typos(_dn(2150, 3, 31))
    assert "day_month_exchanged" not in I.date_typos(_dn(2150, 5, 5))
    may5 = I.date_typos(_dn(2150, 5, 5))
    assert "day_digits_exchanged" not in may5                   # 05 -> 50
    assert "day_digits_exchanged" not in I.date_typos(_dn(2150, 5, 11))


def test_wrong_date_is_always_a_different_valid_date():
    rng = np.random.default_rng(3)
    start = _dn(2150, 1, 1)
    mechs = set()
    for k in range(400):
        n = start + k
        new, mech = I.wrong_date(n, rng)
        assert new != n
        mechs.add(mech)
    assert mechs == {"day_month_exchanged", "day_digits_exchanged", "month_off_by_one", "year_off_by_one"}


def _cells():
    import pandas as pd
    rows = []
    for s, vals in {1: [140, 141, 141], 2: [135, 150, 138], 3: [139, 139, 145], 4: [130, 132, 128]}.items():
        for v_idx, v in enumerate(vals):
            rows.append(dict(subject_id=s, visit=f"D{v_idx + 1}", visit_idx=v_idx, field="sodium", value=float(v)))
    return pd.DataFrame(rows)


def test_previous_values_follow_visit_order():
    c = _cells().sample(frac=1, random_state=0)
    prev = I.previous_values(c)
    s1 = c[c.subject_id == 1].sort_values("visit_idx")
    assert prev[s1.index].tolist()[1:] == [140.0, 141.0]
    assert np.isnan(prev[s1.index[0]])


def test_swap_pairs_respect_field_visit_split_and_values():
    import pandas as pd
    c = _cells()
    group = pd.Series({1: "train", 2: "train", 3: "test", 4: "test"})
    pairs = I.swap_pairs(c, group, np.ones(len(c), bool), 10, np.random.default_rng(0))
    assert pairs
    seen = set()
    for a, b in pairs:
        ra, rb = c.loc[a], c.loc[b]
        assert ra.field == rb.field and ra.visit == rb.visit
        assert group[ra.subject_id] == group[rb.subject_id] and ra.subject_id != rb.subject_id
        assert ra.value != rb.value
        assert not ({a, b} & seen)
        seen |= {a, b}


@pytest.fixture
def table():
    import pandas as pd
    rng = np.random.default_rng(5)
    rows = []
    for s in range(1, 41):
        base = dict(sodium=rng.normal(139, 4), glucose=rng.normal(130, 30), temperature=rng.normal(37, .5),
                    heart_rate=rng.normal(85, 12))
        for v in range(6):
            for f, mu in base.items():
                dec = {"sodium": 0, "glucose": 0, "temperature": 1, "heart_rate": 0}[f]
                rows.append(dict(subject_id=s, visit=f"D{v + 1}", visit_idx=v, field=f, modality="lab",
                                 value=round(float(mu + rng.normal(0, 2)), dec)))
            rows.append(dict(subject_id=s, visit=f"D{v + 1}", visit_idx=v, field="lab_date", modality="date",
                             value=float(66000 + 30 * s + v)))
    c = pd.DataFrame(rows)
    c.insert(0, "cell_id", np.arange(len(c)) + 1000)
    group = pd.Series({s: "train" if s <= 20 else "test" for s in range(1, 41)})
    return c, group


def test_inject_hits_the_planned_counts(table):
    c, group = table
    cor, truth, counts = I.inject(c, group, 0.05, seed=1)
    for t, n in counts.items():
        if t == "patient_swap":
            assert n["injected"] == 2 * (n["planned"] // 2)
        else:
            assert n["injected"] == n["planned"]
    assert sum(n["planned"] for n in counts.values()) == round(0.05 * len(c))
    assert truth.cell_id.is_unique


def test_inject_ground_truth_matches_the_data(table):
    c, group = table
    before = c.copy()
    cor, truth, _ = I.inject(c, group, 0.05, seed=2)
    assert c.equals(before)                                     # input untouched
    t = truth.set_index("cell_id")
    hit = cor.cell_id.isin(t.index)
    assert (cor.value[~hit] == c.value[~hit]).all()
    idx = cor.cell_id[hit]
    assert np.allclose(cor.value[hit], t.loc[idx, "injected"])
    assert np.allclose(c.value[hit], t.loc[idx, "original"])
    assert (t.injected != t.original).all()


def test_inject_types_go_to_the_right_cells(table):
    c, group = table
    cor, truth, _ = I.inject(c, group, 0.05, seed=3)
    mod = c.set_index("cell_id").modality
    assert (mod[truth.cell_id[truth.error_type == "wrong_date"]] == "date").all()
    assert (mod[truth.cell_id[truth.error_type != "wrong_date"]] != "date").all()
    fields = c.set_index("cell_id").field
    assert set(fields[truth.cell_id[truth.error_type == "unit_error"]]) <= {"glucose", "temperature"}


def test_copy_previous_uses_the_previous_visit(table):
    c, group = table
    _, truth, _ = I.inject(c, group, 0.05, seed=4)
    cc = c.set_index("cell_id")
    for r in truth[truth.error_type == "copy_previous"].itertuples():
        cell = cc.loc[r.cell_id]
        prev = cc[(cc.subject_id == cell.subject_id) & (cc.field == cell.field) & (cc.visit_idx == cell.visit_idx - 1)]
        assert r.injected == prev.value.item()


def test_swaps_are_symmetric_and_within_split(table):
    c, group = table
    _, truth, _ = I.inject(c, group, 0.05, seed=5)
    cc = c.set_index("cell_id")
    sw = truth[truth.error_type == "patient_swap"].set_index("cell_id")
    assert len(sw) > 0
    for cid, r in sw.iterrows():
        a, b = cc.loc[cid], cc.loc[r.partner_cell_id]
        assert sw.loc[r.partner_cell_id, "partner_cell_id"] == cid
        assert r.injected == b.value and sw.loc[r.partner_cell_id, "injected"] == a.value
        assert a.field == b.field and a.visit == b.visit and group[a.subject_id] == group[b.subject_id]


def test_inject_is_deterministic(table):
    c, group = table
    t1 = I.inject(c, group, 0.05, seed=9)[1]
    t2 = I.inject(c, group, 0.05, seed=9)[1]
    t3 = I.inject(c, group, 0.05, seed=10)[1]
    assert t1.equals(t2) and not t1.equals(t3)
