import pandas as pd
import pytest

from bcp import explain as X


def _row(**kw):
    base = dict(field="potassium", value=4.6, visit="D3", nominal_date=1000, window_days=1)
    return pd.Series({**base, **kw})


def test_written_values_keep_their_decimals():
    assert X.fmt("potassium", 4.6) == "4.6"
    assert X.fmt("vancomycin", 0.04) == "0.04"          # mg dose written in grams
    assert X.fmt("heart_rate", 9.8) == "9.8"            # decimal slip on an integer field
    assert X.fmt("platelets", 1050) == "1,050"


def test_rule_queries():
    assert X.rule_text(_row(value=45.0), 1000, 1, None) == (
        "Potassium 45.0 mmol/L at visit D3 is outside the expected range 2.5 to 7.0 mmol/L. "
        "Please check against the source document.")
    d = X.rule_text(_row(field="lab_date", value=1365), 1000, 1, None)
    assert "365 days after the scheduled date (window 1 day)" in d


def test_model_queries_state_evidence_and_never_a_value_to_use():
    text = X.model_text(_row(value=6.4), ["potassium 4.1 mmol/L 1 day earlier", "creatinine 0.9 mg/dL at the same visit"])
    assert text.startswith("Potassium 6.4 mmol/L at visit D3 does not fit the rest of the record:")
    assert text.endswith(X.ASK)
    for word in ("should", "expected value", "correct", "replace", "probably"):
        assert word not in text.lower()


def test_model_query_mentions_the_range_when_it_is_broken():
    text = X.model_text(_row(value=46.0), ["potassium 4.6 mmol/L 1 day earlier"])
    assert "outside the expected range 2.5 to 7.0 mmol/L and does not fit" in text
    assert X.model_text(_row(value=46.0), []) == (
        "Potassium 46.0 mmol/L at visit D3 is outside the expected range 2.5 to 7.0 mmol/L. "
        "Please check against the source document.")
    assert "is unusual for this patient's record" in X.model_text(_row(value=5.0), [])


@pytest.mark.parametrize("n,expected", [(1, "1 day"), (2, "2 days"), (0, "0 days")])
def test_days(n, expected):
    assert X._days(n) == expected
