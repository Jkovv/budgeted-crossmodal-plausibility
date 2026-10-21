# Analysis plan: budgeted cross-modal plausibility checks

Written and committed before any detector was run on the resampled data. The
numeric settings are mirrored in `src/bcp/config.py`. Any change made after
results were seen is listed under *Deviations* at the end, with the reason.

## What was known before this plan

* An earlier proof of concept by the same author used the same MIMIC-IV demo
  data with a different design (hourly ICU values, 5% injected errors including
  non-transcription types, no held-out patients, no query budget). Its results
  are known to the author and informed two hypotheses below (that cross-modal
  context matters for patient swaps, and the index of individuality). None of
  its numbers are reused.
* For this plan, only availability counts were computed on the visit schedule
  (patients with any laboratory value, vital sign or medication order in each
  visit window). No detector was run and no error was injected.

| Visit | Day | Window | Patients with labs | with ICU vital signs | with outpatient BP or weight |
|---|---:|---|---:|---:|---:|
| D1-D7 | 1-7 | +/- 12 h | 92, 89, 79, 70, 53, 48, 40 | 97, 61, 46, 37, 30, 18, 17 | 0-1 |
| W2, W3, W4 | 14, 21, 28 | +/- 3 days | 26, 14, 11 | 12, 5, 3 | 17, 14, 11 |

## Question

**Primary.** At a fixed query budget of 0.25 queries per patient per visit,
does a cross-modal plausibility model catch more injected transcription errors
than EDC-style range rules, on held-out patients?

Secondary: the same comparison at other budgets; recall by error type; how much
each modality contributes; a delta-check baseline and a combined detector;
false-query control with conformal p-values; and the index-of-individuality
hypothesis.

## Data

* **Source.** MIMIC-IV Clinical Database Demo v2.2 (100 patients, ODbL),
  tables `patients`, `admissions`, `icustays`, `labevents`, `d_labitems`,
  `chartevents`, `d_items`, `omr`, `prescriptions`, `diagnoses_icd`. Files are
  checked against the published SHA-256 sums.
* **Cohort.** Every patient with an ICU stay. The index stay is the first ICU
  stay; day 0 is its admission time (`intime`).
* **Visit schedule.** Daily visits D1 to D7 at `intime` + k days (k = 1..7),
  window +/- 12 hours. Weekly visits W2, W3, W4 at `intime` + 14, 21 and 28
  days, window +/- 3 calendar days around the nominal date. A visit exists for
  a patient if any of its forms has a value.
* **Laboratory form.** One blood draw per visit: among the draws (`labevents`
  charttime, inpatient or outpatient) in the window, the one with the most of
  the 14 analytes, ties broken by closeness to the nominal time. All analytes
  come from that draw; an analyte not measured in it is missing. Fields: sodium,
  potassium, chloride, bicarbonate, urea nitrogen, creatinine, glucose, calcium,
  magnesium, phosphate, hemoglobin, hematocrit, white blood cells, platelets.
  The form date is the calendar date of the draw.
* **Vital signs form.** ICU (`chartevents`): the charting time with a heart
  rate closest to the nominal time in the window; the other vital signs are
  taken within +/- 1 hour of it. Blood pressure from the non-invasive cuff when
  charted, otherwise the arterial line, all three components from the same
  source. Temperature in degrees Celsius (Fahrenheit converted). Weight from
  daily or admission weight in the window. After ICU discharge, outpatient
  records (`omr`): blood pressure (systolic and diastolic) and weight (pounds
  converted to kilograms) on the date closest to the nominal date in the window;
  the other vital signs are missing. Fields: heart rate, systolic, diastolic and
  mean arterial pressure, respiratory rate, SpO2, temperature, weight. The form
  date is the calendar date of the charting time or `omr` date.
* **Concomitant medications form.** For each of six drugs, the total daily dose
  (`dose_val_rx` x `doses_per_24_hrs`) of an order active at the nominal visit
  time: heparin (subcutaneous, units), metoprolol tartrate, furosemide,
  aspirin, famotidine, vancomycin (intravenous) (all mg). No date cell.
