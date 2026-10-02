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
from .conditions import TRUE
from .sops import DIMENSIONS, SOPError, SOPSet, validate_sops
from .verify import verify_reply
from .weather import WeatherClient, build_snapshot, forecast_params

# Used only when the SOP file itself is invalid, so its `messages` section cannot be trusted.
POLICY_ERROR_TEXT = "The advice policy file is currently invalid, so I can't answer safely right now."
# Fixed control-flow wording for when the intent parser itself fails (no policy content).
SYSTEM_ERROR_TEXT = "Sorry, I couldn't process your question just now. Please try again."
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
                checkpointer=None):
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
        return "compose" if o == "advice" else o

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
    for n in ("no_guidance", "data_unavailable"):
        g.add_node(n, terminal_logged(n))
    for n, f in (("explain", explain), ("resolve_location", resolve_location), ("fetch_weather", fetch_weather),
                 ("match_sops", match_sops), ("resolve_conflicts", resolve_conflicts),
                 ("compose", compose), ("verify", verify)):
        g.add_node(n, f)
    g.set_entry_point("load_policy")
    g.add_conditional_edges("load_policy", lambda s: "parse_intent" if s["policy_raw"] else "policy_error",
                            ["parse_intent", "policy_error"])
    g.add_conditional_edges("parse_intent", route_parse,
                            ["explain", "out_of_scope", "insufficient_intent", "ask_location", "resolve_location",
                             "system_error"])
    g.add_conditional_edges("resolve_location", lambda s: "fetch_weather" if s["place"] else "location_unresolved",
                            ["fetch_weather", "location_unresolved"])
    g.add_conditional_edges("fetch_weather", lambda s: "match_sops" if s["snapshot"] else "weather_unavailable",
                            ["match_sops", "weather_unavailable"])
    g.add_edge("match_sops", "resolve_conflicts")
    g.add_conditional_edges("resolve_conflicts", route_resolution, ["compose", "no_guidance", "data_unavailable"])
    g.add_edge("compose", "verify")
    for n in ("policy_error", "system_error", "out_of_scope", "insufficient_intent", "ask_location", "location_unresolved",
              "weather_unavailable", "no_guidance", "data_unavailable", "explain", "verify"):
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
