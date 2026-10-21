# Data

No data is committed to this repository. `download_mimic_demo.py` fetches the
ten tables used here from PhysioNet into `data/raw/` (or `$BCP_DATA_DIR/raw/`)
and checks each against the SHA-256 that PhysioNet publishes for version 2.2:

| File | Used for |
|---|---|
| `hosp/patients.csv.gz` | age, sex |
| `hosp/admissions.csv.gz` | index admission |
| `hosp/diagnoses_icd.csv.gz` | diagnosis groups (context) |
| `hosp/labevents.csv.gz`, `hosp/d_labitems.csv.gz` | laboratory form |
| `hosp/omr.csv.gz` | outpatient blood pressure and weight at the weekly visits |
| `hosp/prescriptions.csv.gz` | concomitant medication doses and medication classes |
| `icu/icustays.csv.gz` | index ICU stay, day 0 of the visit schedule |
| `icu/chartevents.csv.gz`, `icu/d_items.csv.gz` | vital signs form during the ICU stay |

Source: MIMIC-IV Clinical Database Demo, version 2.2, PhysioNet,
https://doi.org/10.13026/dp1f-ex47. The demo is open access under the Open Data
Commons Open Database License v1.0 (ODbL); a copy of the license is downloaded
to `data/raw/LICENSE.txt`. Dates in MIMIC are shifted into the future for
de-identification.

Processed tables are written to `data/processed/` and row-level detector
outputs to `results/cells/`; neither is committed. Only aggregate tables and
figures in `results/` are.
