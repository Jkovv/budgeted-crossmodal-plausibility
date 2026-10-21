"""Resample the ICU data to a clinical trial visit schedule and build the table of cells.

A *cell* is one recorded value of one field at one visit of one patient, or the date of
the laboratory or vital signs form of a visit. Dates are stored as day numbers (days
since 1970-01-01) so that every cell has a numeric value.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import config as C
from .load import diagnosis_flags, index_stays, medication_classes

EPOCH = pd.Timestamp("1970-01-01")


def day_number(ts: pd.Series) -> pd.Series:
    return (pd.to_datetime(ts).dt.normalize() - EPOCH).dt.days


def nominal_visits(stays: pd.DataFrame, visits=C.VISITS) -> pd.DataFrame:
    """One row per patient and scheduled visit, with its nominal time and window."""
    rows = []
    for idx, (label, day, window) in enumerate(visits):
        t = stays.intime + pd.Timedelta(days=day)
        date = t.dt.normalize()
        if window.endswith("h"):
            half = pd.Timedelta(window)
            start, end, win_days = t - half, t + half, 1
        else:
            k = int(window[:-1])
            start, end, win_days = date - pd.Timedelta(days=k), date + pd.Timedelta(days=k + 1), k
        rows.append(pd.DataFrame({"subject_id": stays.subject_id, "visit": label, "visit_idx": idx, "day": day,
                                  "nominal_time": t, "nominal_date": day_number(t), "win_start": start,
                                  "win_end": end, "window_days": win_days}))
    return pd.concat(rows, ignore_index=True)


def _in_window(events: pd.DataFrame, visits: pd.DataFrame, time_col: str) -> pd.DataFrame:
    m = events.merge(visits, on="subject_id")
    m = m[(m[time_col] >= m.win_start) & (m[time_col] < m.win_end)].copy()
    m["dist"] = (m[time_col] - m.nominal_time).abs()
    return m


def lab_form(lab: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """One blood draw per visit: the draw with the most analytes, then the one closest to the nominal time."""
    m = _in_window(lab, visits, "charttime")
    draws = (m.groupby(["subject_id", "visit", "charttime"])
             .agg(n=("field", "nunique"), dist=("dist", "first")).reset_index()
             .sort_values(["subject_id", "visit", "n", "dist"], ascending=[True, True, False, True]))
    best = draws.groupby(["subject_id", "visit"], as_index=False).head(1)[["subject_id", "visit", "charttime"]]
    vals = m.merge(best, on=["subject_id", "visit", "charttime"])
    vals = vals.groupby(["subject_id", "visit", "field", "charttime"], as_index=False).valuenum.mean()
    return vals.rename(columns={"valuenum": "value", "charttime": "form_time"})


def _closest(events: pd.DataFrame, anchors: pd.DataFrame, window: pd.Timedelta, out_field: str) -> pd.DataFrame:
    """For each anchor (subject, visit, anchor_time), the event closest in time within +/- window."""
    m = events.merge(anchors, on="subject_id")
    m["d"] = (m.charttime - m.anchor_time).abs()
    m = m[m.d <= window].sort_values("d")
    m = m.groupby(["subject_id", "visit"], as_index=False).head(1)
    return m[["subject_id", "visit", "valuenum"]].rename(columns={"valuenum": "value"}).assign(field=out_field)


def vital_form(ce: pd.DataFrame, omr: pd.DataFrame, visits: pd.DataFrame,
               pair_window: str = C.VITALS_PAIR_WINDOW) -> pd.DataFrame:
    """ICU vital signs around the heart-rate charting closest to the nominal time; outpatient
    blood pressure and weight at weekly visits without ICU vital signs."""
    win = pd.Timedelta(pair_window)
    ce = ce.assign(charttime=pd.to_datetime(ce.charttime), valuenum=ce.valuenum.astype(float))
    omr = omr.assign(chartdate=pd.to_datetime(omr.chartdate))
    hr = _in_window(ce[ce.itemid == C.HEART_RATE_ITEMID], visits, "charttime").sort_values("dist")
    hr = hr.groupby(["subject_id", "visit"], as_index=False).head(1)
    anchors = hr[["subject_id", "visit", "charttime"]].rename(columns={"charttime": "anchor_time"})
    parts = [hr[["subject_id", "visit", "valuenum"]].rename(columns={"valuenum": "value"}).assign(field="heart_rate")]

    # blood pressure: all three components from the cuff if it was charted near the anchor, else the arterial line
    nibp = _closest(ce[ce.itemid == C.BP_ITEMIDS["nibp"]["sbp"]], anchors, win, "sbp")
    has_nibp = set(zip(nibp.subject_id, nibp.visit))
    use_nibp = np.array([(s, v) in has_nibp for s, v in zip(anchors.subject_id, anchors.visit)], bool)
    for src, mask in (("nibp", use_nibp), ("art", ~use_nibp)):
        for comp, item in C.BP_ITEMIDS[src].items():
            parts.append(_closest(ce[ce.itemid == item], anchors[mask], win, comp))
    for fld, items in C.OTHER_VITAL_ITEMIDS.items():
        parts.append(_closest(ce[ce.itemid.isin(items)], anchors, win, fld))
    icu = pd.concat(parts, ignore_index=True).merge(anchors, on=["subject_id", "visit"])
    icu = icu.rename(columns={"anchor_time": "form_time"})

    # weight anywhere in the visit window
    w = _in_window(ce[ce.itemid.isin(C.WEIGHT_ITEMIDS)], visits, "charttime").sort_values("dist")
    w = w.groupby(["subject_id", "visit"], as_index=False).head(1)
    w = w[["subject_id", "visit", "valuenum"]].rename(columns={"valuenum": "value"}).assign(field="weight")
    icu_weight = w.merge(anchors.rename(columns={"anchor_time": "form_time"}), on=["subject_id", "visit"])

    # outpatient records for weekly visits with no ICU vital signs
    weekly = visits[(visits.window_days > 1) & ~visits.set_index(["subject_id", "visit"]).index.isin(
        anchors.set_index(["subject_id", "visit"]).index)]
    o = _in_window(omr.rename(columns={"chartdate": "charttime"}), weekly, "charttime")
    o = o[o.result_name.isin([C.OMR_BP, C.OMR_WEIGHT_LBS])].sort_values(["dist", "charttime"])
    day_pick = o.groupby(["subject_id", "visit"], as_index=False).head(1)[["subject_id", "visit", "charttime"]]
    o = o.merge(day_pick, on=["subject_id", "visit", "charttime"]).drop_duplicates(["subject_id", "visit", "result_name"])
    rows = []
    for r in o.itertuples():
        if r.result_name == C.OMR_BP:
            m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(r.result_value))
            if m:
                rows += [(r.subject_id, r.visit, "sbp", float(m.group(1)), r.charttime),
                         (r.subject_id, r.visit, "dbp", float(m.group(2)), r.charttime)]
        else:
            v = pd.to_numeric(r.result_value, errors="coerce")
            if pd.notna(v):
                rows.append((r.subject_id, r.visit, "weight", float(v) / 2.20462, r.charttime))
    out_omr = pd.DataFrame(rows, columns=["subject_id", "visit", "field", "value", "form_time"])
    keep = ["subject_id", "visit", "field", "value", "form_time"]
    parts = [p[keep] for p in (icu, icu_weight, out_omr) if len(p)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=keep)


def dose_form(rx: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """Daily dose of each tracked drug from the most recently started order active at the nominal time."""
    out = []
    for fld, d in C.DOSE_FIELDS.items():
        m = rx[rx.drug.str.strip().str.contains(d["pattern"], flags=re.I, regex=True, na=False) & rx.daily_dose.gt(0)]
        if d["route"]:
            m = m[m.route.eq(d["route"])]
        m = m.merge(visits[["subject_id", "visit", "nominal_time"]], on="subject_id")
        m = m[(m.starttime <= m.nominal_time) & (m.stoptime >= m.nominal_time)]
        m = m.sort_values("starttime").groupby(["subject_id", "visit"], as_index=False).tail(1)
        out.append(m[["subject_id", "visit", "daily_dose"]].rename(columns={"daily_dose": "value"}).assign(field=fld))
    return pd.concat(out, ignore_index=True).assign(form_time=pd.NaT)


def visit_medication_classes(classes: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """Which medication classes have an order active at each nominal visit time (context only)."""
    m = classes.merge(visits[["subject_id", "visit", "nominal_time"]], on="subject_id")
    m = m[(m.starttime <= m.nominal_time) & (m.stoptime >= m.nominal_time)]
    act = m.drop_duplicates(["subject_id", "visit", "med_class"]).assign(on=1)
    wide = act.pivot_table(index=["subject_id", "visit"], columns="med_class", values="on", fill_value=0)
    wide = wide.reindex(columns=list(C.MED_CLASSES), fill_value=0).add_prefix("med_")
    base = visits[["subject_id", "visit"]].set_index(["subject_id", "visit"])
    return base.join(wide).fillna(0).astype(int).reset_index()


def round_and_clean(values: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Round to the decimals a site would write and drop physiologically impossible values."""
    spec = C.VALUE_FIELDS
    dec = values.field.map({f: d["dec"] for f, d in spec.items()})
    values = values.assign(value=[round(v, int(k)) for v, k in zip(values.value, dec)])
    lo = values.field.map({f: d["hard"][0] for f, d in spec.items()})
    hi = values.field.map({f: d["hard"][1] for f, d in spec.items()})
    bad = ~values.value.between(lo, hi) | (values.value <= 0)
    report["artefacts_removed"] = values[bad].groupby("field").size().to_dict()
    return values[~bad]


