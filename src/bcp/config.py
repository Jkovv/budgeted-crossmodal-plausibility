"""Settings, matching docs/analysis_plan.md.

edc   range used by the range rules
hard  impossible values, dropped before injection
dec   decimals as recorded
tf    model scale (log for skewed fields)
alt   alternative unit for unit errors: (factor or "c2f", decimals), None if there is none
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("BCP_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = ROOT / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
CELLS_DIR = RESULTS_DIR / "cells"          # row-level outputs, not committed

SEED = 20261021

# split
N_TRAIN = 50                               # rest are held out

# visit schedule
# label, day after icu admission, window
VISITS = [(f"D{k}", k, "12h") for k in range(1, 8)] + [(f"W{w}", 7 * w, "3d") for w in (2, 3, 4)]
VITALS_PAIR_WINDOW = "1h"                  # around the chosen heart rate

# fields
LAB_FIELDS = {
    "sodium":      dict(itemid=50983, label="Sodium",          unit="mmol/L", dec=0, tf="lin", edc=(115, 165), hard=(80, 200),   alt=None),
    "potassium":   dict(itemid=50971, label="Potassium",       unit="mmol/L", dec=1, tf="lin", edc=(2.5, 7.0), hard=(0.5, 15),   alt=None),
    "chloride":    dict(itemid=50902, label="Chloride",        unit="mmol/L", dec=0, tf="lin", edc=(75, 130),  hard=(40, 180),   alt=None),
    "bicarbonate": dict(itemid=50882, label="Bicarbonate",     unit="mmol/L", dec=0, tf="lin", edc=(8, 45),    hard=(1, 70),     alt=None),
    "bun":         dict(itemid=51006, label="Urea nitrogen",   unit="mg/dL",  dec=0, tf="log", edc=(2, 150),   hard=(0.5, 400),  alt=(0.357, 1)),
    "creatinine":  dict(itemid=50912, label="Creatinine",      unit="mg/dL",  dec=1, tf="log", edc=(0.2, 12),  hard=(0.05, 40),  alt=(88.42, 0)),
    "glucose":     dict(itemid=50931, label="Glucose",         unit="mg/dL",  dec=0, tf="log", edc=(40, 600),  hard=(5, 3000),   alt=(1 / 18.016, 1)),
    "calcium":     dict(itemid=50893, label="Calcium",         unit="mg/dL",  dec=1, tf="lin", edc=(5, 14),    hard=(1, 25),     alt=(0.2495, 2)),
    "magnesium":   dict(itemid=50960, label="Magnesium",       unit="mg/dL",  dec=1, tf="lin", edc=(0.8, 5),   hard=(0.2, 15),   alt=(0.4114, 2)),
    "phosphate":   dict(itemid=50970, label="Phosphate",       unit="mg/dL",  dec=1, tf="log", edc=(0.8, 10),  hard=(0.1, 25),   alt=(0.3229, 2)),
    "hemoglobin":  dict(itemid=51222, label="Hemoglobin",      unit="g/dL",   dec=1, tf="lin", edc=(5, 20),    hard=(1, 30),     alt=(10, 0)),
    "hematocrit":  dict(itemid=51221, label="Hematocrit",      unit="%",      dec=1, tf="lin", edc=(15, 60),   hard=(3, 80),     alt=(0.01, 2)),
    "wbc":         dict(itemid=51301, label="White blood cells", unit="K/uL", dec=1, tf="log", edc=(0.5, 50),  hard=(0.01, 500), alt=None),
    "platelets":   dict(itemid=51265, label="Platelets",       unit="K/uL",   dec=0, tf="log", edc=(10, 1000), hard=(1, 3000),   alt=None),
}

VITAL_FIELDS = {
    "heart_rate":  dict(label="Heart rate",       unit="bpm",  dec=0, tf="lin", edc=(30, 200), hard=(1, 300),  alt=None),
    "sbp":         dict(label="Systolic BP",      unit="mmHg", dec=0, tf="lin", edc=(60, 230), hard=(20, 300), alt=None),
    "dbp":         dict(label="Diastolic BP",     unit="mmHg", dec=0, tf="lin", edc=(25, 140), hard=(5, 250),  alt=None),
    "map":         dict(label="Mean arterial pressure", unit="mmHg", dec=0, tf="lin", edc=(40, 160), hard=(10, 250), alt=None),
    "resp_rate":   dict(label="Respiratory rate", unit="/min", dec=0, tf="lin", edc=(6, 45),   hard=(1, 90),   alt=None),
    "spo2":        dict(label="SpO2",             unit="%",    dec=0, tf="lin", edc=(70, 100), hard=(10, 100), alt=None),
    "temperature": dict(label="Temperature",      unit="C",    dec=1, tf="lin", edc=(34, 41),  hard=(25, 45),  alt=("c2f", 1)),
    "weight":      dict(label="Weight",           unit="kg",   dec=1, tf="lin", edc=(30, 250), hard=(20, 400), alt=(2.20462, 1)),
}
HEART_RATE_ITEMID = 220045
BP_ITEMIDS = {"nibp": {"sbp": 220179, "dbp": 220180, "map": 220181},
              "art": {"sbp": 220050, "dbp": 220051, "map": 220052}}
OTHER_VITAL_ITEMIDS = {"resp_rate": [220210, 224690], "spo2": [220277], "temperature": [223762, 223761]}
TEMP_F_ITEMID = 223761
WEIGHT_ITEMIDS = [224639, 226512]           # daily, admission weight (kg)
OMR_BP, OMR_WEIGHT_LBS = "Blood Pressure", "Weight (Lbs)"

DOSE_FIELDS = {
    # regex on prescriptions.drug, route filter
    "heparin_sc":  dict(label="Heparin (SC) daily dose",    unit="units/day", pattern=r"^heparin$", route="SC", dec=0, edc=(2500, 22500), alt=None),
    "metoprolol":  dict(label="Metoprolol daily dose",      unit="mg/day", pattern=r"^metoprolol tartrate$", route=None, dec=2, edc=(1.25, 450), alt=(0.001, 4)),
    "furosemide":  dict(label="Furosemide daily dose",      unit="mg/day", pattern=r"^furosemide$", route=None, dec=0, edc=(5, 600), alt=(0.001, 3)),
    "aspirin":     dict(label="Aspirin daily dose",         unit="mg/day", pattern=r"^aspirin$", route=None, dec=0, edc=(40, 1300), alt=(0.001, 3)),
    "famotidine":  dict(label="Famotidine daily dose",      unit="mg/day", pattern=r"^famotidine$", route=None, dec=0, edc=(10, 80), alt=(0.001, 3)),
    "vancomycin":  dict(label="Vancomycin (IV) daily dose", unit="mg/day", pattern=r"^vancomycin$", route="IV", dec=0, edc=(250, 5000), alt=(0.001, 3)),
}
for d in DOSE_FIELDS.values():
    d.update(tf="log", hard=(1e-6, 1e9))

DATE_FIELDS = {"lab_date": dict(label="Laboratory sample date", form="lab"),
               "vital_date": dict(label="Vital signs date", form="vital")}

VALUE_FIELDS = {**LAB_FIELDS, **VITAL_FIELDS, **DOSE_FIELDS}
FIELD_MODALITY = {**{f: "lab" for f in LAB_FIELDS}, **{f: "vital" for f in VITAL_FIELDS},
                  **{f: "med" for f in DOSE_FIELDS}, **{f: "date" for f in DATE_FIELDS}}

# context only
MED_CLASSES = {
    "anti_infective": r"vancomycin|cef|ceph|penicillin|piperacillin|ampicillin|amoxicillin|nafcillin|meropenem|"
                      r"ertapenem|aztreonam|floxacin|metronidazole|clindamycin|azithromycin|doxycycline|linezolid|"
                      r"daptomycin|gentamicin|tobramycin|sulfameth|trimethoprim|nitrofurantoin|fluconazole|"
                      r"micafungin|voriconazole|acyclovir|ganciclovir|oseltamivir",
    "vasopressor": r"norepinephrine|phenylephrine|vasopressin|epinephrine|dopamine|dobutamine|milrinone",
    "insulin": r"insulin",
    "loop_diuretic": r"furosemide|torsemide|bumetanide",
    "potassium_suppl": r"potassium chloride|potassium phosphate|potassium citrate",
    "anticoagulant": r"^(?!.*(?:flush|dwell)).*(?:heparin|enoxaparin|warfarin|argatroban|bivalirudin|apixaban|rivaroxaban)",
    "steroid": r"hydrocortisone|methylprednisolone|prednisone|prednisolone|dexamethasone",
    "sedative": r"propofol|midazolam|dexmedetomidine|lorazepam|fentanyl",
    "iv_fluid": r"^(?!.*flush).*(?:sodium chloride 0\.9|0\.9% sodium chloride|lactated ringer|5% dextrose|dextrose 5%)",
}

ICD_GROUPS = {  # code prefixes per icd version
    "infection": {9: ["00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13",
                      "320", "321", "322", "421", "46", "480", "481", "482", "483", "484", "485", "486", "487",
                      "488", "590", "5990", "680", "681", "682", "686", "730", "7907", "99591", "99592"],
                  10: ["A", "B", "G00", "G01", "G02", "G03", "I33", "J09", "J10", "J11", "J12", "J13", "J14",
                       "J15", "J16", "J17", "J18", "J20", "J21", "J22", "K65", "L02", "L03", "M86", "N10", "N390",
                       "R652", "T814"]},
    "ckd": {9: ["585"], 10: ["N18"]},
    "esrd_dialysis": {9: ["5856", "V4511", "V56"], 10: ["N186", "Z992", "Z49"]},
    "aki": {9: ["584"], 10: ["N17"]},
    "diabetes": {9: ["249", "250"], 10: ["E08", "E09", "E10", "E11", "E13"]},
    "heart_failure": {9: ["428"], 10: ["I50", "I110", "I130", "I132"]},
    "liver_disease": {9: ["570", "571", "572", "573"], 10: ["K70", "K71", "K72", "K73", "K74", "K75", "K76", "K77"]},
    "anemia": {9: ["280", "281", "282", "283", "284", "285"], 10: ["D50", "D51", "D52", "D53", "D55", "D56",
                                                                  "D57", "D58", "D59", "D60", "D61", "D62", "D63", "D64"]},
    "malignancy": {9: ["14", "15", "16", "17", "18", "19", "20"], 10: ["C"]},
    "resp_failure": {9: ["51881", "51882", "51884"], 10: ["J96"]},
    "electrolyte_dx": {9: ["276"], 10: ["E86", "E87"]},
    "coagulopathy": {9: ["286", "2871", "2873", "2874", "2875"], 10: ["D65", "D66", "D67", "D68", "D69"]},
}

# error injection
ERROR_TYPES = ["wrong_date", "patient_swap", "copy_previous", "unit_error", "decimal_slip", "digit_transposition"]
ERROR_RATE = 0.02
SENSITIVITY_RATES = (0.005, 0.05)
N_REPLICATES = 20
N_REPLICATES_SECONDARY = 10                # ablation, sensitivity

# budgets and statistics
BUDGETS = (0.05, 0.10, 0.25, 0.50, 1.00)   # queries per patient per visit
PRIMARY_BUDGET = 0.25
N_BOOTSTRAP = 2000
N_PERMUTATIONS = 10000
SIZE_BINS = (0.5, 2.0)                     # robust sd units
DATE_SIZE_BIN = 7                          # days

# plausibility model
N_FOLDS = 5
Z_CONFIRM = 4.0
MAX_ROUNDS = 30
MIN_TRAIN_CELLS = 30
MU_PARAMS = dict(objective="huber", alpha=1.0, n_estimators=200, learning_rate=0.05, num_leaves=15,
                 min_child_samples=10, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                 reg_lambda=1.0, verbose=-1, n_jobs=4)
SIGMA_PARAMS = dict(objective="l1", n_estimators=150, learning_rate=0.05, num_leaves=7, min_child_samples=20,
                    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, n_jobs=4)
ABLATIONS = ["cross_modal_only", "own_history_only", "no_labs", "no_vitals", "no_meds", "no_dates", "no_baseline"]

# secondary analyses
N_SITES = 5
FDR_TARGETS = (0.10, 0.20)
II_MIN_VISITS = 3
II_MIN_SWAPS = 20
II_GAIN = 0.05
