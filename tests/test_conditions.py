import pytest

from weather_advisor.conditions import (EvalContext, FALSE, TRUE, UNKNOWN, MissingEvidence,
                                        evaluate, fmt_number, render_advice)
from helpers import snapshot


def sop(fixture_sops, sid):
    return next(s for s in fixture_sops.sops if s.id == sid)


def run(fixture_sops, sid, snap, tr=None):
    s = sop(fixture_sops, sid)
    return evaluate(s.condition, EvalContext(snap, fixture_sops.vocabulary, tr))


# ---- compare boundaries (strict > vs inclusive >=) ----
@pytest.mark.parametrize("w,exp", [(40, FALSE), (40.1, TRUE), (39.9, FALSE)])
def test_strict_greater_boundary(fixture_sops, w, exp):
    assert run(fixture_sops, "FX-WIND-01", snapshot(current={"wind_speed_10m": w})).value == exp


@pytest.mark.parametrize("w,exp", [(60, TRUE), (59.9, FALSE)])
def test_inclusive_boundary(fixture_sops, w, exp):
    assert run(fixture_sops, "FX-WIND-02", snapshot(current={"wind_speed_10m": w})).value == exp


def test_missing_and_null_are_unknown(fixture_sops):
    assert run(fixture_sops, "FX-WIND-01", snapshot()).value == UNKNOWN
    r = run(fixture_sops, "FX-WIND-01", snapshot(current={"wind_speed_10m": None}))
    assert r.value == UNKNOWN and "missing or null" in r.trace[0]["reason"]


def test_in_set(fixture_sops):
    assert run(fixture_sops, "FX-THUNDER-01", snapshot(current={"weather_code": 95})).value == TRUE
    assert run(fixture_sops, "FX-THUNDER-01", snapshot(current={"weather_code": 61})).value == FALSE


# ---- fixed windows: start inclusive, end exclusive ----
def uv_series(**spikes):
    s = [0.0] * 48
    for h, v in spikes.items():
        s[int(h[1:])] = v
    return s


@pytest.mark.parametrize("hour,exp", [("h11", TRUE), ("h15", TRUE), ("h16", FALSE), ("h10", FALSE)])
def test_window_start_inclusive_end_exclusive(fixture_sops, hour, exp):
    snap = snapshot(hourly={"uv_index": uv_series(**{hour: 9})})
    assert run(fixture_sops, "FX-UV-01", snap).value == exp


def test_window_evidence_and_threshold(fixture_sops):
    r = run(fixture_sops, "FX-UV-01", snapshot(hourly={"uv_index": uv_series(h12=8)}))
    assert r.value == TRUE and r.evidence["uv_peak"] == 8
    assert run(fixture_sops, "FX-UV-01", snapshot(hourly={"uv_index": uv_series(h12=7.9)})).value == FALSE


def test_window_with_null_is_strict_unknown(fixture_sops):
    s = uv_series(h12=9)
    s[13] = None
    r = run(fixture_sops, "FX-UV-01", snapshot(hourly={"uv_index": s}))
    assert r.value == UNKNOWN and "13:00" in r.trace[0]["reason"]


def test_window_with_missing_hours_is_unknown(fixture_sops):
    snap = snapshot(hourly={"uv_index": 9})
    snap["hourly"]["time"] = snap["hourly"]["time"][:12]   # data ends before the window
    snap["hourly"]["uv_index"] = snap["hourly"]["uv_index"][:12]
    assert run(fixture_sops, "FX-UV-01", snap).value == UNKNOWN


# ---- window from time reference ----
def test_time_reference_window(fixture_sops):
    rain = [0] * 48
    rain[20] = 80       # 20:00 today
    snap = snapshot(hourly={"precipitation_probability": rain})
    assert run(fixture_sops, "FX-RAIN-TRAVEL-01", snap, "evening").value == TRUE
    assert run(fixture_sops, "FX-RAIN-TRAVEL-01", snap, "morning").value == FALSE
    rain2 = [0] * 48
    rain2[30] = 80      # 06:00 tomorrow
    snap2 = snapshot(hourly={"precipitation_probability": rain2})
    assert run(fixture_sops, "FX-RAIN-TRAVEL-01", snap2, "tomorrow").value == TRUE
    assert run(fixture_sops, "FX-RAIN-TRAVEL-01", snap2, "today").value == FALSE


def test_time_reference_missing_or_unknown_tag_is_unknown(fixture_sops):
    snap = snapshot(hourly={"precipitation_probability": 90})
    assert run(fixture_sops, "FX-RAIN-TRAVEL-01", snap, None).value == UNKNOWN
    assert run(fixture_sops, "FX-RAIN-TRAVEL-01", snap, "bogus").value == UNKNOWN


