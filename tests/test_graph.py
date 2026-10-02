import shutil

import pytest
import yaml

from conftest import FIXTURE
from helpers import GEO, ScriptedParser, full_snapshot, intent
from weather_advisor.graph import ask, build_graph
from weather_advisor.weather import FaultInjectingClient, FixtureClient, build_snapshot, WeatherError


def app_for(parser, snap=None, geo=GEO, sop_path=FIXTURE, client=None, **kw):
    client = client or FixtureClient(snap if snap is not None else full_snapshot(), geo)
    return build_graph(sop_path, client, parser, **kw), client


BIKE = dict(location_text="Bhopal", activities=["cycling"], question_types=["safety_check"])


def test_advice_branch_and_trace():
    app, _ = app_for(ScriptedParser(intent(**BIKE)), full_snapshot(current={"wind_speed_10m": 50}))
    r = ask(app, "t", "bike?")
    t = r["trace"]
    assert r["branch"] == "compose" and r["reply_source"] == "fallback_template"
    assert t["primary_sop"] == "FX-WIND-01" and t["matched_sops"] == ["FX-WIND-01"]
    assert "Wind is 50 km/h" in r["reply"] and "Bhopal, Madhya Pradesh, India" in r["reply"]
    assert t["chosen_place"]["label"] == "Bhopal, Madhya Pradesh, India"
    assert {e["id"]: e["effective"] for e in t["sop_evaluations"]}["FX-UV-01"] == "FALSE"


def test_weather_request_is_union_of_requires():
    app, client = app_for(ScriptedParser(intent(**BIKE)))
    r = ask(app, "t", "x")
    req = r["trace"]["weather_request"]
    assert req["timezone"] == "auto" and req["latitude"] == 23.25
    assert "uv_index" in req["hourly"] and "precipitation_sum" in req["daily"] and "weather_code" in req["current"]
    assert "weather_code" in client.forecast_calls[0][2]["current"]


def test_out_of_scope_insufficient_and_ask_location():
    app, _ = app_for(ScriptedParser(intent(in_scope=False), intent(), intent(activities=["cycling"])))
    assert ask(app, "t", "stocks?")["branch"] == "out_of_scope"
    assert ask(app, "t", "hmm")["branch"] == "insufficient_intent"
    r = ask(app, "t", "can I cycle?")
    assert r["branch"] == "ask_location" and "city" in r["reply"]


@pytest.mark.parametrize("fault,branch", [
    ("geocode_empty", "location_unresolved"), ("geocode_error", "location_unresolved"),
    ("forecast_timeout", "weather_unavailable"), ("forecast_connection", "weather_unavailable"),
    ("forecast_http_500", "weather_unavailable"), ("forecast_malformed", "weather_unavailable")])
def test_faults_fail_honestly(fault, branch):
    inner = FixtureClient(full_snapshot(current={"wind_speed_10m": 99}), GEO)
    app, _ = app_for(ScriptedParser(intent(**BIKE)), client=FaultInjectingClient(inner, fault))
    r = ask(app, "t", "bike?")
    assert r["branch"] == branch and "failure_reason" in r["trace"]
    assert "matched_sops" not in r["trace"] and not any(ch.isdigit() for ch in r["reply"])


def test_unknown_place_goes_to_location_branch():
    app, _ = app_for(ScriptedParser(intent(**{**BIKE, "location_text": "Nowhereville"})))
    assert ask(app, "t", "x")["branch"] == "location_unresolved"


def test_no_guidance_when_nothing_applies_or_nothing_true():
    app, _ = app_for(ScriptedParser(intent(location_text="Bhopal", activities=["walking"], question_types=["safety_check"])))
    r = ask(app, "t", "walk?")
    assert r["branch"] == "no_guidance" and r["trace"]["outcome"] == "no_guidance"
    assert "matched_sops" in r["trace"] and r["trace"]["primary_sop"] is None


def test_material_unknown_with_no_true_is_data_unavailable():
    snap = full_snapshot()
    del snap["current"]["temperature_2m"]    # FX-COLD-01 (advisory, below 'warning') becomes UNKNOWN
    app, _ = app_for(ScriptedParser(intent(location_text="Bhopal", groups=["elderly"])),
                     snap)
    r = ask(app, "t", "x")
    ev = {e["id"]: e["effective"] for e in r["trace"]["sop_evaluations"]}
    assert ev["FX-COLD-01"] == "UNKNOWN" and ev["FX-HEAT-01"] == "UNKNOWN"
    # FX-HEAT-01 is 'warning' -> material -> data_unavailable
    assert r["branch"] == "data_unavailable"