* **Context only, never checked.** Age, sex, 12 ICD diagnosis groups of the
  index admission (infection, CKD, ESRD or dialysis, AKI, diabetes, heart
  failure, liver disease, anemia, malignancy, respiratory failure, electrolyte
  disorder, coagulopathy) and medication classes active at the nominal time
  (anti-infective, vasopressor, insulin, loop diuretic, potassium supplement,
  anticoagulant, corticosteroid, sedative, IV fluid).
* **Cells.** One recorded value of one field at one visit of one patient, plus
  one date cell per laboratory form and per vital signs form.
* **Recorded precision.** Each field is rounded to the decimals a site would
  write (for example one decimal for potassium and creatinine, none for
  sodium, as set in `config.py`) before anything else, so injected errors act
  on realistic entries.
* **Pre-existing artefacts.** Values outside physiologically possible limits
  (hard limits in `config.py`, for example heart rate 0) are set to missing
  before injection and counted.

## Split

Patients are split at random (fixed seed) into **50 training** and **50
held-out** patients. **All reported results are on held-out patients.**
Training patients are used to fit the plausibility model, to estimate the
index of individuality, as the conformal calibration set and for any check
made while writing the code. No setting is tuned on held-out patients.

## Error injection

* Applied to all patients, training and held-out alike, so the model is trained
  on data that contains errors, as it would be in practice. A new injection is
  drawn for each replicate.
* **Error rate.** 2% of all cells in the primary analysis. This sits between
  EDC entry without chart abstraction (14.3 errors per 10,000 fields, Nahm et
  al. 2008; 0.29% single data entry, Garza et al. 2025) and chart abstraction
  (6.57%, Garza et al. 2025; 5.6% before source data verification, van den Bor
  et al. 2016). Sensitivity analyses: 0.5% and 5%.
* **Six error types, transcription errors only**, each one sixth of the
  injected errors. Cells are drawn uniformly among the eligible cells of each
  type. A type with fewer eligible cells than its share uses all of them and
  the shortfall is reported; it is not redistributed. A cell gets at most one
  error.
  1. **Digit transposition.** Two adjacent digits of the value as written are
     exchanged, the decimal point staying in place (sodium 142 becomes 124 or
     412, potassium 4.6 becomes 6.4). Eligible if the result differs.
  2. **Unit error.** The value is written in a common alternative unit: glucose
     and urea nitrogen, calcium, magnesium and phosphate mg/dL to mmol/L,
     creatinine mg/dL to umol/L, hemoglobin g/dL to g/L, hematocrit % to a
     fraction, temperature Celsius to Fahrenheit, weight kg to lb, and mg doses
     written in grams. Not eligible: fields whose usual alternative unit gives
     the same number (sodium, potassium, chloride, bicarbonate in mEq/L; white
     cells and platelets in 10^9/L) and fields without an alternative unit
     (heart rate, blood pressure, respiratory rate, SpO2, heparin units).
  3. **Decimal slip.** The decimal point moves one place (x10 or /10, equal
     probability), rounded to the field's decimals. Eligible if the result
     differs and is above zero.
  4. **Copied from the previous visit.** The value is replaced by the same
     patient's value of the same field at the previous visit where it was
     recorded. Eligible if that exists and differs.
  5. **Wrong visit date.** One of: day and month exchanged (if the day is 12 or
     less and differs from the month), the two digits of the day exchanged (if
     that gives a different valid day), the month off by one, the year off by
     one; drawn uniformly among those that apply. Applies to date cells only.
  6. **Values swapped between patients.** Two cells of the same field at the
     same visit (for example both D3) from two different patients of the same
     split exchange values; both count as errors. Eligible if the values
     differ.
* Injected values may land inside or outside the range rules; this is not
  controlled.
* The ground truth (cell, type, original and injected value) is written to a
  separate file that only the evaluation step reads.
* **Replicates.** R = 20 independent injections for the primary analysis,
  R = 10 for the ablation and the sensitivity analyses.

