# Literature check: error detection, central monitoring and query budgets

Searched 2026-10-21, before any code in this repository was written. The aim was
to find (1) established methods and evaluation practice to reuse, and (2) prior
work that already compares value-level error detectors at a fixed review or
query budget, so that the README claims only what is new.

## How the citations were verified

* Every DOI below was resolved against its registry record on 2026-10-21:
  Crossref (`api.crossref.org/works/<doi>`) for articles and DataCite
  (`api.datacite.org/dois/<doi>`) for the MIMIC-IV demo. Authors, title, journal,
  volume, issue and pages are copied from that record.
* What is said about each clinical paper is taken from its PubMed abstract
  (NCBI E-utilities), not from secondary summaries. Where a number circulates in
  secondary sources but is not in the abstract, it is not used here.
* What is said about the data-cleaning papers is taken from their abstracts in
  the full text (VLDB and author-hosted PDFs).
* The regulatory documents were read in full from the issuing agency: the ICH
  E6(R3) Step 4 PDF, the two FDA guidance PDFs, the Federal Register API record
  of the FDA adoption of E6(R3), and the EMA reflection paper PDF.
* Searches: Crossref bibliographic queries and web searches for *query burden*,
  *queries per patient*, *targeted source data verification*, *budgeted data
  cleaning*, *delta check simulation*, *index of individuality and delta checks*
  and *conformal p-values clinical data*.

## 1. Error detection and data cleaning

| Work | What it does | How it is evaluated | Used here |
|---|---|---|---|
| Rekatsinas et al. 2017, HoloClean | Repairs data: combines integrity constraints and external data with statistical properties of the data in one probabilistic program | precision and recall of repairs (about 90% and 76% on average, per the abstract) | the idea of judging a cell by its plausibility given the rest of its record; **repair is not used**, by design |
| Heidari et al. 2019, HoloDetect | Few-shot error detection, learns from a small labeled set augmented with generated errors | cell-level precision, recall, F1 | cell-level metrics; we use no labels |
| Mahdavi et al. 2019, Raha | Configuration-free error detection: an ensemble of detector configurations as features, the user labels a few tuples | cell-level precision, recall, F1; "no more than 20 labeled tuples on each dataset" | cell-level metrics; labeling effort as an explicit cost |
| Mahdavi and Abedjan 2020, Baran | Error correction; describes a value's context as the value itself, the co-occurring values in the same tuple and the attribute's values; "only 20 labeled tuples" | precision, recall of corrections | the three-way context maps onto our own-history, same-visit and population features; correction is not used |
| Abedjan et al. 2016 | Runs several error detection tools on five real datasets with ground truth | coverage of each tool "well below 100%"; the order of running tools matters; proposes ordering tools "to maximize their benefit, while minimizing human effort in verifying results" | verification effort as the quantity to budget; a combined detector as a secondary analysis |
| Arocena et al. 2015, BART | Controlled generation of errors in clean data for benchmarking cleaning algorithms | a benchmark generator | controlled error injection with known ground truth |
| Krishnan et al. 2016, ActiveClean | Chooses which records to clean first under a limited cleaning budget, for model training | model accuracy against records cleaned | prioritising review under a budget |
| Campos et al. 2016 | Evaluation of unsupervised outlier detection | precision at n, average precision, ROC AUC; rank-based measures | precision at a fixed number of queries is precision at n |
| Damerau 1964 | Spelling-error correction | n/a | adjacent transposition is one of the four single-error classes (insertion, deletion, substitution, transposition) |
| Wu and Keogh 2021 | Critique of time-series anomaly benchmarks | identifies trivial anomalies, unrealistic anomaly density and mislabeled ground truth as flaws | realistic error rates; no detector that restates the injected errors; held-out patients |

## 2. Laboratory medicine: delta checks and biological variation

