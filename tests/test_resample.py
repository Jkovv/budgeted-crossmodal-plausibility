import pandas as pd
import pytest

from bcp import config as C
from bcp import resample as R

T0 = pd.Timestamp("2150-01-01 10:00")


@pytest.fixture
def visits():
    stays = pd.DataFrame({"subject_id": [1], "intime": [T0]})
    return R.nominal_visits(stays, visits=[("D1", 1, "12h"), ("W2", 14, "3d")])


def test_windows(visits):
    d1, w2 = visits.iloc[0], visits.iloc[1]
    assert d1.win_start == T0 + pd.Timedelta("12h") and d1.win_end == T0 + pd.Timedelta("36h")
    assert w2.win_start == pd.Timestamp("2150-01-12") and w2.win_end == pd.Timestamp("2150-01-19")
    assert d1.window_days == 1 and w2.window_days == 3
    assert d1.nominal_date == R.day_number(pd.Series([T0 + pd.Timedelta(days=1)])).iloc[0]


def test_lab_draw_with_most_analytes_wins_then_closest(visits):
    nominal = T0 + pd.Timedelta(days=1)
    lab = pd.DataFrame({
        "subject_id": 1,
        "charttime": [nominal, nominal + pd.Timedelta("2h"), nominal + pd.Timedelta("2h"), nominal + pd.Timedelta("20h")],
        "field": ["sodium", "sodium", "potassium", "sodium"],
        "valuenum": [140.0, 141.0, 4.0, 150.0],
    })
    out = R.lab_form(lab, visits)
    assert set(out.field) == {"sodium", "potassium"}                    # the two-analyte draw, not the closer one
    assert out.loc[out.field == "sodium", "value"].item() == 141.0
    assert (out.form_time == nominal + pd.Timedelta("2h")).all()
    lab2 = lab.iloc[[0, 1]].assign(field="sodium")                        # same count: closest draw wins
    assert R.lab_form(lab2, visits).value.item() == 140.0


def test_vitals_pair_within_window_and_prefer_cuff(visits):
    t = T0 + pd.Timedelta(days=1)
    ce = pd.DataFrame({
        "subject_id": 1,
        "itemid": [C.HEART_RATE_ITEMID, C.BP_ITEMIDS["nibp"]["sbp"], C.BP_ITEMIDS["art"]["sbp"],
                   C.BP_ITEMIDS["nibp"]["dbp"], 220210, 220277],
        "charttime": [t, t + pd.Timedelta("30min"), t, t + pd.Timedelta("30min"), t + pd.Timedelta("3h"), t],
        "valuenum": [80.0, 120.0, 135.0, 70.0, 18.0, 97.0],
    })
    out = R.vital_form(ce, pd.DataFrame(columns=["subject_id", "chartdate", "result_name", "result_value"]), visits)
    got = dict(zip(out.field, out.value))
    assert got["heart_rate"] == 80 and got["sbp"] == 120 and got["dbp"] == 70   # cuff, not arterial line
    assert "resp_rate" not in got                                               # 3 h away: outside +/- 1 h
    assert got["spo2"] == 97


def test_weekly_visit_falls_back_to_outpatient_records(visits):
    omr = pd.DataFrame({"subject_id": 1, "chartdate": pd.to_datetime(["2150-01-16", "2150-01-16", "2150-01-12"]),
                        "result_name": [C.OMR_BP, C.OMR_WEIGHT_LBS, C.OMR_BP],
                        "result_value": ["128/76", "176.4", "150/90"]})
    out = R.vital_form(pd.DataFrame(columns=["subject_id", "itemid", "charttime", "valuenum"]), omr, visits)
    got = dict(zip(out.field, out.value))
    assert got["sbp"] == 128 and got["dbp"] == 76                    # date closest to the nominal date (Jan 15)
    assert got["weight"] == pytest.approx(176.4 / 2.20462)


def test_dose_uses_most_recent_active_order(visits):
    t = T0 + pd.Timedelta(days=1)
    rx = pd.DataFrame({"subject_id": 1, "drug": ["Furosemide", "Furosemide", "Furosemide"], "route": "IV",
                       "starttime": [t - pd.Timedelta("2d"), t - pd.Timedelta("1h"), t + pd.Timedelta("1h")],
                       "stoptime": [t + pd.Timedelta("2d")] * 3, "daily_dose": [40.0, 80.0, 120.0]})
    out = R.dose_form(rx, visits)
    assert out.loc[(out.field == "furosemide") & (out.visit == "D1"), "value"].item() == 80.0


def test_round_and_clean_drops_impossible_values():
    report = {}
    v = pd.DataFrame({"field": ["potassium", "potassium", "heart_rate"], "value": [4.06, 20.0, 0.0]})
    out = R.round_and_clean(v, report)
    assert out.value.tolist() == [4.1]
    assert report["artefacts_removed"] == {"heart_rate": 1, "potassium": 1}