def build(tables: dict) -> dict[str, pd.DataFrame]:
    report: dict = {}
    stays = index_stays(tables["icu"], tables["patients"])
    visits = nominal_visits(stays)
    lab = lab_form(tables["lab"], visits).assign(form="lab")
    vit = vital_form(tables["chartevents"], tables["omr"], visits).assign(form="vital")
    dose = dose_form(tables["prescriptions"], visits).assign(form="med")
    values = round_and_clean(pd.concat([lab, vit, dose], ignore_index=True), report)

    forms = values[values.form.isin(["lab", "vital"])].groupby(["subject_id", "visit", "form"], as_index=False).form_time.first()
    dates = forms.assign(field=forms.form.map({"lab": "lab_date", "vital": "vital_date"}),
                         value=day_number(forms.form_time).astype(float), form="date")
    cells = pd.concat([values, dates], ignore_index=True)
    vmeta = visits[["subject_id", "visit", "visit_idx", "day", "nominal_date", "window_days"]]
    cells = cells.merge(vmeta, on=["subject_id", "visit"])
    cells["modality"] = cells.field.map(C.FIELD_MODALITY)
    cells = cells.sort_values(["subject_id", "visit_idx", "modality", "field"]).reset_index(drop=True)
    cells.insert(0, "cell_id", np.arange(len(cells)))
    cells = cells[["cell_id", "subject_id", "visit", "visit_idx", "day", "nominal_date", "window_days",
                   "modality", "field", "value"]]

    present = cells[["subject_id", "visit"]].drop_duplicates()
    visits = visits.merge(present, on=["subject_id", "visit"])[
        ["subject_id", "visit", "visit_idx", "day", "nominal_time", "nominal_date", "window_days"]]
    baseline = stays[["subject_id", "age", "female"]].merge(diagnosis_flags(tables["diagnoses"], stays), on="subject_id")
    visit_ctx = visit_medication_classes(medication_classes(tables["prescriptions"]), visits)

    report.update(patients=int(cells.subject_id.nunique()), patient_visits=int(len(visits)), cells=int(len(cells)),
                  cells_by_modality=cells.modality.value_counts().to_dict(),
                  cells_by_field=cells.field.value_counts().to_dict(),
                  patient_visits_by_visit=visits.visit.value_counts().reindex([v[0] for v in C.VISITS]).fillna(0).astype(int).to_dict())
    return dict(cells=cells, visits=visits, baseline=baseline, visit_context=visit_ctx, report=report)