| Work | Relevance |
|---|---|
| Strathmann et al. 2011 | Simulates specimen mislabeling by sampling successive specimens from the same patient or from two different patients, and evaluates univariate delta checks. MCV performed best; potassium and anion gap rules had very low yield. |
| Ovens and Naugler 2012 | Simulates mix-ups by switching pairs of second results for five analytes; sensitivities generally below 20% except creatinine (82.8%); positive predictive value negligible at plausible mix-up rates. |
| Rosenbaum and Baron 2018 | Simulated wrong-blood-in-tube errors; a multianalyte machine-learning delta check (11 analytes) reached AUC 0.97 and beat single-analyte delta checks. |
| Harris 1974; Fraser and Harris 1989 | The index of individuality: within-subject over between-subject biological variation. |
| Tan, Markus and Loh 2020 | Shows mathematically that delta-check specificity is scaled by within-subject variation and sensitivity by between-subject variation, and compares with laboratory data. |

These are the closest precedents for the patient-swap error used here, and for
the detectability hypothesis (section 6).

## 3. Central statistical monitoring of clinical trial data

| Work | Unit of analysis | Relevance |
|---|---|---|
| Venet et al. 2012 | centre | many statistical tests on all variables, a matrix of p-values used to find centres that differ from the others |
| Kirkwood et al. 2013 | centre | application of central statistical monitoring methods |
| Desmet et al. 2014 | centre | linear mixed-effects models for central statistical monitoring |
| Edwards et al. 2014 (CRASH-2) | centre | central monitoring used to target on-site visits; coefficient of variation of SBP, heart rate, respiratory rate per site |
| Timmermans et al. 2016 | centre | data-driven risk identification in phase III trials |
| Trotta et al. 2019 | centre | real trial data contaminated in simulation; sensitivity and specificity of unsupervised monitoring measured on the contaminated centres |
| Buyse et al. 2020 | centre | central statistical monitoring in investigator-led oncology trials |
| de Viron et al. 2024 | centre | 1,111 sites flagged by statistical data monitoring in 159 studies; quality metrics improved at 83% of them |
| Nelson et al. 2025 | form | machine-learning outlier detection of form-level irregularities; ground truth from comparing early database snapshots with the locked database; reports AUROC, positive predictive value and sensitivity |

Central statistical monitoring works at the level of the centre (and, in Nelson
et al., the form). This repository works at the level of the single recorded
value, which is what a data query is raised on. Trotta et al. 2019 is the
precedent for evaluating a monitoring method by contaminating real data.

## 4. Regulatory context

* **ICH E6(R3)**, Guideline for Good Clinical Practice, endorsed under Step 4 on
  6 January 2025. Section 3.11.4.2 defines centralised monitoring as an
  evaluation of accumulated data by the sponsor's qualified persons (for example
  a data manager or biostatistician) and says centralised data analytics "can
  help identify systemic or site-specific issues, including protocol
  noncompliance and potentially unreliable data". Section 4.2.1(c): "At the
  point of data capture, automated data validation checks to raise data queries
  should be considered as required based on risk". The sponsor should focus
  quality control, including data review, on data of higher criticality.
  https://database.ich.org/sites/default/files/ICH_E6(R3)_Step4_FinalGuideline_2025_0106.pdf
* **FDA** adopted E6(R3) as final guidance for industry: Federal Register
  document 2025-17311, 90 FR 43460, 9 September 2025.
