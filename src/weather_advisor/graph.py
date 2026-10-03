"""The LangGraph agent. LLM-dependent steps (parser, composer, verifier) are injected so the graph
runs deterministically in tests; weather access is an injected client.

Branches (each END-bound branch is its own node so the trace names it):
  load_policy -> policy_error
              -> parse_intent -> out_of_scope | insufficient_intent | explain | ask_location
                              -> resolve_location -> location_unresolved
                                                  -> fetch_weather -> weather_unavailable
                                                                   -> match_sops -> resolve_conflicts
                                                        -> no_guidance | data_unavailable | compose -> verify
"""
from __future__ import annotations

import operator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable, TypedDict

import yaml
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from . import engine
from .conditions import TRUE, fmt_number
from .sops import DIMENSIONS, SOPError, SOPSet, validate_sops
from .verify import _numbers, verify_advice, verify_reply
from .weather import WeatherClient, build_snapshot, forecast_params

# Used only when the SOP file itself is invalid, so its `messages` section cannot be trusted.
POLICY_ERROR_TEXT = "The advice policy file is currently invalid, so I can't answer safely right now."
# Fixed control-flow wording for when the intent parser itself fails (no policy content).
SYSTEM_ERROR_TEXT = "Sorry, I couldn't process your question just now. Please try again."
# Control-flow lead-in for the deterministic 'reassure' outcome (no policy TRUE, but a relevant one was checked).
REASSURE_TEXT = "No active policy flags a concern for that activity in the current conditions. Here is what I checked:"
SESSION_KEYS = ("location_text", "activities", "groups", "question_types", "time_reference")


class State(TypedDict, total=False):
    # per-session (checkpointed by thread_id)
    messages: Annotated[list, operator.add]
    session: dict
    decision_log: list
    # per-turn (reset by load_policy)
    user_text: str
    policy_raw: Any
    raw_intent: dict
    intent: dict
    place: dict
    snapshot: dict
    evals: list
    resolution: dict
    approved: dict
    draft: str | None
    reply: str
    reply_source: str
    branch: str
    trace: dict


Parser = Callable[[str, SOPSet, dict], dict]
Composer = Callable[[dict], str]


def place_label(c: dict) -> str:
    return ", ".join(str(c[k]) for k in ("name", "admin1", "country") if c.get(k))


