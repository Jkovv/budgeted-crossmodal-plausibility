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
