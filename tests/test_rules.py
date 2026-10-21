import numpy as np
import pandas as pd
import pytest

from bcp import rules


def _cells(rows):
    base = dict(subject_id=1, visit="D1", visit_idx=0, nominal_date=1000, window_days=1, modality="lab")
    return pd.DataFrame([{**base, **r} for r in rows])


def test_values_inside_the_range_score_zero():
    c = _cells([dict(field="potassium", value=4.1), dict(field="sodium", value=115)])
    assert rules.range_scores(c).tolist() == [0.0, 0.0]


def test_severity_is_distance_over_range_width():
    c = _cells([dict(field="potassium", value=7.9), dict(field="potassium", value=0.25)])
    width = 7.0 - 2.5
    assert rules.range_scores(c) == pytest.approx([0.9 / width, 2.25 / width])


def test_dates_outside_the_window_are_flagged():
    c = _cells([dict(field="lab_date", modality="date", value=1001),          # inside +/- 1 day
                dict(field="lab_date", modality="date", value=1003, visit="D2", visit_idx=1),
                dict(field="lab_date", modality="date", value=1000 + 365, visit="W2", visit_idx=7,
                     nominal_date=1013, window_days=3)])
    c.loc[1, "nominal_date"] = 1001
    s = rules.range_scores(c)
    assert s[0] == 0
    assert s[1] == pytest.approx(1.0)                                          # 2 days off, window 1
    assert s[2] == pytest.approx((352 - 3) / 3)


def test_date_before_the_previous_visit_is_flagged():
    c = _cells([dict(field="vital_date", modality="date", value=1002, visit="D1", visit_idx=0, nominal_date=1001),
                dict(field="vital_date", modality="date", value=1001, visit="D2", visit_idx=1, nominal_date=1002)])
    s = rules.range_scores(c)
    assert s[0] == 0 and s[1] == pytest.approx(1.0)                           # inside its window but before D1


def test_rules_never_change_the_data():
    c = _cells([dict(field="potassium", value=9.0)])
    before = c.copy()
    rules.RangeRules().fit(c).score(c)
    assert c.equals(before)
