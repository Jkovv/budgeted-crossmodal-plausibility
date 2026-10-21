"""Command line entry point: ``python -m bcp.cli <step>``.

prepare      raw tables -> data/processed/ (cells, visits, context)
primary      20 replicates at 2%: all detectors on held-out patients -> results/cells/
ablation     10 replicates, the seven reduced models (same injections as primary)
sensitivity  10 replicates each at 0.5% and 5%
evaluate     results/cells/ -> results/tables/*.csv, results/summary.json
figures      results/tables/ -> results/figures/*.png
all          every step in order
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from . import config as C

log = logging.getLogger("bcp")


def load_processed() -> dict:
    d = {k: pd.read_parquet(C.PROCESSED_DIR / f"{k}.parquet") for k in ("cells", "visits", "baseline", "visit_context")}
    d["split"] = pd.read_parquet(C.PROCESSED_DIR / "split.parquet").set_index("subject_id").group
    return d


def step_prepare(args) -> None:
    from . import load, resample, run
    out = resample.build(load.load_tables())
    C.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for k in ("cells", "visits", "baseline", "visit_context"):
        out[k].to_parquet(C.PROCESSED_DIR / f"{k}.parquet", index=False)
    split = run.split_patients(out["baseline"].subject_id)
    split.rename_axis("subject_id").reset_index().to_parquet(C.PROCESSED_DIR / "split.parquet", index=False)
    report = {**out["report"], "split": split.value_counts().to_dict(),
              "patients_with_cells": out["cells"].drop_duplicates("subject_id").subject_id.map(split).value_counts().to_dict()}
    C.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    (C.TABLES_DIR / "prepare_report.json").write_text(json.dumps(report, indent=2, default=str))
    log.info("%d cells, %d patient-visits", report["cells"], report["patient_visits"])


def _job(job):
    from . import run
    analysis, rate, rep, variants, baselines = job
    data = load_processed()
    out, calib, counts = run.run_replicate(data, data["split"], rate, rep, variants, baselines)
    C.CELLS_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(C.CELLS_DIR / f"{analysis}_r{rep:02d}_test.parquet", index=False)
    calib.to_parquet(C.CELLS_DIR / f"{analysis}_r{rep:02d}_calib.parquet", index=False)
    return analysis, rep, counts


def _run_jobs(jobs, workers: int) -> list[dict]:
    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for analysis, rep, counts in ex.map(_job, jobs):
            log.info("%s replicate %d done (%.0f s)", analysis, rep, counts["seconds"])
            results.append(dict(analysis=analysis, **counts))
    log.info("%d replicates in %.0f s", len(jobs), time.time() - t0)
    return results


def _save_counts(name: str, results: list[dict]) -> None:
    C.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    (C.TABLES_DIR / f"injection_{name}.json").write_text(json.dumps(results, indent=2, default=str))


def step_primary(args) -> None:
    jobs = [("primary", C.ERROR_RATE, r, ("full",), True) for r in range(C.N_REPLICATES)]
    _save_counts("primary", _run_jobs(jobs, args.workers))


def step_ablation(args) -> None:
    jobs = [("ablation_raw", C.ERROR_RATE, r, tuple(C.ABLATIONS), False) for r in range(C.N_REPLICATES_SECONDARY)]
    _save_counts("ablation", _run_jobs(jobs, args.workers))
    for r in range(C.N_REPLICATES_SECONDARY):        # same injections as primary: add its full model
        prim = pd.read_parquet(C.CELLS_DIR / f"primary_r{r:02d}_test.parquet")
        abl = pd.read_parquet(C.CELLS_DIR / f"ablation_raw_r{r:02d}_test.parquet")
        assert prim.cell_id.equals(abl.cell_id) and prim.error_type.equals(abl.error_type)
        merged = abl.assign(model_full=prim.model_full.to_numpy())
        merged.to_parquet(C.CELLS_DIR / f"ablation_r{r:02d}_test.parquet", index=False)
        (C.CELLS_DIR / f"ablation_raw_r{r:02d}_calib.parquet").replace(C.CELLS_DIR / f"ablation_r{r:02d}_calib.parquet")


def step_sensitivity(args) -> None:
    jobs = [(f"sens{rate}", rate, r, ("full",), True) for rate in C.SENSITIVITY_RATES
            for r in range(C.N_REPLICATES_SECONDARY)]
    _save_counts("sensitivity", _run_jobs(jobs, args.workers))


def step_evaluate(args) -> None:
    from . import evaluation as E
    data = load_processed()
    setup = E.Setup(data, data["split"])
    prim = E.load("primary", range(C.N_REPLICATES))
    budget, _ = E.budget_analysis(setup, prim)
    budget.to_csv(C.TABLES_DIR / "budget_metrics.csv", index=False, float_format="%.5f")
    summary = {"primary": E.headline(budget)}
    E.conformal_analysis(setup, prim).to_csv(C.TABLES_DIR / "conformal.csv", index=False, float_format="%.5f")
    E.swap_recall_by_field(setup, prim).to_csv(C.TABLES_DIR / "swap_recall_by_field.csv", index=False, float_format="%.5f")

    abl = E.load("ablation", range(C.N_REPLICATES_SECONDARY))
    E.ablation_analysis(setup, abl, ["full"] + list(C.ABLATIONS)).to_csv(
        C.TABLES_DIR / "ablation.csv", index=False, float_format="%.5f")
    ii_tab, ii = E.individuality_analysis(data, data["split"], prim, abl)
    ii_tab.to_csv(C.TABLES_DIR / "individuality.csv", index=False, float_format="%.5f")
    summary["individuality"] = ii

    for rate in C.SENSITIVITY_RATES:
        reps = E.load(f"sens{rate}", range(C.N_REPLICATES_SECONDARY))
        tab, _ = E.budget_analysis(setup, reps)
        tab.to_csv(C.TABLES_DIR / f"sensitivity_{rate}.csv", index=False, float_format="%.5f")
        summary[f"sensitivity_{rate}"] = E.headline(tab)
    E.write_json(C.RESULTS_DIR / "summary.json", summary)
    log.info("primary: %s", summary["primary"])


def step_figures(args) -> None:
    from . import plots
    plots.make_all(C.TABLES_DIR, C.FIGURES_DIR)


STEPS = {"prepare": step_prepare, "primary": step_primary, "ablation": step_ablation,
         "sensitivity": step_sensitivity, "evaluate": step_evaluate, "figures": step_figures}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=list(STEPS) + ["all"])
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for name in (list(STEPS) if args.step == "all" else [args.step]):
        log.info("step %s", name)
        STEPS[name](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
