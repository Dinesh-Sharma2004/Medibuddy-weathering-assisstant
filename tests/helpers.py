"""Hand-built snapshots for unit tests (Open-Meteo shape, location-local times)."""
from datetime import datetime, timedelta


def snapshot(now="2026-09-04T13:30", current=None, hourly=None, daily=None):
    t0 = datetime.fromisoformat(now)
    day0 = datetime(t0.year, t0.month, t0.day)
    times = [(day0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
    hourly = hourly or {}
    h = {"time": times}
    for k, v in hourly.items():
        h[k] = list(v) if isinstance(v, (list, tuple)) else [v] * 48
    dates = [(day0 + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(3)]
    d = {"time": dates}
    for k, v in (daily or {}).items():
        d[k] = list(v) if isinstance(v, (list, tuple)) else [v] * 3
    return {"current": {"time": now, **(current or {})}, "hourly": h, "daily": d}


FULL_CURRENT = {"temperature_2m": 25, "wind_speed_10m": 5, "precipitation": 0, "weather_code": 0,
                "surface_pressure": 1010}
FULL_HOURLY = {"uv_index": 1, "precipitation": 0, "precipitation_probability": 0}
FULL_DAILY = {"precipitation_sum": 0}


def full_snapshot(current=None, hourly=None, daily=None, now="2026-09-04T13:30"):
    """Every field every fixture SOP needs, calm values; override what a test cares about."""
    return snapshot(now, {**FULL_CURRENT, **(current or {})}, {**FULL_HOURLY, **(hourly or {})},
                    {**FULL_DAILY, **(daily or {})})


BHOPAL = [{"name": "Bhopal", "admin1": "Madhya Pradesh", "country": "India", "latitude": 23.25, "longitude": 77.4}]
DELHI = [{"name": "Delhi", "admin1": "Delhi", "country": "India", "latitude": 28.6, "longitude": 77.2}]
GEO = {"bhopal": BHOPAL, "delhi": DELHI}


def intent(**kw):
    base = {"in_scope": True, "location_text": None, "activities": [], "groups": [], "question_types": [],
            "time_reference": None, "asks_for_explanation": False}
    return {**base, **kw}


class ScriptedParser:
    """Stands in for the LLM parser: returns pre-set raw intents in order."""
    def __init__(self, *intents):
        self.intents = list(intents)

    def __call__(self, text, policy, session):
        return self.intents.pop(0)
