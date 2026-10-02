"""Deterministic condition evaluator. No LLM, no I/O.

Snapshot shape (Open-Meteo with timezone=auto, so all times are location-local):
  {"current": {"time": "2026-09-04T07:30", <field>: v, ...},
   "hourly":  {"time": ["2026-09-04T00:00", ...], <field>: [v, ...], ...},
   "daily":   {"time": ["2026-09-04", ...], <field>: [v, ...], ...},
   "now_local": "2026-09-04T07:30"}   # location-local now; falls back to current.time if absent

Every node evaluates to TRUE, FALSE or UNKNOWN (Kleene logic). Missing or null
data is UNKNOWN and never silently becomes TRUE, FALSE or zero.
"""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"

_CMP = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
        "==": operator.eq, "!=": operator.ne}
_AGG = {"max": max, "min": min, "sum": sum, "mean": lambda xs: sum(xs) / len(xs)}


@dataclass
class EvalContext:
    snapshot: dict[str, Any]
    vocabulary: dict[str, Any]
    time_reference: str | None = None   # a vocabulary.time_words tag from the parsed intent


@dataclass
class Result:
    value: str
    evidence: dict[str, Any] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)


class MissingEvidence(Exception):
    pass


def evaluate(node: dict, ctx: EvalContext) -> Result:
    (kind, body), = node.items()
    if kind in ("all", "any"):
        kids = [evaluate(c, ctx) for c in body]   # no short-circuit: keep all evidence and trace
        vals = [k.value for k in kids]
        if kind == "all":
            v = FALSE if FALSE in vals else UNKNOWN if UNKNOWN in vals else TRUE
        else:
            v = TRUE if TRUE in vals else UNKNOWN if UNKNOWN in vals else FALSE
        return _merge(v, kids, {"node": kind, "result": v})
    if kind == "not":
        k = evaluate(body, ctx)
        v = {TRUE: FALSE, FALSE: TRUE, UNKNOWN: UNKNOWN}[k.value]
        return _merge(v, [k], {"node": "not", "result": v})
    if kind == "compare":
        return _compare(body, ctx)
    if kind == "window_agg":
        return _compare({**body, "source": "hourly"}, ctx)
    if kind == "score":
        return _score(body, ctx)
    raise ValueError(f"unknown condition type {kind!r}")


def _merge(value, kids, own) -> Result:
    ev: dict[str, Any] = {}
    tr = [own]
    for k in kids:
        ev.update(k.evidence)
        tr.extend(k.trace)
    return Result(value, ev, tr)


# ---------- value reading ----------

def _now(ctx: EvalContext) -> datetime | None:
    t = ctx.snapshot.get("now_local") or (ctx.snapshot.get("current") or {}).get("time")
    try:
        return datetime.fromisoformat(t)
    except (TypeError, ValueError):
        return None


def resolve_window(window: dict, ctx: EvalContext) -> tuple[datetime, datetime] | str:
    """Return [start, end) in location-local time, or a string explaining why it can't be resolved."""
    now = _now(ctx)
    if now is None:
        return "snapshot has no usable current.time"
    if "from_time_reference" in window:
        tag = ctx.time_reference
        if not tag:
            return "SOP needs a time window from the user's time reference but none was given"
        word = ctx.vocabulary.get("time_words", {}).get(tag)
        if not word or "window" not in word:
            return f"time reference {tag!r} has no window defined in vocabulary.time_words"
        spec = word["window"]
    else:
        spec = window["fixed_local"]
    day = now.date() + timedelta(days=1 if spec.get("day", "today") == "tomorrow" else 0)
    midnight = datetime(day.year, day.month, day.day)
    return (midnight + timedelta(hours=int(spec["start"][:2])),
            midnight + timedelta(hours=int(spec["end"][:2])))