def test_data_unavailable_distinct_from_no_guidance():
    snap = full_snapshot()
    snap["current"]["wind_speed_10m"] = None
    app, _ = app_for(ScriptedParser(intent(location_text="Bhopal", activities=["running"], question_types=["safety_check"]),
                                    intent(location_text="Bhopal", activities=["walking"])), snap)
    r = ask(app, "t", "run?")   # FX-WIND-02 (critical, applies to any) UNKNOWN, nothing TRUE
    assert r["branch"] == "data_unavailable" and "FX-WIND-02" in r["trace"]["disclosed_unknown_sops"]
    assert "could not be fully evaluated" in r["reply"]


def test_true_match_plus_material_unknown_is_disclosed():
    snap = full_snapshot(current={"wind_speed_10m": 50})
    snap["current"]["weather_code"] = None            # FX-THUNDER-01 critical UNKNOWN
    app, _ = app_for(ScriptedParser(intent(**BIKE)), snap)
    r = ask(app, "t", "bike?")
    assert r["trace"]["primary_sop"] == "FX-WIND-01"
    assert "could not check FX-THUNDER-01" in r["reply"]


def test_true_condition_with_unrenderable_advice_becomes_unknown(tmp_path):
    raw = yaml.safe_load(FIXTURE.read_text())
    sop = next(s for s in raw["sops"] if s["id"] == "FX-WIND-02")
    sop["condition"] = {"any": [
        {"compare": {"field": "wind_speed_10m", "source": "current", "op": ">=", "value": 60, "as": "wind"}},
        {"compare": {"field": "weather_code", "source": "current", "op": "in", "value": [95], "as": "code"}}]}
    sop["requires"].append({"field": "weather_code", "source": "current"})
    sop["advice"] = "Wind {wind}, code {code}."
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump(raw))
    snap = full_snapshot(current={"wind_speed_10m": 70})
    snap["current"]["weather_code"] = None
    app, _ = app_for(ScriptedParser(intent(**BIKE)), snap, sop_path=p)
    r = ask(app, "t", "x")
    e = next(e for e in r["trace"]["sop_evaluations"] if e["id"] == "FX-WIND-02")
    assert e["result"] == "TRUE" and e["effective"] == "UNKNOWN" and "needs {code}" in e["render_blocked"]
    assert "FX-WIND-02" not in r["trace"]["matched_sops"]
    assert "FX-WIND-02" in r["trace"]["disclosed_unknown_sops"]


def test_unrelated_unknown_does_not_downgrade():
    snap = full_snapshot(current={"wind_speed_10m": 50})
    snap["current"]["precipitation"] = None
    app, _ = app_for(ScriptedParser(intent(**BIKE)), snap)
    assert ask(app, "t", "x")["trace"]["primary_sop"] == "FX-WIND-01"


def test_conflict_severity_then_priority_then_id():
    snap = full_snapshot(current={"wind_speed_10m": 65})   # FX-WIND-01 (warning) + FX-WIND-02 (critical)
    app, _ = app_for(ScriptedParser(intent(**BIKE)), snap)
    t = ask(app, "t", "x")["trace"]
    assert t["primary_sop"] == "FX-WIND-02" and t["secondary_sops"] == ["FX-WIND-01"]


def test_conflict_larger_priority_wins_on_equal_severity(tmp_path):
    raw = yaml.safe_load(FIXTURE.read_text())
    for s in raw["sops"]:
        if s["id"] in ("FX-WIND-01", "FX-UV-01"):
            s["severity"] = "warning"
    next(s for s in raw["sops"] if s["id"] == "FX-WIND-01")["priority"] = 4
    next(s for s in raw["sops"] if s["id"] == "FX-UV-01")["priority"] = 5
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump(raw))
    snap = full_snapshot(current={"wind_speed_10m": 45}, hourly={"uv_index": 9})
    app, _ = app_for(ScriptedParser(intent(**BIKE)), snap, sop_path=p)
    t = ask(app, "t", "x")["trace"]
    assert t["primary_sop"] == "FX-UV-01" and t["secondary_sops"] == ["FX-WIND-01"]


def test_override_leads_even_over_higher_severity():
    snap = full_snapshot(current={"wind_speed_10m": 65, "surface_pressure": 990}, hourly={"precipitation": 1})
    app, _ = app_for(ScriptedParser(intent(**BIKE)), snap)
    r = ask(app, "t", "x")
    t = r["trace"]
    assert t["primary_sop"] == "FX-SITUATION-01" and "FX-WIND-02" in t["secondary_sops"]
    assert r["reply"].index("[FX-SITUATION-01]") < r["reply"].index("[FX-WIND-02]")