## Detectors

No detector may restate how errors were injected. There is no
"value equals previous visit" check, no swap or unit-conversion detector, no
rule written for an error type, and the date model has no feature for
exchanged day and month. The cross-modal rules of the earlier proof of concept
(unexplained fever, renal dosing) are dropped for that reason.

1. **Range rules (the EDC baseline).** A fixed plausible range per field
   (`config.py`, taken from the proof of concept for the fields it shares; the
   only change made with knowledge of those results is the metoprolol lower
   limit, lowered to 1.25 mg/day because intravenous doses of 1.25-5 mg are
   standard). Date cells: the date must lie within the visit window around the
   nominal date and must not precede the same form's date at the previous
   visit. Ranking for a budget: distance outside the range divided by the
   range width (dates: days outside the window divided by the window width);
   ties in a fixed random order. Only flagged cells can be queried.
2. **Cross-modal plausibility model (the method under test).** For each field,
   a model of the recorded value given the patient's other data.
   * Features: (a) own history: the same field at the previous and next
     recorded visit and the days between, the patient's leave-one-out median,
     the number of other recorded visits; (b) same visit, other modalities:
     every other laboratory, vital sign and dose field, their changes since the
     previous visit, and engineered relations (Na - Cl - HCO3 for the
     electrolytes, the hematocrit to hemoglobin ratio, (SBP + 2 DBP) / 3 for the
     pressures); (c) medication classes active at the visit; (d) baseline: age,
     sex, diagnosis groups; (e) visit day. For date cells the target is the
     form date's offset in days from the nominal date and the features are the
     other form's offset at the same visit, the same form's offsets at adjacent
     visits and the visit day.
   * Model: LightGBM. Location with Huber loss on the field's modelling scale
     (log for urea nitrogen, creatinine, glucose, phosphate, white cells,
     platelets and doses); scale from a second model of the absolute
     out-of-fold residual (L1 loss); score = |y - mu| / sigma, with a floor on
     sigma of half the recorded resolution or 0.1 robust SD, whichever is
     larger. Hyperparameters fixed in `config.py`.
   * Training: on training patients only. Out-of-fold residuals for the scale
     model come from 5-fold patient cross-fitting within the training patients;
     the final models are fit on all training patients and applied to held-out
     patients.
   * Fields with fewer than 30 recorded training cells are scored with a
     population robust z (median and MAD of the training cells).
   * Explaining away on held-out patients, as in the proof of concept: cells
     above |z| = 4 are confirmed one neighbourhood at a time, most implausible
     first, removed from every other cell's features, and the rest re-scored,
     until no unconfirmed cell exceeds 4 (at most 30 rounds). Neighbourhood:
     same patient and visit, or same field at the adjacent recorded visits. The
     budget ranking uses the final score.
3. **Delta check (secondary baseline).** |value - previous recorded value of
   the same field| divided by the robust SD of visit-to-visit changes of that
   field on training patients. Cells without a previous value and date cells
   are not scored.
4. **Combined (secondary).** Range-rule violations first, by severity; the rest
   of the budget filled by the plausibility model's ranking.

