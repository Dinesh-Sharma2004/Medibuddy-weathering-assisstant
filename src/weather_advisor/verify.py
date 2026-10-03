"""Deterministic verifier for composed replies.

A composed reply is accepted only if:
  1. every SOP ID it cites is in the allowed set (this request's matched SOPs plus the SOPs
     disclosed as UNKNOWN). A token counts as an SOP ID only if it matches meta.id_pattern, so
     invented IDs in that namespace (e.g. "SOP-99") are rejected and "UTC-5" is not an ID;
  2. the primary ID, every secondary ID and every disclosed-UNKNOWN ID are all present;
  3. every number is one that code already placed in the approved text (rendered advice, resolved
     place, resolved date/time, disclosure lines), compared numerically.
Spelled-out numbers ("fifty") are not checked; the compose prompt asks for digits.
"""
from __future__ import annotations

import re

from .sops import SOPSet

_NUM = re.compile(r"(?<![\d.])(?:(?<!\w)-)?\d+(?:\.\d+)?")


def _namespace_pattern(policy: SOPSet) -> str:
    """The id_pattern as a mid-string token matcher.

    Review fix: meta.id_pattern is a FULLMATCH pattern (the loader validates ids with re.fullmatch),
    so a policy author naturally anchors it, e.g. '^WA-[0-9]{2}$'. Those ^/$ anchors are meaningless -
    and silently break matching - once the pattern is embedded mid-string to find ids inside a reply.
    The production file used an anchored pattern, which made _id_tokens() match nothing: the verifier
    then rejected every faithful LLM rephrase (missing_ids) and the composed answer was never used.
    Strip one leading ^ and one trailing $ so the id namespace is recognised either way.
    """
    p = policy.meta["id_pattern"]
    if p.startswith("^"):
        p = p[1:]
    if p.endswith("$") and not p.endswith(r"\$"):
        p = p[:-1]
    return p


def _id_tokens(text: str, policy: SOPSet) -> set[str]:
    """Tokens in the SOP-ID namespace, i.e. matching the file's own meta.id_pattern. Anything else
    (e.g. "UTC-5") is not an SOP ID."""
    rx = re.compile(rf"(?<![\w-])(?:{_namespace_pattern(policy)})(?![\w-])")
    return {m.group(0) for m in rx.finditer(text)}


def _numbers(text: str, strip: set[str]) -> list[float]:
    for tok in sorted(strip, key=len, reverse=True):
        text = text.replace(tok, " ")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)    # 1,200 -> 1200
    return [float(m) for m in _NUM.findall(text)]


def verify_reply(draft: str, approved: dict, policy: SOPSet, baseline: str) -> tuple[bool, dict]:
    """`baseline` is the deterministic rendering of the approved advice (graph.render_approved)."""
    must = [approved["primary"]["id"], *[s["id"] for s in approved["secondary"]], *approved["disclosed_ids"]]
    allowed_ids = set(must)
    baseline_tokens = _id_tokens(baseline, policy)   # in-namespace tokens the approved text itself contains
    cited = _id_tokens(draft, policy)
    unexpected_ids = sorted(cited - allowed_ids - baseline_tokens)
    missing_ids = sorted(i for i in must if i not in cited)

    strip = baseline_tokens | cited   # IDs contain digits; they are not weather numbers
    allowed_nums = set(_numbers(baseline, strip))
    unexpected_nums = sorted({n for n in _numbers(draft, strip) if n not in allowed_nums})

    details = {"cited_ids": sorted(cited), "unexpected_ids": unexpected_ids, "missing_ids": missing_ids,
               "unexpected_numbers": unexpected_nums}
    ok = bool(draft.strip()) and not (unexpected_ids or missing_ids or unexpected_nums)
    if not ok:
        details["reason"] = "; ".join(
            f"{k}={v}" for k, v in details.items() if k in ("unexpected_ids", "missing_ids", "unexpected_numbers") and v
        ) or "empty reply"
    return ok, details


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def verify_advice(decision: dict, records: list[dict], context_numbers, policy: SOPSet) -> tuple[bool, dict]:
    """Guardrail for the LLM-advisor path. The advisor chooses relevance and framing; code checks it:

      - every cited id exists in the assessed SOPs (`records`);
      - action="advise" only if the lead SOP's deterministic result is TRUE (never flag a hazard that is not
        actually live); action="reassure" only if the lead SOP is FALSE (checked, threshold not met);
      - the reply cites the lead SOP id;
      - every number in the reply is one code produced: a value or threshold from the assessed checks/evidence,
        or a place/time number from `context_numbers`.

    On failure the graph falls back to the deterministic engine, so a bad LLM decision never reaches the user.
    """
    action = decision.get("action")
    reply = (decision.get("reply") or "").strip()
    lead = decision.get("lead_sop")
    cited_fields = [lead, *(decision.get("also_cite") or [])]
    by_id = {r["id"]: r for r in records}
    fails = []

    cited_in_reply = _id_tokens(reply, policy)
    bad_ids = sorted((set(cited_fields) | cited_in_reply) - set(by_id) - {None})
    if bad_ids:
        fails.append(f"cited unknown SOP ids {bad_ids}")

    if action == "advise":
        if not lead or by_id.get(lead, {}).get("result") != "TRUE":
            fails.append(f"'advise' requires lead SOP TRUE; lead={lead} result={by_id.get(lead, {}).get('result')}")
    elif action == "reassure":
        if not lead or by_id.get(lead, {}).get("result") != "FALSE":
            fails.append(f"'reassure' requires lead SOP FALSE; lead={lead} result={by_id.get(lead, {}).get('result')}")
    elif action == "clarify":
        if not (decision.get("follow_up_question") or "").strip():
            fails.append("'clarify' needs a follow_up_question")
    elif action != "no_guidance":
        fails.append(f"unknown action {action!r}")

    if action in ("advise", "reassure"):
        if lead and lead not in cited_in_reply:
            fails.append(f"reply does not cite lead SOP {lead}")
        allowed = set(context_numbers or [])
        for r in records:
            for v in r.get("evidence", {}).values():
                if _num(v):
                    allowed.add(round(float(v), 4))
            for c in r.get("checks", []):
                for v in (c.get("threshold"), c.get("value")):
                    if _num(v):
                        allowed.add(round(float(v), 4))
        strip = _id_tokens(reply, policy)
        bad_nums = sorted({n for n in _numbers(reply, strip) if round(n, 4) not in allowed})
        if bad_nums:
            fails.append(f"reply has ungrounded numbers {bad_nums}")

    if action in ("advise", "reassure", "clarify", "no_guidance") and not reply:
        fails.append("empty reply")

    return (not fails), {"action": action, "lead_sop": lead, "reason": "; ".join(fails)}