def read_value(spec: dict, ctx: EvalContext) -> tuple[float | None, str | None]:
    """Return (value, None) or (None, reason-it-is-unknown)."""
    src, name = spec["source"], spec["field"]
    snap = ctx.snapshot
    if src == "current":
        v = (snap.get("current") or {}).get(name)
        return (v, None) if _is_num(v) else (None, f"current.{name} missing or null")
    if src == "daily":
        daily, now = snap.get("daily") or {}, _now(ctx)
        if now is None or name not in daily or "time" not in daily:
            return None, f"daily.{name} missing"
        day = (now.date() + timedelta(days=1 if spec.get("day") == "tomorrow" else 0)).isoformat()
        if day not in daily["time"]:
            return None, f"daily has no row for {day}"
        v = daily[name][daily["time"].index(day)]
        return (v, None) if _is_num(v) else (None, f"daily.{name} for {day} is null")
    # hourly: strict window aggregation
    win = resolve_window(spec["window"], ctx)
    if isinstance(win, str):
        return None, win
    start, end = win
    hourly = snap.get("hourly") or {}
    if name not in hourly or "time" not in hourly:
        return None, f"hourly.{name} missing"
    by_time = dict(zip(hourly["time"], hourly[name]))
    vals, t = [], start
    while t < end:
        key = t.strftime("%Y-%m-%dT%H:%M")
        v = by_time.get(key)
        if not _is_num(v):
            return None, f"hourly.{name} missing/null at {key} inside window {start:%H:%M}-{end:%H:%M}"
        vals.append(v)
        t += timedelta(hours=1)
    return _AGG[spec["agg"]](vals), None


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------- leaves ----------

def _compare(body: dict, ctx: EvalContext) -> Result:
    v, why = read_value(body, ctx)
    entry = {"node": "compare" if body["source"] != "hourly" else "window_agg",
             "field": body["field"], "source": body["source"], "op": body["op"],
             "threshold": body["value"], "value": v}
    if body.get("agg"):
        entry["agg"] = body["agg"]
    if v is None:
        return Result(UNKNOWN, {}, [{**entry, "result": UNKNOWN, "reason": why}])
    op = body["op"]
    ok = (v in body["value"]) if op == "in" else (v not in body["value"]) if op == "not_in" \
        else _CMP[op](v, body["value"])
    res = TRUE if ok else FALSE
    return Result(res, {body["as"]: v} if body.get("as") else {}, [{**entry, "result": res}])


def _score(body: dict, ctx: EvalContext) -> Result:
    """Weighted score: sum(weight * points) / sum(weight). Any UNKNOWN term makes the whole score UNKNOWN."""
    prefix = body.get("as")
    k_score, k_label = (f"{prefix}_value", f"{prefix}_label") if prefix else ("score", "label")
    ev: dict[str, Any] = {}
    terms_trace, unknown = [], False
    total = wsum = 0.0
    for t in body["terms"]:
        v, why = read_value(t, ctx)
        wsum += t["weight"]
        if v is None:
            unknown = True
            terms_trace.append({"as": t["as"], "field": t["field"], "value": None, "reason": why})
            continue
        pts = next((b["points"] for b in t["bands"] if _CMP[b["op"]](v, b["value"])), t["default_points"])
        total += t["weight"] * pts
        ev[t["as"]] = v
        terms_trace.append({"as": t["as"], "field": t["field"], "value": v, "points": pts,
                            "weight": t["weight"], "contribution": t["weight"] * pts})
    entry = {"node": "score", "terms": terms_trace}
    if unknown:
        return Result(UNKNOWN, {}, [{**entry, "result": UNKNOWN}])
    score = total / wsum
    m = body["match"]
    res = TRUE if _CMP[m["op"]](score, m["value"]) else FALSE
    ev[k_score] = score
    label = next((lb["label"] for lb in body.get("labels", []) if _CMP[lb["op"]](score, lb["value"])), None)
    if label is not None:
        ev[k_label] = label
    return Result(res, ev, [{**entry, "score": score, "label": label, "result": res}])


# ---------- advice rendering ----------

def fmt_number(x: float) -> str:
    """Single formatting rule for every number code puts in a reply (the verifier relies on it)."""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def render_advice(template: str, evidence: dict[str, Any]) -> str:
    def sub(m):
        k = m.group(1)
        if k not in evidence:
            raise MissingEvidence(k)
        v = evidence[k]
        return fmt_number(v) if _is_num(v) else str(v)
    return re.sub(r"\{(\w+)\}", sub, template)
