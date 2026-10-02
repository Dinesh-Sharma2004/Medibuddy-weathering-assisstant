"""SOP file loader and validator.

Re-read from disk on every request by the graph (see graph nodes). All
validation problems are collected and raised together as one SOPError so the
author sees every mistake at once.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CMP_OPS = {">", ">=", "<", "<=", "==", "!="}
SET_OPS = {"in", "not_in"}
AGGS = {"max", "min", "mean", "sum"}
SOURCES = {"current", "hourly", "daily"}
DAYS = {"today", "tomorrow"}
DIMENSIONS = ("activities", "groups", "question_types")
REQUIRED_MESSAGES = (
    "no_guidance", "out_of_scope", "insufficient_intent", "ask_location",
    "location_unresolved", "weather_unavailable", "data_unavailable", "no_prior_decision",
    "unknown_disclosure",
)
# Only this message may contain placeholders (filled by code): the UNKNOWN-SOP disclosure line.
MESSAGE_PLACEHOLDERS = {"unknown_disclosure": {"sop_id", "title", "severity"}}
SOP_KEYS = {"id", "title", "category", "severity", "priority", "applies_to", "requires",
            "condition", "advice", "rationale", "edge_cases", "override"}
SOP_REQUIRED = SOP_KEYS - {"edge_cases", "override"}
_HOUR_RE = re.compile(r"^(?:[01]\d|2[0-3]):00$|^24:00$")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class SOPError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid SOP file:\n  - " + "\n  - ".join(errors))


@dataclass
class SOP:
    id: str
    title: str
    category: str
    severity: str
    priority: int
    applies_to: dict[str, Any]
    requires: list[dict[str, str]]
    condition: dict[str, Any]
    advice: str
    rationale: str
    edge_cases: list[str] = field(default_factory=list)
    override: bool = False


@dataclass
class SOPSet:
    meta: dict[str, Any]
    messages: dict[str, str]
    vocabulary: dict[str, dict[str, Any]]
    sops: list[SOP]

    @property
    def id_regex(self) -> "re.Pattern[str]":
        return re.compile(self.meta["id_pattern"])

    @property
    def severities(self) -> list[str]:
        return self.meta["severities"]

    def severity_rank(self, severity: str) -> int:
        return self.severities.index(severity)

    def required_fields(self) -> dict[str, list[str]]:
        """Union of `requires` over all SOPs, grouped by source."""
        out: dict[str, set[str]] = {}
        for s in self.sops:
            for r in s.requires:
                out.setdefault(r["source"], set()).add(r["field"])
        return {k: sorted(v) for k, v in out.items()}


def load_sops(path: str | Path) -> SOPSet:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SOPError([f"YAML syntax error: {e}"]) from e
    except OSError as e:
        raise SOPError([f"cannot read SOP file: {e}"]) from e
    return validate_sops(raw)


def validate_sops(raw: Any) -> SOPSet:
    errors: list[str] = []
    if not isinstance(raw, dict):
        raise SOPError(["top level must be a mapping"])
    for key in ("meta", "messages", "vocabulary", "sops"):
        if key not in raw:
            errors.append(f"missing top-level section '{key}'")
    extra = set(raw) - {"meta", "messages", "vocabulary", "sops"}
    if extra:
        errors.append(f"unknown top-level section(s): {sorted(extra)}")
    if errors:
        raise SOPError(errors)

    meta = _validate_meta(raw["meta"], errors)
    messages = _validate_messages(raw["messages"], errors)
    vocab = _validate_vocab(raw["vocabulary"], errors)
    dtr = meta.get("default_time_reference")
    tw = vocab.get("time_words", {}) if isinstance(vocab, dict) else {}
    if dtr is not None and not (isinstance(tw.get(dtr), dict) and "window" in tw[dtr]):
        errors.append(f"meta.default_time_reference {dtr!r} must be a vocabulary.time_words tag that has a window")
    sops: list[SOP] = []
    if not isinstance(raw["sops"], list) or not raw["sops"]:
        errors.append("'sops' must be a non-empty list")
    else:
        seen: set[str] = set()
        for i, item in enumerate(raw["sops"]):
            sop = _validate_sop(item, i, meta, vocab, seen, errors)
            if sop:
                sops.append(sop)
    if errors:
        raise SOPError(errors)
    return SOPSet(meta, messages, vocab, sops)


def _validate_meta(meta: Any, errors: list[str]) -> dict:
    if not isinstance(meta, dict):
        errors.append("meta must be a mapping")
        return {"severities": []}
    allowed = {"schema_version", "severities", "disclose_unknown_from", "default_time_reference", "id_pattern"}
    for k in set(meta) - allowed:
        errors.append(f"meta: unknown field '{k}'")
    for k in allowed:
        if k not in meta:
            errors.append(f"meta: missing '{k}'")
    sev = meta.get("severities")
    if not (isinstance(sev, list) and sev and all(isinstance(x, str) for x in sev)) \
            or (isinstance(sev, list) and len(set(sev)) != len(sev)):
        errors.append("meta.severities must be a non-empty list of unique strings, ordered low to high")
        meta = {**meta, "severities": []}
    elif meta.get("disclose_unknown_from") not in sev:
        errors.append(f"meta.disclose_unknown_from must be one of severities {sev}")
    pat = meta.get("id_pattern")
    if isinstance(pat, str):
        try:
            re.compile(pat)
        except re.error as e:
            errors.append(f"meta.id_pattern is not a valid regex: {e}")
    elif "id_pattern" in meta:
        errors.append("meta.id_pattern must be a regex string (the namespace every SOP id belongs to)")
    return meta


def _validate_messages(msgs: Any, errors: list[str]) -> dict:
    if not isinstance(msgs, dict):
        errors.append("messages must be a mapping")
        return {}
    for k in REQUIRED_MESSAGES:
        if not isinstance(msgs.get(k), str) or not msgs[k].strip():
            errors.append(f"messages.{k} is missing or empty")
        else:
            ok = MESSAGE_PLACEHOLDERS.get(k, set())
            for ph in _PLACEHOLDER_RE.findall(msgs[k]):
                if ph not in ok:
                    errors.append(f"messages.{k}: placeholder {{{ph}}} not allowed (allowed: {sorted(ok)})")
    for k in set(msgs) - set(REQUIRED_MESSAGES):
        errors.append(f"messages: unknown message '{k}'")
    return msgs


def _validate_vocab(vocab: Any, errors: list[str]) -> dict:
    if not isinstance(vocab, dict):
        errors.append("vocabulary must be a mapping")
        return {}
    for dim in (*DIMENSIONS, "time_words"):
        sect = vocab.get(dim)
        if not isinstance(sect, dict) or not sect:
            errors.append(f"vocabulary.{dim} must be a non-empty mapping of tag -> definition")
            continue
        for tag, d in sect.items():
            if dim == "time_words":
                if not (isinstance(d, dict) and isinstance(d.get("description"), str)):
                    errors.append(f"vocabulary.time_words.{tag}: needs a mapping with 'description'")
                    continue
                for k in set(d) - {"description", "window"}:
                    errors.append(f"vocabulary.time_words.{tag}: unknown field '{k}'")
                if "window" in d:
                    _validate_window(d["window"], f"vocabulary.time_words.{tag}.window", errors,
                                     allow_reference=False)
            elif not isinstance(d, str) or not d.strip():
                errors.append(f"vocabulary.{dim}.{tag}: description must be a non-empty string")
    for k in set(vocab) - {*DIMENSIONS, "time_words"}:
        errors.append(f"vocabulary: unknown section '{k}'")
    return vocab


def _validate_window(w: Any, where: str, errors: list[str], allow_reference: bool = True) -> None:
    """A window is {fixed_local: {start, end, day?}}, {from_time_reference: true} (conditions only),
    or, inside vocabulary.time_words, the bare {start, end, day?} body."""
    if not isinstance(w, dict):
        errors.append(f"{where}: window must be a mapping")
        return
    if "fixed_local" in w or "from_time_reference" in w:
        if not allow_reference:
            errors.append(f"{where}: time_words windows are written as plain {{start, end, day}}")
            return
        if len(w) != 1:
            errors.append(f"{where}: give exactly one of fixed_local / from_time_reference")
            return
        if "from_time_reference" in w:
            if w["from_time_reference"] is not True:
                errors.append(f"{where}.from_time_reference must be true")
            return
        w = w["fixed_local"]
        where += ".fixed_local"
        if not isinstance(w, dict):
            errors.append(f"{where} must be a mapping")
            return
    elif allow_reference:
        errors.append(f"{where}: window must contain fixed_local or from_time_reference")
        return
    for k in set(w) - {"start", "end", "day"}:
        errors.append(f"{where}: unknown field '{k}'")
    for k in ("start", "end"):
        if not (isinstance(w.get(k), str) and _HOUR_RE.match(w[k])):
            errors.append(f"{where}.{k} must be a whole hour 'HH:00' (end may be '24:00')")
    if all(isinstance(w.get(k), str) and _HOUR_RE.match(w[k]) for k in ("start", "end")):
        if int(w["start"][:2]) >= int(w["end"][:2]):
            errors.append(f"{where}: start must be before end (start inclusive, end exclusive)")
    if "day" in w and w["day"] not in DAYS:
        errors.append(f"{where}.day must be one of {sorted(DAYS)}")


def _validate_sop(item, idx, meta, vocab, seen, errors) -> SOP | None:
    where = f"sops[{idx}]"
    if not isinstance(item, dict):
        errors.append(f"{where}: must be a mapping")
        return None
    sid = item.get("id")
    where = f"sop '{sid}'" if isinstance(sid, str) else where
    n0 = len(errors)
    for k in sorted(SOP_REQUIRED - set(item)):
        errors.append(f"{where}: missing '{k}'")
    for k in sorted(set(item) - SOP_KEYS):
        errors.append(f"{where}: unknown field '{k}'")
    if isinstance(sid, str):
        pat = meta.get("id_pattern")
        if isinstance(pat, str) and _valid_re(pat) and not re.fullmatch(pat, sid):
            errors.append(f"{where}: id does not match meta.id_pattern {pat!r}")
        if sid in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(sid)
    else:
        errors.append(f"{where}: id must be a string")
    for k in ("title", "category", "rationale"):
        if k in item and not (isinstance(item[k], str) and item[k].strip()):
            errors.append(f"{where}: {k} must be a non-empty string")
    if "advice" in item and not (isinstance(item["advice"], str) and item["advice"].strip()):
        errors.append(f"{where}: advice is missing or empty")
    if "severity" in item and item["severity"] not in meta.get("severities", []):
        errors.append(f"{where}: severity {item['severity']!r} not in meta.severities")
    if "priority" in item and (not isinstance(item["priority"], int) or isinstance(item["priority"], bool)):
        errors.append(f"{where}: priority must be an integer")
    if "override" in item and not isinstance(item["override"], bool):
        errors.append(f"{where}: override must be true or false")
    if "edge_cases" in item and not (isinstance(item["edge_cases"], list)
                                     and all(isinstance(x, str) for x in item["edge_cases"])):
        errors.append(f"{where}: edge_cases must be a list of strings")

    at = item.get("applies_to")
    if "applies_to" in item:
        if not isinstance(at, dict):
            errors.append(f"{where}: applies_to must be a mapping")
        else:
            for k in set(at) - set(DIMENSIONS):
                errors.append(f"{where}: applies_to unknown dimension '{k}'")
            for dim in DIMENSIONS:
                v = at.get(dim)
                if v == "any":
                    continue
                if not (isinstance(v, list) and v):
                    errors.append(f"{where}: applies_to.{dim} must be a non-empty tag list or 'any'")
                    continue
                for tag in v:
                    if tag not in vocab.get(dim, {}):
                        errors.append(f"{where}: applies_to.{dim} has unknown tag {tag!r}")

    declared: set[tuple[str, str]] = set()
    req = item.get("requires")
    if "requires" in item:
        if not (isinstance(req, list) and req):
            errors.append(f"{where}: requires must be a non-empty list of {{field, source}}")
        else:
            for r in req:
                if not (isinstance(r, dict) and set(r) == {"field", "source"}
                        and isinstance(r["field"], str) and r["source"] in SOURCES):
                    errors.append(f"{where}: bad requires entry {r!r} (need field + source in {sorted(SOURCES)})")
                else:
                    declared.add((r["field"], r["source"]))

    provided: set[str] = set()
    if "condition" in item:
        used: set[tuple[str, str]] = set()
        validate_condition(item["condition"], f"{where}.condition", used, provided, errors)
        for f, s in sorted(used - declared):
            errors.append(f"{where}: condition uses {s}.{f} but it is not listed in requires")
    if isinstance(item.get("advice"), str):
        for name in _PLACEHOLDER_RE.findall(item["advice"]):
            if name not in provided:
                errors.append(f"{where}: advice placeholder {{{name}}} is not produced by the condition "
                              f"(available: {sorted(provided)})")
    if len(errors) > n0:
        return None
    return SOP(**{k: item[k] for k in SOP_KEYS if k in item})


def _valid_re(pat: str) -> bool:
    try:
        re.compile(pat)
        return True
    except re.error:
        return False


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_value_spec(spec: dict, where: str, used: set, errors: list[str], allow_day: bool = True) -> None:
    """Shared by compare, window_agg and score terms: field/source/agg/window/day."""
    field_, source = spec.get("field"), spec.get("source")
    if not isinstance(field_, str):
        errors.append(f"{where}: field must be a string")
        return
    if source not in SOURCES:
        errors.append(f"{where}: source must be one of {sorted(SOURCES)}")
        return
    used.add((field_, source))
    if source == "hourly":
        if spec.get("agg") not in AGGS:
            errors.append(f"{where}: hourly values need agg in {sorted(AGGS)}")
        if "window" not in spec:
            errors.append(f"{where}: hourly values need a window")
        else:
            _validate_window(spec["window"], f"{where}.window", errors)
        if "day" in spec:
            errors.append(f"{where}: 'day' is not allowed for hourly (put it inside the window)")
    else:
        for k in ("agg", "window"):
            if k in spec:
                errors.append(f"{where}: '{k}' is only valid with source: hourly")
        if source == "current" and "day" in spec:
            errors.append(f"{where}: 'day' is only valid with source: daily")
        if "day" in spec and spec["day"] not in DAYS:
            errors.append(f"{where}: day must be one of {sorted(DAYS)}")


def validate_condition(node: Any, where: str, used: set, provided: set, errors: list[str]) -> None:
    if not (isinstance(node, dict) and len(node) == 1):
        errors.append(f"{where}: a condition node must have exactly one key "
                      "(compare, window_agg, score, all, any, not)")
        return
    (kind, body), = node.items()
    where = f"{where}.{kind}"
    if kind in ("all", "any"):
        if not (isinstance(body, list) and body):
            errors.append(f"{where}: must be a non-empty list")
            return
        for i, child in enumerate(body):
            validate_condition(child, f"{where}[{i}]", used, provided, errors)
    elif kind == "not":
        validate_condition(body, where, used, provided, errors)
    elif kind == "compare":
        _leaf(body, where, {"field", "source", "op", "value", "as", "day"}, used, provided, errors, window=False)
        if isinstance(body, dict):
            if body.get("source") == "hourly":
                errors.append(f"{where}: hourly values need window_agg, not compare")
            op, val = body.get("op"), body.get("value")
            if op in SET_OPS:
                if not (isinstance(val, list) and val and all(_num(v) or isinstance(v, str) for v in val)):
                    errors.append(f"{where}: '{op}' needs a non-empty list value")
            elif op in CMP_OPS:
                if not _num(val):
                    errors.append(f"{where}: '{op}' needs a numeric value")
            else:
                errors.append(f"{where}: unknown operator {op!r}")
    elif kind == "window_agg":
        if isinstance(body, dict):
            body = {**body, "source": "hourly"}
            if body.get("op") not in CMP_OPS:
                errors.append(f"{where}: op must be one of {sorted(CMP_OPS)}")
            if not _num(body.get("value")):
                errors.append(f"{where}: value must be numeric")
        _leaf(body, where, {"field", "source", "agg", "window", "op", "value", "as"}, used, provided, errors,
              window=True)
    elif kind == "score":
        _validate_score(body, where, used, provided, errors)
    else:
        errors.append(f"{where}: unknown condition type '{kind}'")


def _leaf(body, where, allowed, used, provided, errors, window) -> None:
    if not isinstance(body, dict):
        errors.append(f"{where}: must be a mapping")
        return
    for k in set(body) - allowed:
        errors.append(f"{where}: unknown field '{k}'")
    _check_value_spec(body, where, used, errors)
    name = body.get("as")
    if name is not None:
        if not (isinstance(name, str) and name.isidentifier()):
            errors.append(f"{where}: 'as' must be an identifier")
        elif name in provided:
            errors.append(f"{where}: duplicate 'as' name {name!r}")
        else:
            provided.add(name)


def _validate_score(body, where, used, provided, errors) -> None:
    if not isinstance(body, dict):
        errors.append(f"{where}: must be a mapping")
        return
    for k in set(body) - {"terms", "match", "labels", "as"}:
        errors.append(f"{where}: unknown field '{k}'")
    prefix = body.get("as") or "score"
    for n in (f"{prefix}_value", f"{prefix}_label") if body.get("as") else ("score", "label"):
        if n in provided:
            errors.append(f"{where}: duplicate score placeholder {n!r}; give this score its own 'as'")
        provided.add(n)
    terms = body.get("terms")
    if not (isinstance(terms, list) and terms):
        errors.append(f"{where}.terms must be a non-empty list")
        terms = []
    names: set[str] = set()
    total_w = 0.0
    for i, t in enumerate(terms):
        tw = f"{where}.terms[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{tw}: must be a mapping")
            continue
        for k in set(t) - {"field", "source", "agg", "window", "day", "as", "weight", "bands", "default_points"}:
            errors.append(f"{tw}: unknown field '{k}'")
        _check_value_spec(t, tw, used, errors)
        nm = t.get("as")
        if not (isinstance(nm, str) and nm.isidentifier()):
            errors.append(f"{tw}: 'as' is required and must be an identifier")
        elif nm in names or nm in provided:
            errors.append(f"{tw}: duplicate 'as' name {nm!r}")
        else:
            names.add(nm)
            provided.add(nm)
        w = t.get("weight")
        if not _num(w) or w < 0:
            errors.append(f"{tw}: weight must be a number >= 0")
        else:
            total_w += w
        dp = t.get("default_points")
        if not (_num(dp) and 0 <= dp <= 1):
            errors.append(f"{tw}: default_points must be a number in 0..1")
        bands = t.get("bands")
        if not (isinstance(bands, list) and bands):
            errors.append(f"{tw}.bands must be a non-empty list")
            continue
        for j, b in enumerate(bands):
            bw = f"{tw}.bands[{j}]"
            if not (isinstance(b, dict) and set(b) == {"op", "value", "points"}):
                errors.append(f"{bw}: needs exactly op, value, points")
                continue
            if b["op"] not in CMP_OPS:
                errors.append(f"{bw}: op must be one of {sorted(CMP_OPS)}")
            if not _num(b["value"]):
                errors.append(f"{bw}: value must be numeric")
            if not (_num(b["points"]) and 0 <= b["points"] <= 1):
                errors.append(f"{bw}: points must be a number in 0..1")
    if terms and total_w <= 0:
        errors.append(f"{where}: sum of term weights must be > 0")
    m = body.get("match")
    if not (isinstance(m, dict) and set(m) == {"op", "value"} and m["op"] in CMP_OPS and _num(m["value"])):
        errors.append(f"{where}.match must be {{op: <comparison op>, value: <number>}}")
    labels = body.get("labels", [])
    if not isinstance(labels, list):
        errors.append(f"{where}.labels must be a list")
    else:
        for j, lb in enumerate(labels):
            if not (isinstance(lb, dict) and set(lb) == {"op", "value", "label"}
                    and lb["op"] in CMP_OPS and _num(lb["value"]) and isinstance(lb["label"], str)):
                errors.append(f"{where}.labels[{j}] must be {{op, value, label}}")