**Ablation (secondary).** The model is refit without: (i) own history
("cross-modal only"); (ii) all other modalities and baseline ("own history
only"); (iii) laboratory context; (iv) vital-sign context; (v) medication
context (dose fields and medication classes); (vi) date context (date cells
only); (vii) baseline context. Each removes the named features from every
field's model; a field's own history is removed only in (i).

**Explanations.** Every query carries a one-sentence, non-leading explanation
of the evidence (the patient's adjacent values, the strongest same-visit
evidence, the visit window for dates). No detector ever writes a value; a test
checks that the data are unchanged after detection.

## Budgets and endpoints

* **Budgets.** b = 0.05, 0.10, 0.25, 0.50 and 1.00 queries per patient per
  visit. For a set of held-out patients with V patient-visits, a detector may
  raise Q = round(b x V) queries, on its Q highest-ranked cells.
* **Errors caught per query** (yield) = errors among the raised queries / Q.
  **Precision** = errors among the raised queries / queries raised. They differ
  only when a detector has fewer than Q cells to query, which can happen to the
  range rules; their unused budget counts as catching nothing.
* **Primary endpoint.** Yield at b = 0.25 on held-out patients, averaged over
  the 20 replicates.
* **Primary comparison.** Yield difference, model minus range rules, at
  b = 0.25. 95% interval from a patient-level cluster bootstrap of the held-out
  patients (2,000 resamples): each resample draws patients with replacement,
  recomputes V and Q, re-selects the top Q cells of each detector in each
  replicate and averages over replicates. **Better** if the interval is above
  0, **worse** if below 0, **no clear difference** otherwise. This is the only
  confirmatory comparison.
* **Secondary, descriptive** (same bootstrap, no multiplicity adjustment): yield,
  precision, queries raised and recall at every budget for every detector; the
  difference to range rules at every budget; recall by error type; recall by
  error size (|injected - original| in robust SD units of the field on training
  patients: under 0.5, 0.5 to 2, over 2; dates: up to 7 days, more than 7 days).
* **Ablation.** Yield and recall by error type at b = 0.25 for each variant,
  and the difference to the full model with a bootstrap interval (R = 10).
* **Sensitivity.** Error rates 0.5% and 5%: model, range rules, delta check and
  combined at every budget (R = 10).

## Secondary analysis A: conformal false-query control

Added at the author's request before this plan was committed.

* **Calibration set.** Clean visits of training patients: their patient-visits
  in which no cell received an injected error in that replicate. Their scores
  come from the 5-fold cross-fitted models, so they are out of sample.
  Selecting clean visits uses the injection ground truth; in practice it stands
  for visits verified at source.
* **Scores.** The first-pass score of each detector, without explaining away,
  for calibration and held-out cells alike, so that the two are computed the
  same way.
* **Conformal p-value** for each held-out cell j (Bates et al. 2023):
  p_j = (1 + #{calibration cells i with s_i >= s_j}) / (n + 1), with the
  calibration cells of all fields pooled.
* **Sites.** MIMIC comes from one hospital, so the 50 held-out patients are
  allocated at random (fixed seed) to 5 pseudo-sites of 10 patients.
  Benjamini-Hochberg is applied within each site at target false-query rates
  alpha = 0.10 and 0.20.
* **Reported** for every detector and alpha: queries raised (total and per
  patient-visit), errors caught, and the achieved false-query rate (false
  queries / queries raised) pooled and per site, averaged over replicates, with
  bootstrap intervals; shown next to the fixed-budget results.
* **Stated plainly in the results:** the guarantee holds only if the
  calibration cells are exchangeable with the clean held-out cells, that is, if
  the calibration data are clean. Here they are only free of *injected*
  errors; any genuine recording error left in MIMIC breaks the assumption, and
  real calibration data are never fully clean. The calibration scores also come
  from models fit on 80% of the training patients while held-out scores come
  from models fit on all of them, a small further departure.

## Secondary analysis B: the index of individuality and swap detectability

Pre-registered hypothesis: **across laboratory and vital-sign fields, the index
of individuality is negatively correlated with how well swapped values are
detected.** The relationship is expected from the delta-check literature (Tan
et al. 2020); what is tested is whether it holds for the cross-modal model.

* **Index of individuality** per field, on the modelling scale, estimated on
  training patients before error injection: within-patient SD (median over
  patients with at least 3 recorded visits) divided by the SD of those
  patients' medians (Harris 1974; analytical variation not separated).
* **Detectability** per field: the AUROC of the full model's score for swapped
  cells against clean cells of the same field, held-out patients, pooled over
  the 20 replicates. Recall of swapped cells at b = 0.25 is reported as a
  secondary measure.
* **Test.** Spearman correlation across fields with at least 20 swapped cells,
  one-sided (rho < 0), permutation p-value from 10,000 permutations, alpha
  0.05. Reported whether or not it holds.
* **Fields where cross-modal context changes detectability beyond the index.**
  A least-squares line of detectability on the index is fit to the
  own-history-only ablation (what a patient's own history can achieve given its
  individuality). For each field the full model's distance above that line and
  its gain over the own-history-only model are reported; fields with a gain of
  at least 0.05 AUROC that lie above the line are listed as changed by
  cross-modal context. Expected in advance: the blood pressure components
  (linked by MAP = (SBP + 2 DBP) / 3), the electrolytes (sodium, chloride,
  bicarbonate) and hemoglobin with hematocrit.

## Reproducibility

Fixed seeds for the split, every replicate's injection, the pseudo-sites, the
bootstrap and the permutation test. Pinned dependencies. `make all` reruns
everything from the raw files.

## Implementation details (fixed with the code, before any result was computed)

One replicate was run end to end to time the pipeline (about 25 seconds); no
detection metric was computed from it.

* **Cohort.** 99 of the 100 patients have at least one cell; the split is drawn
  over all 100, so the held-out set has 49 patients with data.
* **Resampling.** Other ICU vital signs within +/- 1 hour of the chosen heart
  rate; weight anywhere in the visit window. Doses: the most recently started
  order active at the nominal time; heparin restricted to route SC and
  vancomycin to route IV.
* **Recorded decimals** as in `config.py`; metoprolol doses with two decimals
  (6.25 mg), grams in unit errors with three or four.
* **Error injection.** Types are drawn in the order wrong date, patient swap,
  copy, unit error, decimal slip, transposition, each from the cells still
  untouched. A swap share of k cells gives floor(k / 2) pairs. A copied value is
  the clean value of the previous visit. A decimal slip divided by ten keeps one
  more decimal (98 becomes 9.8).
* **Ranking.** Ties are broken by a random order seeded per replicate and
  detector. Range rules can only query cells that violate a rule. The delta
  check scores only cells with a previous value. The combined detector ranks
  every range violation above every other cell.
* **Bootstrap.** The same 2,000 patient resamples are used for every detector
  and replicate, so differences are paired. A resampled patient's cells count
  with their multiplicity; when the budget ends inside a duplicated cell, that
  cell counts fractionally.
* **Conformal analysis.** Cells a detector does not score get p = 1. The
  combined detector's calibration score combines the range rules with the
  model's out-of-fold score.
* **Index of individuality** on the modelling scale. Detectability uses the
  model's final score (after explaining away), pooled over the 20 primary
  replicates; the own-history-only AUROC is pooled over the 10 ablation
  replicates.
* **Error size** is measured on the modelling scale against the robust SD of
  the field in training patients before injection.

## Deviations

All four were made after the results were seen. None changes the primary
analysis.

1. **Conformal intervals come from the spread over replicates, not from the
   patient bootstrap.** In the first evaluation the bootstrap interval of the
   delta check's errors caught did not contain its own point estimate. The
   reason is that a bootstrap resample duplicates patients, so the same
   p-values appear several times, and Benjamini-Hochberg then rejects more than
   it would on real data. The conformal results are therefore reported as the
   mean over the 20 replicates with the 2.5 and 97.5 percentiles over
   replicates. These intervals reflect injection variability only, not patient
   sampling, and are narrower than an honest interval would be.
2. **An exploratory version of the individuality test over all fields.** Only
   4 fields reached the pre-registered minimum of 20 swapped cells, so the
   pre-registered test has little power. The same Spearman test over all 22
   laboratory and vital-sign fields is reported next to it, labelled
   exploratory. The pre-registered result stands as the answer to the
   hypothesis.
3. **Error size for fields with no spread.** Some dose fields have a robust SD
   of zero in training patients, which made every error in them "> 2 SD". The
   size is now scaled by the SD, or 1, when the robust SD is zero. Only the
   recall-by-size table can change, and only for dose errors.
4. **Faster budget counts.** The evaluation code was changed to sum only over
   the ranked cells a budget can reach. The tests compare it with literally
   duplicating resampled patients, and the primary numbers were identical
   before and after the change.
