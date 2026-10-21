"""Features for the plausibility model, built from the visit table.

Column prefixes give the context group (the ablation drops whole groups):
own_                      same field at the patient's other visits
lab: lab_d: lab_x:        other lab values, change since previous visit, relations
vital: vital_d: vital_x:  same for vital signs
med: med_d: medcls:       doses, dose changes, active medication classes
date:                     the other form's date offset (date cells only)
base:                     age, sex, diagnosis groups
day, window_days          always kept
A cell's own value is never one of its features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

GROUPS = {"own": ("own_",), "lab": ("lab:", "lab_d:", "lab_x:"), "vital": ("vital:", "vital_d:", "vital_x:"),
          "med": ("med:", "med_d:", "medcls:"), "date": ("date:",), "base": ("base:",)}
ALWAYS = ("day", "window_days")
META = {"cell_id", "subject_id", "visit", "visit_idx", "modality", "field", "value", "y"}

# same-visit relations per target: (name, group, function of the visit row)
RELATIONS = {
    "sodium":      [("cl_plus_hco3", "lab", lambda w: w["chloride"] + w["bicarbonate"])],
    "chloride":    [("na_minus_hco3", "lab", lambda w: w["sodium"] - w["bicarbonate"])],
    "bicarbonate": [("na_minus_cl", "lab", lambda w: w["sodium"] - w["chloride"])],
    "hemoglobin":  [("hct_over_3", "lab", lambda w: w["hematocrit"] / 3)],
    "hematocrit":  [("hb_times_3", "lab", lambda w: w["hemoglobin"] * 3)],
    "sbp":         [("from_map_dbp", "vital", lambda w: 3 * w["map"] - 2 * w["dbp"])],
    "dbp":         [("from_map_sbp", "vital", lambda w: (3 * w["map"] - w["sbp"]) / 2)],
    "map":         [("from_sbp_dbp", "vital", lambda w: (w["sbp"] + 2 * w["dbp"]) / 3)],
}

ABLATION_DROPS = {
    "full": (),
    "cross_modal_only": ("own",),
    "own_history_only": ("lab", "vital", "med", "date", "base"),
    "no_labs": ("lab",),
    "no_vitals": ("vital",),
    "no_meds": ("med",),
    "no_dates": ("date",),
    "no_baseline": ("base",),
}


def model_scale(field: str, values) -> np.ndarray:
    v = np.asarray(values, float)
    if field in C.DATE_FIELDS or C.VALUE_FIELDS[field]["tf"] != "log":
        return v
    return np.log(np.clip(v, 1e-6, None))


def _own_history(cells: pd.DataFrame, usable: np.ndarray) -> pd.DataFrame:
    """Previous and next usable value of the field, days between, leave-one-out median, count."""
    c = cells.assign(usable=usable).sort_values(["subject_id", "field", "visit_idx"])
    y = c.y.where(c.usable)
    day = c.day.where(c.usable)
    keys = [c.subject_id, c.field]
    out = pd.DataFrame(index=c.index)
    out["own_prev"] = y.groupby(keys).transform(lambda s: s.shift(1).ffill())
    out["own_next"] = y.groupby(keys).transform(lambda s: s.shift(-1).bfill())
    out["own_dt_prev"] = c.day - day.groupby(keys).transform(lambda s: s.shift(1).ffill())
    out["own_dt_next"] = day.groupby(keys).transform(lambda s: s.shift(-1).bfill()) - c.day
    out["own_n"] = y.groupby(keys).transform("count") - c.usable.astype(int)
    loo = np.full(len(c), np.nan)
    pos = {i: k for k, i in enumerate(c.index)}
    for idx in c.groupby(["subject_id", "field"]).groups.values():
        vals = y.loc[idx].to_numpy()
        for j, i in enumerate(idx):
            others = np.delete(vals, j)
            others = others[~np.isnan(others)]
            if len(others):
                loo[pos[i]] = np.median(others)
    out["own_loo"] = loo
    return out.reindex(cells.index)


def build(cells: pd.DataFrame, baseline: pd.DataFrame, visit_ctx: pd.DataFrame,
          masked: np.ndarray | None = None) -> pd.DataFrame:
    """One row per cell with its target y (model scale; dates as days from nominal) and features.

    Masked cells keep their own row but are left out of every other cell's features.
    """
    cells = cells.reset_index(drop=True)
    usable = np.ones(len(cells), bool) if masked is None else ~np.asarray(masked, bool)
    is_date = cells.modality.eq("date").to_numpy()
    y = np.where(is_date, cells.value - cells.nominal_date, np.nan)
    for f in cells.field[~is_date].unique():
        m = (cells.field == f).to_numpy()
        y[m] = model_scale(f, cells.value[m])
    cells = cells.assign(y=y)

    key = ["subject_id", "visit_idx"]
    index = pd.MultiIndex.from_frame(cells[key].drop_duplicates().sort_values(key))
    use = cells[usable]
    wide = (use[use.modality != "date"].pivot_table(index=key, columns="field", values="value", aggfunc="first")
            .reindex(columns=list(C.VALUE_FIELDS)))
    delta = wide - wide.groupby(level=0).transform(lambda s: s.shift(1).ffill())
    dates = (use[use.modality == "date"].pivot_table(index=key, columns="field", values="y", aggfunc="first")
             .reindex(columns=list(C.DATE_FIELDS)))
    wide, delta, dates = wide.reindex(index), delta.reindex(index), dates.reindex(index)

    ctx = pd.DataFrame(index=index)
    for f in C.VALUE_FIELDS:
        grp = C.FIELD_MODALITY[f]
        ctx[f"{grp}:{f}"] = wide[f]
        ctx[f"{grp}_d:{f}"] = delta[f]
    for f in C.DATE_FIELDS:
        ctx[f"date:{f}"] = dates[f]
    for rels in RELATIONS.values():
        for name, grp, fn in rels:
            ctx[f"{grp}_x:{name}"] = fn(wide)

    rows = cells[key].merge(ctx.reset_index(), on=key, how="left").drop(columns=key)
    med = cells[["subject_id", "visit"]].merge(visit_ctx, on=["subject_id", "visit"], how="left")
    for col in [c for c in visit_ctx if c.startswith("med_")]:
        rows[f"medcls:{col[4:]}"] = med[col].to_numpy()
    base = cells[["subject_id"]].merge(baseline, on="subject_id", how="left")
    for col in [c for c in baseline if c != "subject_id"]:
        rows[f"base:{col}"] = base[col].to_numpy()
    rows.index = cells.index

    meta = cells[["cell_id", "subject_id", "visit", "visit_idx", "day", "window_days", "modality", "field", "value", "y"]]
    return pd.concat([meta, _own_history(cells, usable), rows], axis=1)


def columns_for(feats: pd.DataFrame, field: str, drop_groups: tuple[str, ...] = ()) -> list[str]:
    """Feature columns for one target field, minus its own value and minus dropped groups."""
    if field in C.DATE_FIELDS:
        own_value = {f"date:{field}"}
    else:
        m = C.FIELD_MODALITY[field]
        own_value = {f"{m}:{field}", f"{m}_d:{field}"}
    relations = {f"{grp}_x:{name}" for name, grp, _ in RELATIONS.get(field, [])}
    is_date = field in C.DATE_FIELDS
    cols = []
    for c in feats.columns:
        if c in META or c in own_value:
            continue
        if "_x:" in c and c not in relations:
            continue
        if is_date and not (c.startswith(("own_", "date:")) or c in ALWAYS):
            continue
        if not is_date and c.startswith("date:"):
            continue
        group = next((g for g, pre in GROUPS.items() if c.startswith(pre)), None)
        if group in drop_groups:
            continue
        cols.append(c)
    return cols
