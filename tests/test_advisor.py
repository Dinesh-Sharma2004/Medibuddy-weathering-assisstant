"""LLM-reasoner path: the advise node + verify_advice guardrail. No real LLM — the advisor is stubbed,
so these are deterministic. They prove the guardrail accepts valid decisions, rejects unsafe ones, and
that a rejected decision falls back to the deterministic engine instead of reaching the user."""
from types import SimpleNamespace

import pytest

from helpers import GEO, ScriptedParser, full_snapshot, intent
from conftest import FIXTURE
from weather_advisor.graph import ask, build_graph
from weather_advisor.llm import _parse_json_decision, _coerce_decision
from weather_advisor.verify import verify_advice
from weather_advisor.weather import FixtureClient

POL = SimpleNamespace(meta={"id_pattern": r"^FX-[A-Z0-9-]+$"})
RECORDS = [
    {"id": "FX-WIND-01", "title": "Wind", "severity": "warning", "result": "TRUE",
     "evidence": {"wind": 50}, "checks": [{"field": "wind_speed_10m", "op": ">", "threshold": 40, "value": 50}]},
    {"id": "FX-CALM-01", "title": "Calm", "severity": "advisory", "result": "FALSE",
     "evidence": {"wind": 50}, "checks": [{"field": "wind_speed_10m", "op": "<", "threshold": 5, "value": 50}]},
]


def V(action, lead=None, reply="", also=None, follow=None):
    d = {"action": action, "lead_sop": lead, "also_cite": also or [], "follow_up_question": follow, "reply": reply}
    return verify_advice(d, RECORDS, [], POL)


def test_verify_advice_accepts_valid_advise():
    ok, det = V("advise", "FX-WIND-01", "Wind is 50 km/h, a risk [FX-WIND-01].")
    assert ok, det


def test_verify_advice_rejects_hazard_that_is_not_true():
    ok, det = V("advise", "FX-CALM-01", "Danger [FX-CALM-01].")      # FX-CALM-01 is FALSE
    assert not ok and "requires lead SOP TRUE" in det["reason"]


def test_verify_advice_accepts_reassure_on_false_sop():
    ok, det = V("reassure", "FX-CALM-01", "No concern; wind 50 is above the 5 threshold [FX-CALM-01].")
    assert ok, det


def test_verify_advice_reassure_requires_false_not_true():
    ok, det = V("reassure", "FX-WIND-01", "No concern [FX-WIND-01].")   # FX-WIND-01 is TRUE
    assert not ok and "requires lead SOP FALSE" in det["reason"]


def test_verify_advice_rejects_unknown_id_and_ungrounded_number():
    ok, det = V("advise", "FX-WIND-01", "Per [FX-NOPE-99] wind is 50 km/h [FX-WIND-01].")
    assert not ok and "unknown SOP ids" in det["reason"]
    ok, det = V("advise", "FX-WIND-01", "Wind is 999 km/h [FX-WIND-01].")
    assert not ok and "ungrounded numbers" in det["reason"]


def test_verify_advice_requires_citation_of_lead():
    ok, det = V("advise", "FX-WIND-01", "Conditions are risky.")        # no [FX-WIND-01]
    assert not ok and "does not cite lead" in det["reason"]


def test_verify_advice_clarify_needs_question():
    assert V("clarify", reply="?", follow="Which activity?")[0]
    assert not V("clarify", reply="?")[0]


def test_parse_json_decision_handles_fences_and_prose():
    d = _parse_json_decision('```json\n{"action":"clarify","follow_up_question":"Which city?","reply":"Which city?"}\n```')
    assert d["action"] == "clarify" and d["follow_up_question"] == "Which city?"
    d2 = _parse_json_decision('Here:\n{"action":"no_guidance","reply":"No policy applies."} thanks')
    assert d2["action"] == "no_guidance" and d2["reply"] == "No policy applies."
    with pytest.raises(ValueError):
        _parse_json_decision('{"action":"banana","reply":"x"}')


# ---------- advise node, driven by a stubbed advisor (no LLM) ----------
def app_with(decision_or_fn, snap):
    adv = decision_or_fn if callable(decision_or_fn) else (lambda payload: dict(decision_or_fn))
    return build_graph(FIXTURE, FixtureClient(snap, GEO),
                       ScriptedParser(intent(location_text="Bhopal", activities=["cycling"])),
                       advisor=adv)


def test_advise_node_true_hazard_is_used():
    snap = full_snapshot(current={"wind_speed_10m": 50})            # FX-WIND-01 TRUE
    r = ask(app_with(_coerce_decision(
        {"action": "advise", "lead_sop": "FX-WIND-01", "reply": "Wind is 50 km/h, a risk [FX-WIND-01]."}), snap), "t", "bike?")
    assert r["branch"] == "advise" and r["reply_source"] == "llm" and "FX-WIND-01" in r["reply"]
    assert r["trace"]["advisor_action"] == "advise"


def test_advise_node_reassure_is_used():
    snap = full_snapshot(current={"wind_speed_10m": 10})            # FX-WIND-01 FALSE (>40)
    r = ask(app_with(_coerce_decision(
        {"action": "reassure", "lead_sop": "FX-WIND-01", "reply": "No concern; wind is 10 km/h, below 40 [FX-WIND-01]."}), snap), "t", "bike?")
    assert r["branch"] == "reassure" and r["reply_source"] == "llm" and "FX-WIND-01" in r["reply"]


def test_advise_node_clarify_returns_the_question():
    snap = full_snapshot()
    r = ask(app_with({"action": "clarify", "lead_sop": None, "also_cite": [], "follow_up_question": "Cycling or driving?",
                      "reply": "Are you cycling or driving?"}, snap), "t", "going out?")
    assert r["branch"] == "clarify" and "cycling" in r["reply"].lower()


def test_advise_node_falls_back_when_guardrail_trips():
    snap = full_snapshot(current={"wind_speed_10m": 10})            # FX-WIND-01 is FALSE
    # advisor wrongly claims a hazard on a FALSE SOP -> guardrail rejects -> deterministic fallback.
    # The engine reassures (checked, threshold not met), never presents the FALSE SOP as a live hazard.
    r = ask(app_with(_coerce_decision(
        {"action": "advise", "lead_sop": "FX-WIND-01", "reply": "Danger! [FX-WIND-01]"}), snap), "t", "bike?")
    assert r["trace"].get("advisor_rejected") and r["reply_source"] == "fallback_template"
    assert r["branch"] == "reassure" and "threshold" in r["reply"].lower()


def test_advise_node_fallback_on_advisor_exception():
    snap = full_snapshot(current={"wind_speed_10m": 50})            # FX-WIND-01 TRUE
    def boom(payload):
        raise RuntimeError("provider down")
    r = ask(app_with(boom, snap), "t", "bike?")
    assert "provider down" in r["trace"]["advisor_rejected"] and r["reply_source"] == "fallback_template"
    assert r["branch"] == "advise" and "FX-WIND-01" in r["reply"]   # deterministic engine still answers
