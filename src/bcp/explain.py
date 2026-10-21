"""Query text for raised cells.

One sentence per query: what does not fit and which recorded values it conflicts with.
Never a suggested value; fixing the entry is up to the site.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import config as C
from . import features as F

ASK = "Please check against the source document."
FORM_LABEL = {"lab_date": "laboratory sample date", "vital_date": "vital signs date"}
RELATED = {"sodium": ["chloride", "bicarbonate"], "chloride": ["sodium", "bicarbonate"], "bicarbonate": ["sodium", "chloride"],
           "hemoglobin": ["hematocrit"], "hematocrit": ["hemoglobin"], "sbp": ["map", "dbp"], "dbp": ["map", "sbp"],
           "map": ["sbp", "dbp"]}
CLASS_LABEL = {"anti_infective": "anti-infective", "vasopressor": "vasopressor", "insulin": "insulin",
               "loop_diuretic": "loop diuretic", "potassium_suppl": "potassium supplement", "anticoagulant": "anticoagulant",
               "steroid": "corticosteroid", "sedative": "sedative", "iv_fluid": "IV fluid"}


def fmt(field: str, v: float) -> str:
    """The value as written: the field's decimals, more if the entry has them (0.04 g, 9.8)."""
    d = C.VALUE_FIELDS[field]["dec"]
    if round(v, d) != round(v, 6):
        return np.format_float_positional(round(v, 6), trim="-")
    return f"{v:,.{d}f}" if abs(v) >= 1000 else f"{v:.{d}f}"


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def value_phrase(field: str, v: float) -> str:
    d = C.VALUE_FIELDS[field]
    name = d["label"] if d["label"] == "SpO2" else d["label"].lower()
    return f"{name} {fmt(field, v)} {d['unit']}"


def date_str(day_number: float) -> str:
    return str(dt.date(1970, 1, 1) + dt.timedelta(days=int(day_number)))


def _head(row) -> str:
    if row.field in C.DATE_FIELDS:
        return f"The {FORM_LABEL[row.field]} {date_str(row.value)} for visit {row.visit}"
    return f"{value_phrase(row.field, row.value)[0].upper()}{value_phrase(row.field, row.value)[1:]} at visit {row.visit}"


def rule_text(row, nominal_date: float, window: int, prev_date: float | None) -> str:
    if row.field in C.DATE_FIELDS:
        off = int(row.value - nominal_date)
        if abs(off) > window:
            side = "after" if off > 0 else "before"
            return f"{_head(row)} is {_days(abs(off))} {side} the scheduled date (window {_days(window)}). {ASK}"
        return f"{_head(row)} is earlier than the date recorded for the previous visit ({date_str(prev_date)}). {ASK}"
    lo, hi = C.VALUE_FIELDS[row.field]["edc"]
    unit = C.VALUE_FIELDS[row.field]["unit"]
    return f"{_head(row)} is outside the expected range {fmt(row.field, lo)} to {fmt(row.field, hi)} {unit}. {ASK}"


def delta_text(row, prev_value: float, prev_visit: str, k: float) -> str:
    return (f"{_head(row)} changed from {fmt(row.field, prev_value)} at visit {prev_visit}, "
            f"{k:.1f} times the usual change between visits. {ASK}")


def _raw(field: str, y: float) -> float:
    if field in C.DATE_FIELDS or C.VALUE_FIELDS[field]["tf"] != "log":
        return y
    return float(np.exp(y))


def model_evidence(frow: pd.Series, contrib: pd.Series, sign: float, sigma: float, nominal: float) -> list[str]:
    """Recorded values that pull against the flagged one: the patient's own adjacent values, then the
    strongest same-visit context (TreeSHAP contribution of at least 0.25 robust SD)."""
    f = frow.field
    ev = []
    for col, when in (("own_prev", "earlier"), ("own_next", "later")):
        y = frow[col]
        days = frow["own_dt_prev" if col == "own_prev" else "own_dt_next"]
        if pd.notna(y) and abs(y - frow.y) >= 2 * sigma:
            if f in C.DATE_FIELDS:
                continue
            ev.append(f"{value_phrase(f, _raw(f, y))} {_days(int(days))} {when}")
    against = contrib[(np.sign(contrib) == -sign) & (contrib.abs() >= 0.25)].abs().sort_values(ascending=False)
    used = set()
    for col in against.index:
        if len(ev) >= 3:
            break
        phrase = _context_phrase(f, col, frow, nominal, used)
        if phrase:
            ev.append(phrase)
    return ev


