"""Read the raw demo tables and keep what the visit schedule needs."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def _read(raw: Path, rel: str, **kw) -> pd.DataFrame:
    return pd.read_csv(raw / f"{rel}.csv.gz", **kw)


def load_tables(raw: Path = C.RAW_DIR) -> dict[str, pd.DataFrame]:
    icu = _read(raw, "icu/icustays", parse_dates=["intime", "outtime"])
    patients = _read(raw, "hosp/patients")
    admissions = _read(raw, "hosp/admissions", parse_dates=["admittime"])
    diagnoses = _read(raw, "hosp/diagnoses_icd")

    lab = _read(raw, "hosp/labevents", usecols=["subject_id", "itemid", "charttime", "valuenum"],
                parse_dates=["charttime"])
    item2lab = {d["itemid"]: f for f, d in C.LAB_FIELDS.items()}
    lab = lab[lab.itemid.isin(item2lab) & lab.valuenum.notna()].assign(field=lambda d: d.itemid.map(item2lab))

    vital_items = ([C.HEART_RATE_ITEMID] + [i for src in C.BP_ITEMIDS.values() for i in src.values()]
                   + [i for ids in C.OTHER_VITAL_ITEMIDS.values() for i in ids] + C.WEIGHT_ITEMIDS)
    ce = _read(raw, "icu/chartevents", usecols=["subject_id", "itemid", "charttime", "valuenum"],
               parse_dates=["charttime"])
    ce = ce[ce.itemid.isin(vital_items) & ce.valuenum.notna()].drop_duplicates()
    f = ce.itemid == C.TEMP_F_ITEMID
    ce.loc[f, "valuenum"] = (ce.loc[f, "valuenum"] - 32) * 5 / 9

    omr = _read(raw, "hosp/omr", parse_dates=["chartdate"])
    omr = omr[omr.result_name.isin([C.OMR_BP, C.OMR_WEIGHT_LBS])]

    rx = _read(raw, "hosp/prescriptions", parse_dates=["starttime", "stoptime"],
               usecols=["subject_id", "drug", "route", "starttime", "stoptime", "dose_val_rx", "doses_per_24_hrs"])
    rx = rx[rx.starttime.notna()].copy()
    rx["stoptime"] = rx.stoptime.where(rx.stoptime >= rx.starttime, rx.starttime + pd.Timedelta("24h"))
    rx["dose"] = pd.to_numeric(rx.dose_val_rx, errors="coerce")
    rx["daily_dose"] = rx.dose * rx.doses_per_24_hrs
    return dict(icu=icu, patients=patients, admissions=admissions, diagnoses=diagnoses,
                lab=lab, chartevents=ce, omr=omr, prescriptions=rx)


def index_stays(icu: pd.DataFrame, patients: pd.DataFrame) -> pd.DataFrame:
    """First icu stay per patient, with age and sex."""
    idx = icu.sort_values("intime").groupby("subject_id", as_index=False).head(1)
    idx = idx.merge(patients[["subject_id", "gender", "anchor_age", "anchor_year"]], on="subject_id")
    idx["age"] = idx.anchor_age + (idx.intime.dt.year - idx.anchor_year)
    idx["female"] = idx.gender.eq("F").astype(int)
    return idx[["subject_id", "hadm_id", "stay_id", "intime", "outtime", "age", "female"]].reset_index(drop=True)


def diagnosis_flags(diagnoses: pd.DataFrame, stays: pd.DataFrame) -> pd.DataFrame:
    """Diagnosis group flags for the index admission."""
    dx = diagnoses[diagnoses.hadm_id.isin(stays.hadm_id)]
    code = dx.icd_code.astype(str).str.strip().str.upper()
    out = stays[["subject_id", "hadm_id"]].copy()
    for grp, by_version in C.ICD_GROUPS.items():
        hit = np.zeros(len(dx), bool)
        for version, prefixes in by_version.items():
            hit |= (dx.icd_version == version).to_numpy() & code.str.startswith(tuple(prefixes)).to_numpy()
        out[f"dx_{grp}"] = out.hadm_id.isin(dx.hadm_id[hit]).astype(int)
    return out.drop(columns="hadm_id")


def medication_classes(rx: pd.DataFrame) -> pd.DataFrame:
    """Order intervals per medication class."""
    rows = []
    for cls, pattern in C.MED_CLASSES.items():
        m = rx[rx.drug.str.contains(pattern, flags=re.I, regex=True, na=False)]
        rows.append(m[["subject_id", "starttime", "stoptime"]].assign(med_class=cls))
    return pd.concat(rows, ignore_index=True)