def build_graph(sop_path: str | Path, client: WeatherClient, parser: Parser,
                composer: Composer | None = None, clock: Callable[[], datetime] | None = None,
                checkpointer=None, advisor: Callable[[dict], dict] | None = None):
    """When `advisor` is given, the post-weather decision is made by the LLM-reasoner path (advise node,
    guardrailed by verify_advice, with a deterministic fallback). When it is None, the original deterministic
    match/resolve/compose path runs unchanged (used by the reproducible engine-tier evals and unit tests)."""
    sop_path = Path(sop_path)

    def policy(state) -> SOPSet:
        return validate_sops(state["policy_raw"])

    def tr(state, **kw) -> dict:
        return {**state.get("trace", {}), **kw}

    def finish(state, branch: str, text: str, source: str = "template", state_updates=None, **extra) -> dict:
        return {"reply": text, "reply_source": source, "branch": branch,
                "messages": [{"role": "assistant", "content": text}],
                "trace": tr(state, branch=branch, reply_source=source, **extra), **(state_updates or {})}

    # ---------------- nodes ----------------
    def load_policy(state):
        reset = {k: None for k in ("raw_intent", "intent", "place", "snapshot", "evals", "resolution",
                                   "approved", "draft", "reply", "reply_source", "branch")}
        base = {**reset, "user_text": state["user_text"], "trace": {"user_text": state["user_text"]},
                "messages": [{"role": "user", "content": state["user_text"]}],
                "session": state.get("session") or {}, "decision_log": state.get("decision_log") or []}
        try:
            raw = yaml.safe_load(sop_path.read_text(encoding="utf-8"))
            validate_sops(raw)
            return {**base, "policy_raw": raw}
        except (SOPError, yaml.YAMLError, OSError) as e:
            errs = e.errors if isinstance(e, SOPError) else [str(e)]
            return {**base, "policy_raw": None, "trace": {**base["trace"], "policy_errors": errs}}

    def system_error(state):
        return finish(state, "system_error", SYSTEM_ERROR_TEXT)

    def policy_error(state):
        return finish(state, "policy_error", POLICY_ERROR_TEXT, failure_reason="invalid SOP file")

    def parse_intent(state):
        pol, session = policy(state), state["session"]
        try:
            raw = parser(state["user_text"], pol, session)
        except Exception as e:   # LLM/API/schema failure: say so, never guess
            return {"intent": None, "trace": tr(state, failure_reason=f"intent parsing: {e}")}
        dropped = {}
        clean: dict[str, Any] = {"in_scope": bool(raw.get("in_scope")),
                                 "asks_for_explanation": bool(raw.get("asks_for_explanation")),
                                 "location_text": (raw.get("location_text") or "").strip() or None}
        for dim in DIMENSIONS:
            tags = list(raw.get(dim) or [])
            clean[dim] = [t for t in tags if t in pol.vocabulary[dim]]
            if len(clean[dim]) != len(tags):
                dropped[dim] = [t for t in tags if t not in pol.vocabulary[dim]]
        tr_ = raw.get("time_reference")
        clean["time_reference"] = tr_ if tr_ in pol.vocabulary["time_words"] else None
        if tr_ and clean["time_reference"] is None:
            dropped["time_reference"] = [tr_]
        # Safety net: small models sometimes return in_scope=False while still extracting a valid
        # outdoor-activity or group tag (e.g. "driving a car" -> road_driving). A recognised tag from
        # the SOP vocabulary IS an outdoor-activity question, so honour it rather than replying
        # "out of scope" and throwing the extracted intent away.
        if not clean["in_scope"] and (clean["activities"] or clean["groups"]):
            clean["in_scope"] = True
        # Session merge (deterministic): anything the user stated replaces the stored value;
        # anything not stated is inherited. Time falls back to the configured default.
        merged = {k: clean[k] or session.get(k) or ([] if k != "location_text" and k != "time_reference" else None)
                  for k in SESSION_KEYS}
        inherited = [k for k in SESSION_KEYS if not clean[k] and merged[k]]
        merged["time_reference"] = merged["time_reference"] or pol.meta["default_time_reference"]
        intent = {**merged, "in_scope": clean["in_scope"], "asks_for_explanation": clean["asks_for_explanation"]}
        upd: dict[str, Any] = {"raw_intent": raw, "intent": intent}
        if clean["in_scope"] and not clean["asks_for_explanation"]:
            upd["session"] = {k: merged[k] for k in SESSION_KEYS}
        upd["trace"] = tr(state, raw_intent=raw, intent=intent, dropped_tags=dropped, inherited_from_session=inherited)
        return upd

    def route_parse(state) -> str:
        i = state["intent"]
        if i is None:
            return "system_error"
        if i["asks_for_explanation"] and i["in_scope"]:
            return "explain"
        if not i["in_scope"]:
            return "out_of_scope"
        if not any(i[d] for d in DIMENSIONS):
            return "insufficient_intent"
        if not i["location_text"]:
            return "ask_location"
        return "resolve_location"

    def template(name: str):
        def node(state):
            return finish(state, name, policy(state).messages[name])
        node.__name__ = name
        return node

    def explain(state):
        pol, log = policy(state), state["decision_log"]
        if not log:
            return finish(state, "explain", pol.messages["no_prior_decision"], explained_turn=None)
        d = log[-1]
        if d.get("explanation"):   # advisor path precomputes the rationale at decision time
            return finish(state, "explain", d["explanation"], "explain", explained_turn=d["turn"])
        by_id = {s.id: s for s in pol.sops}
        if d["outcome"] == "advice":
            parts = []
            for sid in [d["primary"], *d["secondary"]]:
                s = by_id.get(sid)
                role = "primary" if sid == d["primary"] else "secondary"
                parts.append(f"{sid} ({s.title if s else 'no longer in the SOP file'}; severity "
                             f"{d['severities'].get(sid)}; {role})" + (f": {s.rationale}" if s else ""))
            ev = ", ".join(f"{k}={v}" for k, v in d["evidence"].items()) or "none"
            text = (f"I said that because of {'; '.join(parts)}. Evidence from the weather data for "
                    f"{d['location']} (as of {d['snapshot_time']} local): {ev}.")
        elif d["outcome"] == "data_unavailable":
            text = (f"For {d['location']} (weather as of {d['snapshot_time']} local) my answer was "
                    f"'data_unavailable': a relevant policy ({', '.join(d['unknown'])}) could not be evaluated "
                    "because required weather data was unavailable.")
        else:
            text = (f"For {d['location']} (weather as of {d['snapshot_time']} local) my answer was "
                    "'no_guidance': no applicable guidance existed (no applicable SOP evaluated TRUE).")
        return finish(state, "explain", text, "explain", explained_turn=d["turn"])

    def resolve_location(state):
        name = state["intent"]["location_text"]
        try:
            cands = client.geocode(name)
            first = cands[0] if cands else None
            if first is None or not all(isinstance(first.get(k), (int, float)) for k in ("latitude", "longitude")):
                raise ValueError("no usable geocoding candidate")
        except Exception as e:  # any geocoding failure -> same honest branch
            return {"place": None, "trace": tr(state, location_candidates=[], failure_reason=f"geocoding: {e}")}
        place = {"label": place_label(first), "latitude": first["latitude"], "longitude": first["longitude"],
                 "timezone": first.get("timezone")}
        return {"place": place, "trace": tr(state, location_candidates=[place_label(c) for c in cands],
                                            chosen_place=place)}

    def fetch_weather(state):
        fields, p = policy(state).required_fields(), state["place"]
        req = forecast_params(p["latitude"], p["longitude"], fields)
        try:
            snap = build_snapshot(client.forecast(p["latitude"], p["longitude"], fields), fields,
                                  clock() if clock else None)
        except Exception as e:
            return {"snapshot": None, "trace": tr(state, weather_request=req, failure_reason=f"weather: {e}")}
        return {"snapshot": snap, "trace": tr(state, weather_request=req, weather_snapshot=snap)}

    def match_sops(state):
        pol = policy(state)
        evals = engine.match_sops(pol, state["intent"], state["snapshot"])
        return {"evals": evals, "trace": tr(state, sop_evaluations=[
            {k: e[k] for k in ("id", "applicable", "applies_reason", "result", "effective",
                               "render_blocked", "evidence", "eval_trace")} for e in evals])}

    def resolve_conflicts(state):
        pol, evals = policy(state), state["evals"]
        res = engine.resolve_conflicts(pol, evals)
        by_id = {e["id"]: e for e in evals}
        approved = {
            "place": state["place"]["label"],
            "snapshot_time": state["snapshot"]["now_local"],
            "time_reference": state["intent"]["time_reference"],
            "primary": {"id": res["primary"], "advice": by_id[res["primary"]]["advice"]} if res["primary"] else None,
            "secondary": [{"id": i, "advice": by_id[i]["advice"]} for i in res["secondary"]],
            "disclosed_ids": res["disclosed_unknown"],
            "disclosures": [pol.messages["unknown_disclosure"].format(
                sop_id=i, title=by_id[i]["title"], severity=by_id[i]["severity"]) for i in res["disclosed_unknown"]],
        }
        return {"resolution": res, "approved": approved,
                "trace": tr(state, matched_sops=res["matched"], primary_sop=res["primary"],
                            secondary_sops=res["secondary"], unknown_sops=res["unknown"],
                            disclosed_unknown_sops=res["disclosed_unknown"], outcome=res["outcome"])}

    def route_resolution(state) -> str:
        o = state["resolution"]["outcome"]
        if o == "advice":
            return "compose"
        if o == "no_guidance" and engine.needs_group_clarification(policy(state), state["intent"]):
            return "clarify"   # a group tag would unlock a SOP: ask rather than dead-end (deterministic)
        return o   # reassure | data_unavailable | no_guidance

    def reassure(state):
        """Deterministic 'checked, no concern': a relevant SOP applies but its threshold is not met."""
        pol, res = policy(state), state["resolution"]
        by_id = {e["id"]: e for e in state["evals"]}
        text, cited = render_reassure(res["reassure"], by_id)
        place, time = state["place"]["label"], state["snapshot"]["now_local"]
        entry = {"turn": len(state["decision_log"]) + 1, "outcome": "reassure", "primary": None, "secondary": [],
                 "cited": cited, "location": place, "snapshot_time": time,
                 "severities": {i: by_id[i]["severity"] for i in cited},
                 "evidence": {k: v for i in cited for k, v in by_id[i]["evidence"].items()},
                 "explanation": _explain_reassure(cited, by_id, place, time)}
        return finish(state, "reassure", text, "template",
                      state_updates={"decision_log": [*state["decision_log"], entry]}, reassured_sops=cited)

    def clarify(state):
        """Deterministic follow-up: the user named an activity but no vulnerable group, and a group-restricted
        SOP for that activity exists. Ask which group applies instead of guessing or dead-ending."""
        wanted = engine.needs_group_clarification(policy(state), state["intent"])
        human = ", ".join(w.replace("_", " ") for w in wanted)
        text = (f"To check the right policy, is this for any of: {human}? "
                "Tell me and I'll check the policy that applies, or say it's none of these.")
        return finish(state, "clarify", text, clarify_groups=wanted)

    def compose(state):
        draft = None
        if composer is not None:
            payload = {**state["approved"], "prior_decisions": summarize_log(state["decision_log"])}
            try:
                draft = composer(payload)
            except Exception as e:
                return {"draft": None, "trace": tr(state, compose_error=str(e))}
        return {"draft": draft}

    def verify(state):
        approved = state["approved"]
        fallback = render_approved(approved)
        ok, details = False, {"reason": "no composer output"}
        if state["draft"] is not None:
            ok, details = verify_reply(state["draft"], approved, policy(state), fallback)
        text, source = (state["draft"], "llm") if ok else (fallback, "fallback_template")
        res = state["resolution"]
        by_id = {e["id"]: e for e in state["evals"]}
        entry = {"turn": len(state["decision_log"]) + 1, "outcome": "advice", "primary": res["primary"],
                 "secondary": res["secondary"], "location": approved["place"],
                 "snapshot_time": approved["snapshot_time"],
                 "severities": {i: by_id[i]["severity"] for i in res["matched"]},
                 "evidence": {k: v for i in res["matched"] for k, v in by_id[i]["evidence"].items()}}
        return finish(state, "compose", text, source, verification={"passed": ok, **details},
                      state_updates={"decision_log": [*state["decision_log"], entry]})

    def advise(state):
        """LLM-reasoner path: the model decides which SOP is relevant and how to frame it; code assesses
        every SOP deterministically, guardrails the decision (verify_advice), and falls back safely."""
        pol, intent, snap, place = policy(state), state["intent"], state["snapshot"], state["place"]
        records = engine.assess_all(pol, intent, snap)
        view = [{"id": r["id"], "title": r["title"], "severity": r["severity"],
                 "for": {"activities": r["applies_to"]["activities"], "groups": r["applies_to"]["groups"]},
                 "result": r["result"],
                 "checks": [{k: c[k] for k in ("field", "op", "threshold", "value") if c.get(k) is not None}
                            for c in r["checks"]],
                 "advice": r["advice_template"]} for r in records]
        payload = {"user_text": state["user_text"], "place": place["label"],
                   "snapshot_time": snap["now_local"], "time_reference": intent["time_reference"],
                   "prior_decisions": summarize_log(state["decision_log"]), "sops": view}
        ctx_nums = _numbers(f"{place['label']} {snap['now_local']}", set())
        try:
            decision = advisor(payload)
        except Exception as e:
            return _advise_fallback(state, records, f"advisor call failed: {e}")
        ok, det = verify_advice(decision, records, ctx_nums, pol)
        if not ok:
            return _advise_fallback(state, records, det["reason"], decision=decision)
        action, reply = decision["action"], decision["reply"].strip()
        tr_extra = {"advisor_action": action, "advisor_cited": [decision.get("lead_sop"), *(decision.get("also_cite") or [])],
                    "matched_sops": [r["id"] for r in records if r["result"] == "TRUE"]}
        if action == "clarify":
            return finish(state, "clarify", reply, "llm", **tr_extra)   # a question, not a logged decision
        by_id = {r["id"]: r for r in records}
        cited = [i for i in [decision.get("lead_sop"), *(decision.get("also_cite") or [])] if i in by_id]
        entry = {"turn": len(state["decision_log"]) + 1, "outcome": action, "primary": decision.get("lead_sop"),
                 "secondary": [i for i in cited if i != decision.get("lead_sop")], "cited": cited,
                 "location": place["label"], "snapshot_time": snap["now_local"], "reply": reply,
                 "severities": {i: by_id[i]["severity"] for i in cited},
                 "evidence": {k: v for i in cited for k, v in by_id[i]["evidence"].items()},
                 "explanation": _explain_decision(action, cited, by_id, place["label"], snap["now_local"])}
        return finish(state, action, reply, "llm", state_updates={"decision_log": [*state["decision_log"], entry]},
                      **tr_extra)

    def _advise_fallback(state, records, reason, decision=None):
        """Guardrail tripped (or the advisor failed): answer deterministically so nothing unsafe reaches the user."""
        pol, intent, snap, place = policy(state), state["intent"], state["snapshot"], state["place"]
        evals = engine.match_sops(pol, intent, snap)
        res = engine.resolve_conflicts(pol, evals)
        by_id = {e["id"]: e for e in evals}
        tr_extra = {"advisor_action": (decision or {}).get("action"), "advisor_rejected": reason,
                    "matched_sops": res["matched"]}
        if res["primary"]:
            approved = {"place": place["label"], "snapshot_time": snap["now_local"],
                        "primary": {"id": res["primary"], "advice": by_id[res["primary"]]["advice"]},
                        "secondary": [{"id": i, "advice": by_id[i]["advice"]} for i in res["secondary"]],
                        "disclosed_ids": res["disclosed_unknown"],
                        "disclosures": [pol.messages["unknown_disclosure"].format(
                            sop_id=i, title=by_id[i]["title"], severity=by_id[i]["severity"]) for i in res["disclosed_unknown"]]}
            entry = {"turn": len(state["decision_log"]) + 1, "outcome": "advice", "primary": res["primary"],
                     "secondary": res["secondary"], "cited": res["matched"], "location": place["label"],
                     "snapshot_time": snap["now_local"], "severities": {i: by_id[i]["severity"] for i in res["matched"]},
                     "evidence": {k: v for i in res["matched"] for k, v in by_id[i]["evidence"].items()}}
            return finish(state, "advise", render_approved(approved), "fallback_template",
                          state_updates={"decision_log": [*state["decision_log"], entry]}, **tr_extra)
        if res["outcome"] == "reassure":
            text, cited = render_reassure(res["reassure"], by_id)
            entry = {"turn": len(state["decision_log"]) + 1, "outcome": "reassure", "primary": None, "secondary": [],
                     "cited": cited, "location": place["label"], "snapshot_time": snap["now_local"],
                     "severities": {i: by_id[i]["severity"] for i in cited},
                     "evidence": {k: v for i in cited for k, v in by_id[i]["evidence"].items()},
                     "explanation": _explain_reassure(cited, by_id, place["label"], snap["now_local"])}
            return finish(state, "reassure", text, "fallback_template",
                          state_updates={"decision_log": [*state["decision_log"], entry]}, **tr_extra)
        name = "data_unavailable" if res["outcome"] == "data_unavailable" else "no_guidance"
        entry = {"turn": len(state["decision_log"]) + 1, "outcome": name, "primary": None, "secondary": [],
                 "location": place["label"], "snapshot_time": snap["now_local"], "severities": {}, "evidence": {},
                 "unknown": res["unknown"]}
        return finish(state, name, pol.messages[name], "fallback_template",
                      state_updates={"decision_log": [*state["decision_log"], entry]}, **tr_extra)

    def terminal_logged(name):
        """no_guidance / data_unavailable: reply from template, but still log the decision for 'why?'."""
        base = template(name)
        def node(state):
            out = base(state)
            res = state["resolution"]
            entry = {"turn": len(state["decision_log"]) + 1, "outcome": name, "primary": None, "secondary": [],
                     "location": state["place"]["label"], "snapshot_time": state["snapshot"]["now_local"],
                     "severities": {}, "evidence": {}, "unknown": res["unknown"]}
            return {**out, "decision_log": [*state["decision_log"], entry]}
        node.__name__ = name
        return node

    # ---------------- wiring ----------------
    g = StateGraph(State)
    g.add_node("load_policy", load_policy)
    g.add_node("policy_error", policy_error)
    g.add_node("system_error", system_error)
    g.add_node("parse_intent", parse_intent)
    for n in ("out_of_scope", "insufficient_intent", "ask_location", "location_unresolved", "weather_unavailable"):
        g.add_node(n, template(n))
    for n, f in (("explain", explain), ("resolve_location", resolve_location), ("fetch_weather", fetch_weather)):
        g.add_node(n, f)
    g.set_entry_point("load_policy")
    g.add_conditional_edges("load_policy", lambda s: "parse_intent" if s["policy_raw"] else "policy_error",
                            ["parse_intent", "policy_error"])
    g.add_conditional_edges("parse_intent", route_parse,
                            ["explain", "out_of_scope", "insufficient_intent", "ask_location", "resolve_location",
                             "system_error"])
    g.add_conditional_edges("resolve_location", lambda s: "fetch_weather" if s["place"] else "location_unresolved",
                            ["fetch_weather", "location_unresolved"])
    post_weather = "advise" if advisor is not None else "match_sops"
    g.add_conditional_edges("fetch_weather", lambda s: post_weather if s["snapshot"] else "weather_unavailable",
                            [post_weather, "weather_unavailable"])
    always_end = ["policy_error", "system_error", "out_of_scope", "insufficient_intent", "ask_location",
                  "location_unresolved", "weather_unavailable", "explain"]
    if advisor is not None:
        # LLM-reasoner path: one node decides and returns the final answer (guardrailed, with fallback).
        g.add_node("advise", advise)
        always_end.append("advise")
    else:
        # Deterministic path (default): code matches and picks the answer; the model only parses and rephrases.
        # 'reassure' (relevant SOP checked but threshold not met) and 'clarify' (ask for a missing group) keep
        # the conversation from dead-ending, both decided by code. This is what the eval suites exercise.
        for n in ("no_guidance", "data_unavailable"):
            g.add_node(n, terminal_logged(n))
        for n, f in (("match_sops", match_sops), ("resolve_conflicts", resolve_conflicts),
                     ("compose", compose), ("verify", verify), ("reassure", reassure), ("clarify", clarify)):
            g.add_node(n, f)
        g.add_edge("match_sops", "resolve_conflicts")
        g.add_conditional_edges("resolve_conflicts", route_resolution,
                                ["compose", "no_guidance", "data_unavailable", "reassure", "clarify"])
        g.add_edge("compose", "verify")
        always_end += ["no_guidance", "data_unavailable", "verify", "reassure", "clarify"]
    for n in always_end:
        g.add_edge(n, END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


def render_approved(a: dict) -> str:
    """Deterministic rendering of the approved advice: the fallback reply and the verifier's baseline."""
    lines = [f"{a['place']} (weather as of {a['snapshot_time']} local):",
             f"[{a['primary']['id']}] {a['primary']['advice']}"]
    if a["secondary"]:
        lines.append("Also relevant:")
        lines += [f"- [{s['id']}] {s['advice']}" for s in a["secondary"]]
    lines += a["disclosures"]
    return "\n".join(lines)


def _reassure_line(rec: dict) -> str:
    """One grounded line explaining why a relevant SOP did not trigger (field value vs threshold)."""
    def isnum(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    nums = [t for t in rec["eval_trace"] if t.get("node") in ("compare", "window_agg")
            and isnum(t.get("value")) and isnum(t.get("threshold"))]
    show = [t for t in nums if t.get("result") == "FALSE"] or nums
    parts = [f"{t['field']} is {fmt_number(t['value'])} (threshold {t['op']} {fmt_number(t['threshold'])})"
             for t in show[:2]]
    body = "; ".join(parts) if parts else "its condition was not met"
    return f"- [{rec['id']}] {rec['title']}: {body}."


def render_reassure(reassure_ids: list, by_id: dict) -> tuple[str, list]:
    """Deterministic 'checked, no concern' reply citing the most relevant applicable-but-FALSE SOPs."""
    cited = reassure_ids[:2]
    return "\n".join([REASSURE_TEXT, *[_reassure_line(by_id[i]) for i in cited]]), cited


def _explain_reassure(cited: list, by_id: dict, place: str, time: str) -> str:
    parts = [f"{i} ({by_id[i]['title']})" for i in cited]
    return (f"I did not flag a concern for {place} (weather as of {time} local); I checked "
            f"{'; '.join(parts)} and their thresholds were not met.")


def _explain_decision(action: str, cited: list, by_id: dict, place: str, time: str) -> str:
    """Precompute the 'why?' rationale for an advisor decision from the deterministic records it cited."""
    if not cited:
        return (f"For {place} (weather as of {time} local) no policy applied, so there is no citation to give.")
    parts = []
    for i in cited:
        r = by_id[i]
        ev = ", ".join(f"{k}={v}" for k, v in r["evidence"].items()) or "no specific value"
        parts.append(f"{i} ({r['title']}; severity {r['severity']}; condition {r['result']}; {ev})")
    verb = "flagged a concern" if action == "advise" else "checked and found no concern"
    return f"I {verb} using {'; '.join(parts)}, from the live weather for {place} as of {time} local."


def summarize_log(log: list) -> list[str]:
    out = []
    for d in log[-3:]:
        if d["outcome"] == "advice":
            out.append(f"Earlier in this chat you were given advice (severity {d['severities'][d['primary']]}) for {d['location']}.")
        else:
            out.append(f"Earlier in this chat the answer was '{d['outcome']}' for {d['location']}.")
    return out


def ask(app, thread_id: str, text: str) -> dict:
    """Run one turn on a session thread and return the final state."""
    return app.invoke({"user_text": text}, {"configurable": {"thread_id": thread_id}})