def _context_phrase(target: str, col: str, frow: pd.Series, nominal: float, used: set) -> str | None:
    v = frow[col]
    if pd.isna(v) or col.startswith(("own_", "base:age", "base:female")) or col in F.ALWAYS:
        return None
    if "_x:" in col:
        parts = [p for p in RELATED.get(target, []) if pd.notna(frow.get(f"{C.FIELD_MODALITY[p]}:{p}")) and p not in used]
        used.update(parts)
        vals = [value_phrase(p, frow[f"{C.FIELD_MODALITY[p]}:{p}"]) for p in parts]
        return " and ".join(vals) + " at the same visit" if vals else None
    grp, name = col.split(":", 1)
    if grp in ("lab", "vital", "med") and name not in used:
        used.add(name)
        return f"{value_phrase(name, v)} at the same visit"
    if grp == "medcls":
        return f"{'an active' if v else 'no'} {CLASS_LABEL[name]} order"
    if grp == "base" and name.startswith("dx_"):
        return f"{'a' if v else 'no'} {name[3:].replace('_', ' ')} diagnosis"
    if grp == "date":
        return f"the {FORM_LABEL[name]} {date_str(nominal + v)} for the same visit"
    return None


def model_text(row, evidence: list[str]) -> str:
    clauses = []
    if row.field in C.VALUE_FIELDS:
        lo, hi = C.VALUE_FIELDS[row.field]["edc"]
        if not lo <= row.value <= hi:
            clauses.append(f"is outside the expected range {fmt(row.field, lo)} to {fmt(row.field, hi)} "
                           f"{C.VALUE_FIELDS[row.field]['unit']}")
    if evidence:
        clauses.append(f"does not fit the rest of the record: {', '.join(evidence)}")
    if not clauses:
        clauses.append("is unusual for this patient's record")
    return f"{_head(row)} {' and '.join(clauses)}. {ASK}"


def examples(data: dict, split: pd.Series, rep: int = 0, budget: float = C.PRIMARY_BUDGET) -> pd.DataFrame:
    """Query text for every cell each detector would raise at the budget, in one replicate."""
    from . import stats as S
    from .delta import DeltaCheck
    from .evaluation import tie_seed
    from .inject import inject
    from .plausibility import PlausibilityModel, score_with_explaining_away
    from .rules import range_scores
    from .run import injection_seed

    cells, base, ctx = data["cells"], data["baseline"], data["visit_context"]
    cor, truth, _ = inject(cells, split, C.ERROR_RATE, injection_seed(C.ERROR_RATE, rep))
    is_train = cor.subject_id.map(split).eq("train").to_numpy()
    train, test = cor[is_train].reset_index(drop=True), cor[~is_train].reset_index(drop=True)
    err = test.cell_id.map(truth.set_index("cell_id").error_type)
    Q = int(round(budget * len(test[["subject_id", "visit"]].drop_duplicates())))

    model = PlausibilityModel("full", seed=C.SEED + rep).fit(train, base, ctx)
    z = score_with_explaining_away(model, test, base, ctx).z.to_numpy()
    feats = F.build(test, base, ctx)
    rules = range_scores(test)
    delta = DeltaCheck().fit(train)
    dscore = delta.score(test)
    order_f = test.sort_values(["subject_id", "field", "visit_idx"])
    prev_val = order_f.groupby(["subject_id", "field"]).value.shift(1).reindex(test.index)
    prev_visit = order_f.groupby(["subject_id", "field"]).visit.shift(1).reindex(test.index)

    out = []
    picks = {"rules": np.where(rules > 0, rules, np.nan), "delta": dscore, "model_full": np.abs(z)}
    for det, score in picks.items():
        order = S.rank_order(score, np.random.default_rng(tie_seed(rep, det)))[:Q]
        for i in order:
            row = test.loc[i]
            if det == "rules":
                text = rule_text(row, row.nominal_date, int(row.window_days), prev_val[i])
            elif det == "delta":
                text = delta_text(row, prev_val[i], prev_visit[i], dscore[i])
            else:
                m = model.models[row.field]
                frow = feats.loc[i]
                if m.simple:
                    phi, sigma = pd.Series(dtype=float), m.floor * m.scale
                else:
                    X = feats.loc[[i], m.cols].to_numpy(float)
                    phi = pd.Series(m.mu.predict(X, pred_contrib=True)[0, :-1], index=m.cols)
                    sigma = max(1.4826 * m.sigma.predict(X)[0], m.floor) * m.scale
                text = model_text(row, model_evidence(frow, phi, np.sign(z[i]), sigma, row.nominal_date))
            out.append(dict(detector=det, rank=len([o for o in out if o["detector"] == det]) + 1, cell_id=int(row.cell_id),
                            field=row.field, visit=row.visit, error_type=err[i] if pd.notna(err[i]) else "none",
                            query=text))
    return pd.DataFrame(out)