* **FDA**, *Oversight of Clinical Investigations: A Risk-Based Approach to
  Monitoring*, guidance for industry, August 2013 (https://www.fda.gov/media/116754/download).
  Defines centralized monitoring as a remote evaluation by sponsor personnel and
  notes that data anomalies may be more readily detected centrally than on site.
* **FDA**, *A Risk-Based Approach to Monitoring of Clinical Investigations:
  Questions and Answers*, guidance for industry, April 2023
  (https://www.fda.gov/media/121479/download). Q4: centralized monitoring as a
  systematic analytical evaluation across sites that can detect potential
  anomalies more quickly.
* **EMA**, *Reflection paper on risk based quality management in clinical
  trials*, EMA/269011/2013, 18 November 2013 (now marked as superseded). Suggests
  more central monitoring and targeted source data verification on the
  variables important for the trial objectives.

None of these documents prescribes a query budget or a detection method. They
ask for risk-proportionate checks and centralised review, which is the setting
this repository models.

## 5. Error rates, query burden and budgeted review in clinical data management

| Work | What it reports |
|---|---|
| Nahm et al. 2008 | source-to-database error rate of 14.3 per 10,000 fields in EDC trials without medical record abstraction |
| Garza et al. 2025 | meta-analysis of 93 papers: pooled error rate 6.57% for medical record abstraction, 0.74% optical scanning, 0.29% single data entry, 0.14% double data entry |
| van den Bor et al. 2016 | in empirical trial data, an average pre-SDV transcription error proportion of 0.056 per trial; acceptance sampling for source data verification |
| Grieve 2012 | source data verification by statistical sampling |
| Mitchel et al. 2011 | the main errors in an EDC trial database were transcription errors from paper source to EDC |
| Sheetz et al. 2014 | generalized source data verification has limited value as a quality control measure |
| Tantsyura et al. 2015 | errors and their corrections have minimal effect on study results, diminishing with study size; on average under 8% SDV adequate |
| Tantsyura et al. 2016 | query-driven, "on-demand" SDV and its cost savings |
| Fougerou-Leurent et al. 2019 | targeted SDV produced about 4 times more queries per study than full SDV (132 vs 34); whether total workload went up depended on handling time per query (15 to 45 minutes) |
| Kahn et al. 2016; Weiskopf and Weng 2013 | data quality frameworks for EHR data reuse; plausibility as a dimension of data quality |
| Weis and Levy 2014 | copy-paste and cloned notes in electronic health records, the narrative analogue of carried-forward values |

**Finding on query burden.** The literature measures queries as a cost (per
study, per form, in handling time) and studies how much source data
verification is needed. No study found here compares value-level error
detectors at a fixed number of queries per patient per visit. The closest are:
Abedjan et al. 2016, who order tools to minimise human verification effort on
enterprise datasets; Raha and Baran, which fix the labeling effort at about 20
tuples; and the delta-check literature, which reports sensitivity and positive
predictive value of single-analyte rules. Industry figures for queries per form
and cost per query exist but trace back to vendor or conference material, so
they are not used.

## 6. Methods adopted for the two pre-specified secondary analyses

* **Conformal p-values and Benjamini-Hochberg.** Bates, Candes, Lei, Romano and
  Sesia 2023 construct p-values for outlier detection from a calibration set of
  inliers and show that the Benjamini-Hochberg procedure (Benjamini and
  Hochberg 1995) applied to them controls the false discovery rate. The
  guarantee assumes calibration inliers exchangeable with the test inliers, that
  is, clean calibration data. No application of conformal p-values to clinical
  data queries was found.
* **Index of individuality.** Harris 1974 and Fraser and Harris 1989 define it;
  Tan et al. 2020 relate within- and between-subject variation to delta-check
  specificity and sensitivity; Ovens and Naugler 2012 and Strathmann et al.
  2011 show the expected pattern empirically for single analytes. The
  hypothesis tested here (lower index, higher swap detectability) is therefore
  an expected relationship, not a new one. What is tested here is whether it
  holds for a multivariate, cross-modal detector on trial-like visit data, and
  which variables escape it.

## What is new here, as far as this search goes

1. **The comparison axis.** Value-level detectors compared at fixed query
   budgets expressed in queries per patient per visit, the unit in which a data
   manager's review capacity is planned, with errors caught per query and
   precision at each budget.
2. **The setting.** EDC-style range rules against a cross-modal plausibility
   model on ICU data resampled to a trial visit schedule, with a modality
   ablation, transcription errors only, held-out patients and a pre-registered
   plan.
3. **Conformal false-query control** applied to clinical data queries per site,
   as a secondary analysis. The method is Bates et al. 2023; only its use here
   is new.

Not new: error injection for evaluation (BART, Trotta et al. 2019, Strathmann et
al. 2011), cell-level precision and recall (HoloDetect, Raha), the idea of
scoring a value against its context (HoloClean, Baran, multianalyte delta
checks), and the link between biological variation and swap detectability
(Tan et al. 2020). Anyone who knows of prior work that compares detectors at a
fixed query budget in clinical data management is asked to open an issue so the
claim can be corrected.

## References

* Abedjan Z, Chu X, Deng D, Fernandez RC, Ilyas IF, Ouzzani M, Papotti P, Stonebraker M, Tang N. Detecting data errors: where are we and what needs to be done? *Proc VLDB Endow* 2016;9(12):993-1004. https://doi.org/10.14778/2994509.2994518
* Arocena PC, Glavic B, Mecca G, Miller RJ, Papotti P, Santoro D. Messing up with BART: error generation for evaluating data-cleaning algorithms. *Proc VLDB Endow* 2015;9(2):36-47. https://doi.org/10.14778/2850578.2850579
* Bates S, Candes E, Lei L, Romano Y, Sesia M. Testing for outliers with conformal p-values. *Ann Stat* 2023;51(1):149-178. https://doi.org/10.1214/22-AOS2244
* Benjamini Y, Hochberg Y. Controlling the false discovery rate: a practical and powerful approach to multiple testing. *J R Stat Soc Series B* 1995;57(1):289-300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
* Buyse M, Trotta L, Saad ED, Sakamoto J. Central statistical monitoring of investigator-led clinical trials in oncology. *Int J Clin Oncol* 2020;25(7):1207-1214. https://doi.org/10.1007/s10147-020-01726-6
* Campos GO, Zimek A, Sander J, Campello RJGB, Micenkova B, Schubert E, Assent I, Houle ME. On the evaluation of unsupervised outlier detection: measures, datasets, and an empirical study. *Data Min Knowl Discov* 2016;30(4):891-927. https://doi.org/10.1007/s10618-015-0444-8
* Damerau FJ. A technique for computer detection and correction of spelling errors. *Commun ACM* 1964;7(3):171-176. https://doi.org/10.1145/363958.363994
* de Viron S, Trotta L, Steijn W, Young S, Buyse M. Does central statistical monitoring improve data quality? An analysis of 1,111 sites in 159 clinical trials. *Ther Innov Regul Sci* 2024;58(3):483-494. https://doi.org/10.1007/s43441-024-00613-w
* Desmet L, Venet D, Doffagne E, Timmermans C, Burzykowski T, Legrand C, Buyse M. Linear mixed-effects models for central statistical monitoring of multicenter clinical trials. *Stat Med* 2014;33(30):5265-5279. https://doi.org/10.1002/sim.6294
* Edwards P, Shakur H, Barnetson L, Prieto D, Evans S, Roberts I. Central and statistical data monitoring in the Clinical Randomisation of an Antifibrinolytic in Significant Haemorrhage (CRASH-2) trial. *Clin Trials* 2014;11(3):336-343. https://doi.org/10.1177/1740774513514145
* Fougerou-Leurent C, Laviolle B, Tual C, Visseiche V, Veislinger A, Danjou H, et al. Impact of a targeted monitoring on data-quality and data-management workload of randomized controlled trials: a prospective comparative study. *Br J Clin Pharmacol* 2019;85(12):2784-2792. https://doi.org/10.1111/bcp.14108
* Fraser CG, Harris EK. Generation and application of data on biological variation in clinical chemistry. *Crit Rev Clin Lab Sci* 1989;27(5):409-437. https://doi.org/10.3109/10408368909106595
* Garza MY, Williams T, Ounpraseuth S, Hu Z, Lee J, Snowden J, et al. Error rates of data processing methods in clinical research: a systematic review and meta-analysis of manuscripts identified through PubMed. *Int J Med Inform* 2025;195:105749. https://doi.org/10.1016/j.ijmedinf.2024.105749
* Grieve AP. Source data verification by statistical sampling: issues in implementation. *Drug Inf J* 2012;46(3):368-377. https://doi.org/10.1177/0092861512442057
* Harris EK. Effects of intra- and interindividual variation on the appropriate use of normal ranges. *Clin Chem* 1974;20(12):1535-1542. https://doi.org/10.1093/clinchem/20.12.1535
* Heidari A, McGrath J, Ilyas IF, Rekatsinas T. HoloDetect: few-shot learning for error detection. *Proceedings of SIGMOD* 2019:829-846. https://doi.org/10.1145/3299869.3319888
* Kahn MG, Callahan TJ, Barnard J, Bauck AE, Brown J, Davidson BN, et al. A harmonized data quality assessment terminology and framework for the secondary use of electronic health record data. *eGEMs* 2016;4(1):18. https://doi.org/10.13063/2327-9214.1244
* Kirkwood AA, Cox T, Hackshaw A. Application of methods for central statistical monitoring in clinical trials. *Clin Trials* 2013;10(5):783-806. https://doi.org/10.1177/1740774513494504
* Krishnan S, Wang J, Wu E, Franklin MJ, Goldberg K. ActiveClean: interactive data cleaning for statistical modeling. *Proc VLDB Endow* 2016;9(12):948-959. https://doi.org/10.14778/2994509.2994514
* Mahdavi M, Abedjan Z, Castro Fernandez R, Madden S, Ouzzani M, Stonebraker M, Tang N. Raha: a configuration-free error detection system. *Proceedings of SIGMOD* 2019:865-882. https://doi.org/10.1145/3299869.3324956
* Mahdavi M, Abedjan Z. Baran: effective error correction via a unified context representation and transfer learning. *Proc VLDB Endow* 2020;13(12):1948-1961. https://doi.org/10.14778/3407790.3407801
* Mitchel JT, Kim YJ, Choi J, Park G, Cappi S, Horn D, et al. Evaluation of data entry errors and data changes to an electronic data capture clinical trial database. *Drug Inf J* 2011;45(4):421-430. https://doi.org/10.1177/009286151104500404
* Nahm ML, Pieper CF, Cunningham MM. Quantifying data quality for clinical trials using electronic data capture. *PLoS ONE* 2008;3(8):e3049. https://doi.org/10.1371/journal.pone.0003049
* Nelson W, Petch J, Ranisau J, Zhao R, Balasubramanian K, Bangdiwala SI. Detecting irregularities in randomized controlled trials using machine learning. *Clin Trials* 2025;22(2):178-187. https://doi.org/10.1177/17407745241297947
* Ovens K, Naugler C. How useful are delta checks in the 21st century? A stochastic-dynamic model of specimen mix-up and detection. *J Pathol Inform* 2012;3(1):5. https://doi.org/10.4103/2153-3539.93402
* Rekatsinas T, Chu X, Ilyas IF, Re C. HoloClean: holistic data repairs with probabilistic inference. *Proc VLDB Endow* 2017;10(11):1190-1201. https://doi.org/10.14778/3137628.3137631
* Rosenbaum MW, Baron JM. Using machine learning-based multianalyte delta checks to detect wrong blood in tube errors. *Am J Clin Pathol* 2018;150(6):555-566. https://doi.org/10.1093/ajcp/aqy085
* Sheetz N, Wilson B, Benedict J, Huffman E, Lawton A, Travers M, et al. Evaluating source data verification as a quality control measure in clinical trials. *Ther Innov Regul Sci* 2014;48(6):671-680. https://doi.org/10.1177/2168479014554400
* Strathmann FG, Baird GS, Hoffman NG. Simulations of delta check rule performance to detect specimen mislabeling using historical laboratory data. *Clin Chim Acta* 2011;412(21-22):1973-1977. https://doi.org/10.1016/j.cca.2011.07.007
* Tan RZ, Markus C, Loh TP. Relationship between biological variation and delta check rules performance. *Clin Biochem* 2020;80:42-47. https://doi.org/10.1016/j.clinbiochem.2020.03.017
* Tantsyura V, Dunn IM, Fendt K, Kim YJ, Waters J, Mitchel J. Risk-based monitoring: a closer statistical look at source document verification, queries, study size effects, and data quality. *Ther Innov Regul Sci* 2015;49(6):903-910. https://doi.org/10.1177/2168479015586001
* Tantsyura V, Dunn IM, Waters J, Fendt K, Kim YJ, Viola D, et al. Extended risk-based monitoring model, on-demand query-driven source data verification, and their economic impact on clinical trial operations. *Ther Innov Regul Sci* 2016;50(1):115-122. https://doi.org/10.1177/2168479015596020
* Timmermans C, Venet D, Burzykowski T. Data-driven risk identification in phase III clinical trials using central statistical monitoring. *Int J Clin Oncol* 2016;21(1):38-45. https://doi.org/10.1007/s10147-015-0877-5
* Trotta L, Kabeya Y, Buyse M, Doffagne E, Venet D, Desmet L, et al. Detection of atypical data in multicenter clinical trials using unsupervised statistical monitoring. *Clin Trials* 2019;16(5):512-522. https://doi.org/10.1177/1740774519862564
* van den Bor RM, Oosterman BJ, Oostendorp MB, Grobbee DE, Roes KCB. Efficient source data verification using statistical acceptance sampling: a simulation study. *Ther Innov Regul Sci* 2016;50(1):82-90. https://doi.org/10.1177/2168479015602042
* Venet D, Doffagne E, Burzykowski T, Beckers F, Tellier Y, Genevois-Marlin E, et al. A statistical approach to central monitoring of data quality in clinical trials. *Clin Trials* 2012;9(6):705-713. https://doi.org/10.1177/1740774512447898
* Weis JM, Levy PC. Copy, paste, and cloned notes in electronic health records. *Chest* 2014;145(3):632-638. https://doi.org/10.1378/chest.13-0886
* Weiskopf NG, Weng C. Methods and dimensions of electronic health record data quality assessment: enabling reuse for clinical research. *J Am Med Inform Assoc* 2013;20(1):144-151. https://doi.org/10.1136/amiajnl-2011-000681
* Wu R, Keogh E. Current time series anomaly detection benchmarks are flawed and are creating the illusion of progress. *IEEE Trans Knowl Data Eng*, published online 2021. https://doi.org/10.1109/TKDE.2021.3112126

Regulatory documents (no DOI): ICH E6(R3) Step 4, 6 January 2025; FDA guidance
for industry, August 2013 and April 2023; Federal Register 90 FR 43460, 9
September 2025; EMA/269011/2013, 18 November 2013. URLs are given in section 4.

Data: Johnson A, Bulgarelli L, Pollard T, Horng S, Celi LA, Mark R. MIMIC-IV
Clinical Database Demo (version 2.2). PhysioNet 2023.
https://doi.org/10.13026/dp1f-ex47 (DataCite record checked). Johnson AEW,
Bulgarelli L, Shen L, et al. MIMIC-IV, a freely accessible electronic health
record dataset. *Sci Data* 2023;10(1):1. https://doi.org/10.1038/s41597-022-01899-x.
Pollard T, Moody BE, Lehman LH, Gow BJ, Fernandes C, Xie C, et al. PhysioNet as
a global platform for biomedical research. *Nature Health* 2026;1(8):792-795.
https://doi.org/10.1038/s44360-026-00096-z