def test_session_followup_replaces_only_time_and_new_city_replaces_old():
    rain = [0] * 48
    rain[20] = 90
    snap = full_snapshot(hourly={"precipitation_probability": rain})
    app, _ = app_for(ScriptedParser(
        intent(location_text="Bhopal", activities=["cycling"], question_types=["travel_delay"], time_reference="morning"),
        intent(time_reference="evening"),
        intent(location_text="Delhi")), snap)
    r1 = ask(app, "s", "q1")
    assert r1["trace"]["matched_sops"] == []
    r2 = ask(app, "s", "what about this evening?")
    assert r2["trace"]["matched_sops"] == ["FX-RAIN-TRAVEL-01"]
    assert r2["trace"]["intent"]["location_text"] == "Bhopal" and r2["trace"]["inherited_from_session"]
    r3 = ask(app, "s", "and Delhi?")
    assert r3["trace"]["chosen_place"]["label"] == "Delhi, Delhi, India"
    assert r3["trace"]["intent"]["time_reference"] == "evening"


def test_default_time_reference_comes_from_yaml_and_threads_are_isolated():
    app, _ = app_for(ScriptedParser(intent(**BIKE), intent(activities=["cycling"])))
    assert ask(app, "a", "x")["trace"]["intent"]["time_reference"] == "today"
    assert ask(app, "b", "x")["branch"] == "ask_location"      # fresh thread: nothing inherited


def test_explain_uses_decision_log():
    app, _ = app_for(ScriptedParser(intent(**BIKE), intent(asks_for_explanation=True)),
                     full_snapshot(current={"wind_speed_10m": 50}))
    ask(app, "s", "bike?")
    r = ask(app, "s", "why did you say that?")
    assert r["branch"] == "explain" and "FX-WIND-01" in r["reply"] and "wind=50" in r["reply"]
    assert "Bhopal" in r["reply"] and "2026-09-04T13:30" in r["reply"]
    assert "fetch_weather" not in r["trace"]


def test_explain_with_no_history():
    app, _ = app_for(ScriptedParser(intent(asks_for_explanation=True)))
    r = ask(app, "s", "why?")
    assert r["branch"] == "explain" and "nothing to explain" in r["reply"]


def test_sop_file_is_reread_each_request(tmp_path):
    p = tmp_path / "s.yaml"
    shutil.copy(FIXTURE, p)
    app, _ = app_for(ScriptedParser(intent(**BIKE), intent(**BIKE)), full_snapshot(current={"wind_speed_10m": 45}), sop_path=p)
    assert ask(app, "t", "x")["trace"]["primary_sop"] == "FX-WIND-01"
    raw = yaml.safe_load(p.read_text())
    next(s for s in raw["sops"] if s["id"] == "FX-WIND-01")["condition"]["compare"]["value"] = 50
    p.write_text(yaml.safe_dump(raw))
    assert ask(app, "t", "x")["trace"]["primary_sop"] is None


def test_invalid_sop_file_never_answers(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("meta: {}\n")
    app, _ = app_for(ScriptedParser(intent(**BIKE)), sop_path=p)
    r = ask(app, "t", "x")
    assert r["branch"] == "policy_error" and r["trace"]["policy_errors"]


def test_unknown_tags_from_parser_are_dropped():
    app, _ = app_for(ScriptedParser(intent(location_text="Bhopal", activities=["cycling", "skydiving"])))
    t = ask(app, "t", "x")["trace"]
    assert t["intent"]["activities"] == ["cycling"] and t["dropped_tags"] == {"activities": ["skydiving"]}


def test_build_snapshot_rejects_unusable():
    with pytest.raises(WeatherError):
        build_snapshot({"hourly": {"time": ["a"]}}, {"current": ["x"]})
    with pytest.raises(WeatherError):
        build_snapshot({"current": {"x": 1}}, {"current": ["x"]})
    with pytest.raises(WeatherError):
        build_snapshot({"hourly": {"time": ["a", "b"], "x": [1]}}, {"hourly": ["x"]})


def test_unknown_below_disclosure_threshold_is_no_guidance_but_traced():
    snap = full_snapshot()
    del snap["current"]["temperature_2m"]   # FX-COLD-01 is 'advisory' (< warning); elderly also triggers FX-HEAT-01
    app, _ = app_for(ScriptedParser(intent(location_text="Bhopal", groups=["children"])), snap)
    r = ask(app, "t", "x")
    ev = {e["id"]: e["effective"] for e in r["trace"]["sop_evaluations"]}
    assert ev["FX-COLD-01"] == "UNKNOWN" and r["branch"] == "data_unavailable"   # FX-HEAT-01 (warning) also UNKNOWN


def test_hourly_only_sops_still_resolve_today_from_clock():
    from datetime import datetime, timezone
    raw = {"utc_offset_seconds": 19800, "hourly": {"time": ["2026-09-04T11:00", "2026-09-04T12:00"], "x": [1, 2]}}
    snap = build_snapshot(raw, {"hourly": ["x"]}, datetime(2026, 9, 4, 5, 0, tzinfo=timezone.utc))
    assert snap["now_local"] == "2026-09-04T10:30"
    with pytest.raises(WeatherError):
        build_snapshot({"hourly": {"time": ["a"], "x": [1]}}, {"hourly": ["x"]})   # no offset, no current
