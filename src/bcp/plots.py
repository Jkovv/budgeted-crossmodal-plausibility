"""Figures from the aggregate tables, in a light and a dark version."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from . import config as C  # noqa: E402

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
                  series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a", axis="#383835",
                 series=["#3987e5", "#d95926", "#199e70", "#c98500"]),
}
# colour follows the detector in every figure
DETECTORS = [("rules", "Range rules"), ("model_full", "Plausibility model"), ("combined", "Combined (rules first)"),
             ("delta", "Delta check")]
TYPE_LABELS = {"wrong_date": "Wrong visit date", "patient_swap": "Swapped between patients",
               "copy_previous": "Copied from previous visit", "unit_error": "Unit error",
               "decimal_slip": "Decimal slip", "digit_transposition": "Digit transposition"}
plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans", "sans-serif"]


def _style(ax, t, xgrid=False):
    ax.set_facecolor(t["surface"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(t["axis"])
    ax.tick_params(colors=t["muted"], length=0, labelsize=8.5)
    ax.yaxis.grid(True, color=t["grid"], linewidth=1)
    if xgrid:
        ax.xaxis.grid(True, color=t["grid"], linewidth=1)
    ax.set_axisbelow(True)


def _series(tab, det, metric):
    d = tab[(tab.detector == det) & (tab.metric == metric)].sort_values("budget")
    return d.estimate.to_numpy(), d.lo.to_numpy(), d.hi.to_numpy()


DRAW_ORDER = ["combined", "delta", "model_full", "rules"]     # combined underneath: it often equals the rules


def _lines(ax, tab, metric, t, scale=1.0):
    x = np.arange(len(C.BUDGETS))
    colour = {det: t["series"][k] for k, (det, _) in enumerate(DETECTORS)}
    for z, det in enumerate(DRAW_ORDER):
        if not ((tab.detector == det) & (tab.metric == metric)).any():
            continue
        est, lo, hi = (a * scale for a in _series(tab, det, metric))
        wide = det == "combined"
        ax.fill_between(x, lo, hi, color=colour[det], alpha=0.10, linewidth=0, zorder=2)
        ax.plot(x, est, color=colour[det], linewidth=4.5 if wide else 2, solid_capstyle="round", zorder=3 + z)
        ax.scatter(x, est, s=70 if wide else 36, color=colour[det], edgecolor=t["surface"], linewidth=2, zorder=3 + z)
    ax.set_xticks(x, [f"{b:g}" for b in C.BUDGETS])


def _legend(fig, t, y=0.995, ncol=4):
    handles = [Line2D([], [], color=t["series"][k], linewidth=2, marker="o", markersize=6,
                      markeredgecolor=t["surface"], label=lab) for k, (_, lab) in enumerate(DETECTORS)]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.01, y), ncol=ncol, frameon=False,
               labelcolor=t["ink"], fontsize=9)


def budget_figure(tab: pd.DataFrame, path: Path, theme: str) -> None:
    t = THEMES[theme]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), dpi=150, facecolor=t["surface"])
    for ax, metric, title, scale in ((axes[0], "yield", "Errors caught per 100 budgeted queries", 100),
                                     (axes[1], "precision", "Precision: share of raised queries that are errors", 100)):
        _style(ax, t)
        _lines(ax, tab, metric, t, scale)
        ax.set_title(title, loc="left", color=t["ink"], fontsize=10.5)
        ax.set_xlabel("Query budget (queries per patient per visit)", color=t["muted"], fontsize=8.5)
        ax.set_ylim(0, 100)
        ax.axvline(C.BUDGETS.index(C.PRIMARY_BUDGET), color=t["axis"], linewidth=1, zorder=1)
    axes[0].text(C.BUDGETS.index(C.PRIMARY_BUDGET) + 0.05, 96, "primary budget", color=t["muted"], fontsize=7.5, va="top")
    _legend(fig, t)
    fig.text(0.01, 0.01, "Held-out patients, 20 injection replicates, 2% transcription errors. Bands: 95% patient "
             "bootstrap interval. Range rules can only raise queries on values that break a rule.",
             color=t["muted"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    fig.savefig(path, facecolor=t["surface"])
    plt.close(fig)


def recall_by_type_figure(tab: pd.DataFrame, path: Path, theme: str) -> None:
    t = THEMES[theme]
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.4), dpi=150, facecolor=t["surface"], sharey=True)
    for ax, et in zip(axes.flat, C.ERROR_TYPES):
        _style(ax, t)
        _lines(ax, tab, f"recall|type:{et}", t)
        ax.set_title(TYPE_LABELS[et], loc="left", color=t["ink"], fontsize=10)
        ax.set_ylim(0, 1.02)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1], ["0%", "25%", "50%", "75%", "100%"])
    for ax in axes[1]:
        ax.set_xlabel("Queries per patient per visit", color=t["muted"], fontsize=8.5)
    _legend(fig, t)
    fig.text(0.01, 0.01, "Recall: share of injected errors of that type among the raised queries. Bands: 95% "
             "patient bootstrap interval.", color=t["muted"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))
    fig.savefig(path, facecolor=t["surface"])
    plt.close(fig)


ABLATION_LABELS = {"model_full": "Full model", "model_cross_modal_only": "Cross-modal only (no own history)",
                   "model_own_history_only": "Own history only", "model_no_labs": "Without labs",
                   "model_no_vitals": "Without vital signs", "model_no_meds": "Without medications",
                   "model_no_dates": "Without dates", "model_no_baseline": "Without baseline"}


def ablation_figure(abl: pd.DataFrame, path: Path, theme: str) -> None:
    t = THEMES[theme]
    d = abl[(abl.metric == "yield") & (abl.budget == C.PRIMARY_BUDGET)].set_index("detector").reindex(list(ABLATION_LABELS))
    fig, ax = plt.subplots(figsize=(8.5, 4.2), dpi=150, facecolor=t["surface"])
    _style(ax, t)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=t["grid"], linewidth=1)
    y = np.arange(len(d))[::-1]
    col = t["series"][1]
    ax.barh(y, d.estimate * 100, height=0.5, color=col, zorder=3)
    ax.errorbar(d.estimate * 100, y, xerr=[(d.estimate - d.lo) * 100, (d.hi - d.estimate) * 100], fmt="none",
                ecolor=t["ink2"], elinewidth=1, capsize=0, zorder=4)
    for yi, (e, h) in zip(y, zip(d.estimate, d.hi)):
        ax.text(h * 100 + 1, yi, f"{e * 100:.1f}", va="center", fontsize=8, color=t["ink2"])
    ax.set_yticks(y, [ABLATION_LABELS[i] for i in d.index], color=t["ink2"], fontsize=9)
    ax.set_xlabel(f"Errors caught per 100 queries at {C.PRIMARY_BUDGET} queries per patient per visit",
                  color=t["muted"], fontsize=8.5)
    ax.set_title("Which context the plausibility model needs", loc="left", color=t["ink"], fontsize=10.5)
    fig.text(0.01, 0.01, "10 replicates, same injections for every variant. Whiskers: 95% patient bootstrap interval.",
             color=t["muted"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, facecolor=t["surface"])
    plt.close(fig)


def conformal_figure(conf: pd.DataFrame, path: Path, theme: str) -> None:
    t = THEMES[theme]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0), dpi=150, facecolor=t["surface"])
    x = np.arange(len(DETECTORS))
    for ax, metric, title in ((axes[0], "false_query_rate", "Achieved false-query rate"),
                              (axes[1], "errors_caught", "Errors caught (held-out set, per replicate)")):
        _style(ax, t)
        for j, a in enumerate(C.FDR_TARGETS):
            off = (j - 0.5) * 0.3
            for k, (det, _) in enumerate(DETECTORS):
                r = conf[(conf.detector == det) & (conf.target == a) & (conf.metric == metric)]
                if r.empty:
                    continue
                r = r.iloc[0]
                ax.plot([k + off, k + off], [r.lo, r.hi], color=t["ink2"], linewidth=1, zorder=3)
                ax.scatter([k + off], [r.estimate], s=44, color=t["series"][k], edgecolor=t["surface"], linewidth=2,
                           marker="o" if j == 0 else "D", zorder=4)
            if metric == "false_query_rate":
                ax.axhline(a, color=t["axis"], linewidth=1, zorder=1)
                ax.text(2.5, a, f"target {a:.0%}", color=t["muted"], fontsize=7.5, va="bottom", ha="center")
        ax.set_xticks(x, [lab for _, lab in DETECTORS], fontsize=8, color=t["ink2"])
        ax.set_title(title, loc="left", color=t["ink"], fontsize=10.5)
    axes[0].set_ylim(0, None)
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    handles = [Line2D([], [], color=t["muted"], marker=m, linestyle="", markersize=7, label=f"target {a:.0%}")
               for a, m in zip(C.FDR_TARGETS, ("o", "D"))]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.01, 0.995), ncol=2, frameon=False,
               labelcolor=t["ink"], fontsize=9)
    fig.text(0.01, 0.01, "Conformal p-values from clean visits of training patients, Benjamini-Hochberg within each of 5 "
             "pseudo-sites. Mean over 20 replicates, whiskers 2.5 to 97.5% of replicates. The guarantee assumes "
             "clean calibration data.", color=t["muted"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    fig.savefig(path, facecolor=t["surface"])
    plt.close(fig)


def individuality_figure(ii: pd.DataFrame, path: Path, theme: str, summary: dict | None = None) -> None:
    t = THEMES[theme]
    d = ii[ii.auroc_full.notna()].copy()
    fig, ax = plt.subplots(figsize=(9, 5.4), dpi=150, facecolor=t["surface"])
    _style(ax, t, xgrid=True)
    for r in d.itertuples():
        ax.plot([r.index_of_individuality] * 2, [r.auroc_own_history_only, r.auroc_full], color=t["axis"],
                linewidth=1, zorder=2)
    ax.scatter(d.index_of_individuality, d.auroc_own_history_only, s=34, facecolor=t["surface"], edgecolor=t["muted"],
               linewidth=1.5, zorder=3, label="Own history only")
    test = d[d.in_test]
    rest = d[~d.in_test]
    ax.scatter(rest.index_of_individuality, rest.auroc_full, s=34, color=t["series"][1], alpha=0.55,
               edgecolor=t["surface"], linewidth=1.5, zorder=4, label="Full model")
    ax.scatter(test.index_of_individuality, test.auroc_full, s=90, color=t["series"][1], edgecolor=t["ink"],
               linewidth=1.5, zorder=5, label="Full model, field in the pre-registered test")
    line = test.sort_values("index_of_individuality")
    ax.plot(line.index_of_individuality, line.line_from_own_history, color=t["muted"], linewidth=1, zorder=1)
    show = set(test.field) | set(d.nlargest(3, "gain_over_own_history").field) |         set(d.nsmallest(1, "index_of_individuality").field) | set(d.nlargest(1, "index_of_individuality").field)
    for r in d[d.field.isin(show)].itertuples():
        ax.annotate(C.VALUE_FIELDS[r.field]["label"], (r.index_of_individuality, r.auroc_full), xytext=(6, 4),
                    textcoords="offset points", fontsize=7.5, color=t["ink2"])
    ax.axhline(0.5, color=t["axis"], linewidth=1, zorder=1)
    ax.set_xlabel("Index of individuality (within-patient SD / between-patient SD, training patients)",
                  color=t["muted"], fontsize=8.5)
    ax.set_ylabel("AUROC, swapped against clean values", color=t["muted"], fontsize=8.5)
    ax.set_title("Swap detectability against the index of individuality", loc="left", color=t["ink"], fontsize=10.5)
    ax.legend(loc="lower left", frameon=False, labelcolor=t["ink"], fontsize=8)
    if summary:
        s, e = summary, summary["exploratory_all_fields"]
        fig.text(0.01, 0.01, f"Pre-registered test ({s['n_fields']} fields with at least {C.II_MIN_SWAPS} swapped values): "
                 f"rho = {s['spearman_rho']:.2f}, one-sided p = {s['p_one_sided']:.2f}. Exploratory, all "
                 f"{e['n_fields']} fields: rho = {e['spearman_rho']:.2f}, p = {e['p_one_sided']:.3f}.\n"
                 "Line: fit to the own-history-only AUROC of the tested fields.", color=t["muted"], fontsize=7.5,
                 linespacing=1.5)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, facecolor=t["surface"])
    plt.close(fig)


def make_all(tables: Path, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    budget = pd.read_csv(tables / "budget_metrics.csv")
    abl = pd.read_csv(tables / "ablation.csv")
    conf = pd.read_csv(tables / "conformal.csv")
    ii = pd.read_csv(tables / "individuality.csv")
    summary_path = tables.parent / "summary.json"
    ii_summary = json.loads(summary_path.read_text())["individuality"] if summary_path.exists() else None
    made = []
    for theme in ("light", "dark"):
        sfx = "" if theme == "light" else "_dark"
        for name, fn, tab in (("budget_comparison", budget_figure, budget), ("recall_by_type", recall_by_type_figure, budget),
                              ("ablation", ablation_figure, abl), ("conformal", conformal_figure, conf),
                              ("individuality", individuality_figure, ii)):
            p = out / f"{name}{sfx}.png"
            if fn is individuality_figure:
                fn(tab, p, theme, ii_summary)
            else:
                fn(tab, p, theme)
            made.append(p)
    return made
