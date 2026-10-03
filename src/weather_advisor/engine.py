"""Pure-code SOP matching and conflict resolution (no LLM, no I/O).

Intent (the structured output of parse_intent, after session merge):
  {"activities": [tags], "groups": [tags], "question_types": [tags], "time_reference": tag|None}
"""
from __future__ import annotations

from typing import Any

from .conditions import FALSE, TRUE, UNKNOWN, EvalContext, MissingEvidence, evaluate, render_advice
from .sops import DIMENSIONS, SOP, SOPSet


def applies(sop: SOP, intent: dict) -> tuple[bool, str]:
    """Dimensions AND; tags within a list OR; `any` is unrestricted; no intent tag never satisfies a restriction.

    Exception: `question_types` is a *refinement*, not a gate. It describes how the user phrased the
    question (safety_check / planning / suitability / ...); it should narrow matching only when the user
    actually expressed one. A bare activity statement like "driving in Bhopal" carries no question type,
    and a real fog hazard must still apply, so an empty intent question_type does not exclude any SOP.
    activities and groups still gate: an unspecified activity or vulnerable group never matches a SOP
    that requires one (the bot must not guess the activity or that a child/pet/elder is involved).
    """
    for dim in DIMENSIONS:
        want = sop.applies_to[dim]
        if want == "any":
            continue
        have = set(intent.get(dim) or [])
        if dim == "question_types" and not have:
            continue   # user did not frame a question type -> do not gate on it
        if not have & set(want):
            return False, f"{dim}: need one of {want}, intent has {sorted(have)}"
    return True, "all dimensions satisfied"


def match_sops(policy: SOPSet, intent: dict, snapshot: dict) -> list[dict[str, Any]]:
    """One evaluation record per SOP, in file order.

    `result` is the raw condition result. `effective` is what response selection uses: a TRUE
    condition whose advice cannot be rendered from available evidence becomes UNKNOWN.
    """
    ctx = EvalContext(snapshot, policy.vocabulary, intent.get("time_reference"))
    out = []
    for sop in policy.sops:
        ok, why = applies(sop, intent)
        rec: dict[str, Any] = {"id": sop.id, "title": sop.title, "severity": sop.severity,
                               "priority": sop.priority, "override": sop.override,
                               "applicable": ok, "applies_reason": why,
                               "result": None, "effective": None, "evidence": {}, "advice": None,
                               "render_blocked": None, "eval_trace": []}
        if ok:
            r = evaluate(sop.condition, ctx)
            rec.update(result=r.value, effective=r.value, evidence=r.evidence, eval_trace=r.trace)
            if r.value == TRUE:
                try:
                    rec["advice"] = render_advice(sop.advice, r.evidence)
                except MissingEvidence as e:
                    rec["effective"] = UNKNOWN
                    rec["render_blocked"] = (f"condition evaluated TRUE but advice needs {{{e.args[0]}}}, "
                                             "which is UNKNOWN; effective result is UNKNOWN")
        out.append(rec)
    return out


def resolve_conflicts(policy: SOPSet, evals: list[dict]) -> dict[str, Any]:
    """Decide outcome. Order: override SOPs first, then severity (high first), then priority (LARGER wins),
    then SOP ID (ascending)."""
    def key(e):
        return (not e["override"], -policy.severity_rank(e["severity"]), -e["priority"], e["id"])

    applicable = [e for e in evals if e["applicable"]]
    true = sorted((e for e in applicable if e["effective"] == TRUE), key=key)
    cutoff = policy.severity_rank(policy.meta["disclose_unknown_from"])
    unknown = [e for e in applicable if e["effective"] == UNKNOWN]
    disclosed = sorted((e for e in unknown if policy.severity_rank(e["severity"]) >= cutoff), key=key)
    if true:
        outcome = "advice"
    elif not applicable:
        outcome = "no_guidance"
    elif disclosed:
        outcome = "data_unavailable"
    else:
        outcome = "no_guidance"
    return {"outcome": outcome,
            "matched": [e["id"] for e in true],
            "primary": true[0]["id"] if true else None,
            "secondary": [e["id"] for e in true[1:]],
            "unknown": [e["id"] for e in unknown],
            "disclosed_unknown": [e["id"] for e in disclosed]}