# ---- daily ----
def test_daily_tomorrow(fixture_sops):
    snap = snapshot(daily={"precipitation_sum": [0, 50, 0]})
    assert run(fixture_sops, "FX-TOMORROW-RAIN-01", snap).value == TRUE
    snap = snapshot(daily={"precipitation_sum": [99, 49.9, 0]})
    assert run(fixture_sops, "FX-TOMORROW-RAIN-01", snap).value == FALSE
    snap = snapshot(daily={"precipitation_sum": [0, None, 0]})
    assert run(fixture_sops, "FX-TOMORROW-RAIN-01", snap).value == UNKNOWN


# ---- combinators: Kleene logic ----
def leaf(v):
    return {"compare": {"field": "x", "source": "current", "op": ">", "value": 1}} if v is not None else \
           {"compare": {"field": "missing", "source": "current", "op": ">", "value": 1}}


def ev(node):
    return evaluate(node, EvalContext(snapshot(current={"x": 5}), {}, None)).value


def test_kleene_logic():
    t = {"compare": {"field": "x", "source": "current", "op": ">", "value": 1}}
    f = {"compare": {"field": "x", "source": "current", "op": "<", "value": 1}}
    u = {"compare": {"field": "nope", "source": "current", "op": ">", "value": 1}}
    assert ev({"all": [t, u]}) == UNKNOWN and ev({"all": [f, u]}) == FALSE and ev({"all": [t, t]}) == TRUE
    assert ev({"any": [f, u]}) == UNKNOWN and ev({"any": [t, u]}) == TRUE and ev({"any": [f, f]}) == FALSE
    assert ev({"not": u}) == UNKNOWN and ev({"not": t}) == FALSE and ev({"not": f}) == TRUE


# ---- situational (all of several non-extreme signals) ----
def test_situational_override(fixture_sops):
    rain = [0] * 48
    for h in range(8, 20):
        rain[h] = 1.0        # 12 mm over today
    snap = snapshot(current={"surface_pressure": 995}, hourly={"precipitation": rain})
    r = run(fixture_sops, "FX-SITUATION-01", snap, "today")
    assert r.value == TRUE and r.evidence == {"pressure": 995, "rain_total": 12}
    snap = snapshot(current={"surface_pressure": 1005}, hourly={"precipitation": rain})
    assert run(fixture_sops, "FX-SITUATION-01", snap, "today").value == FALSE


# ---- fuzzy score ----
def picnic_snap(temp, wind, rain):
    return snapshot(current={"temperature_2m": temp, "wind_speed_10m": wind},
                    hourly={"precipitation_probability": rain})


def test_score_true_with_label_and_evidence(fixture_sops):
    r = run(fixture_sops, "FX-PICNIC-01", picnic_snap(22, 10, 5))
    assert r.value == TRUE and r.evidence["picnic_value"] == 1 and r.evidence["picnic_label"] == "very good"
    assert r.trace[0]["terms"][2]["contribution"] == 2
    text = render_advice(sop(fixture_sops, "FX-PICNIC-01").advice, r.evidence)
    assert text.startswith("Picnic conditions look very good (comfort score 1): 22 C")


def test_score_weighting_and_false(fixture_sops):
    # temp 1.0, wind 0.5, rain 0.5*2 -> (1 + .5 + 1)/4 = 0.625 -> fair, TRUE
    r = run(fixture_sops, "FX-PICNIC-01", picnic_snap(20, 20, 30))
    assert r.value == TRUE and r.evidence["picnic_value"] == pytest.approx(0.625)
    assert r.evidence["picnic_label"] == "fair"
    # rain heavy: (1+1+0)/4 = .5 -> FALSE
    r = run(fixture_sops, "FX-PICNIC-01", picnic_snap(20, 5, 80))
    assert r.value == FALSE and r.evidence["picnic_value"] == pytest.approx(0.5)


def test_score_unknown_if_any_term_unknown(fixture_sops):
    snap = picnic_snap(22, 10, 5)
    del snap["current"]["wind_speed_10m"]
    r = run(fixture_sops, "FX-PICNIC-01", snap)
    assert r.value == UNKNOWN and r.evidence == {}


# ---- rendering ----
def test_fmt_and_render():
    assert fmt_number(7.0) == "7" and fmt_number(7.25) == "7.2" and fmt_number(0.05) == "0.1"
    assert render_advice("{a} km/h", {"a": 12.0}) == "12 km/h"
    with pytest.raises(MissingEvidence):
        render_advice("{a}", {})
