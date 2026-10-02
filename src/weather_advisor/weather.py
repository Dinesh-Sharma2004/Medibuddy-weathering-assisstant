"""Open-Meteo clients. The client is injectable so tests use fixtures and fault injection.

A client implements two methods:
  geocode(name) -> list of candidate dicts (may be empty)
  forecast(lat, lon, fields) -> raw Open-Meteo JSON (dict)
and signals trouble by raising WeatherError. build_snapshot() then decides whether the
payload is usable. Nothing here knows any SOP field name: `fields` comes from the SOP file.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT_S = 10
GEOCODE_COUNT = 5
FORECAST_DAYS = 2   # today + tomorrow (enough for windows on either day)


class WeatherError(Exception):
    """kind: timeout | connection | http_error | malformed | unusable"""
    def __init__(self, kind: str, detail: str = ""):
        self.kind, self.detail = kind, detail
        super().__init__(f"{kind}: {detail}")


class WeatherClient(Protocol):
    def geocode(self, name: str) -> list[dict[str, Any]]: ...
    def forecast(self, lat: float, lon: float, fields: dict[str, list[str]]) -> dict[str, Any]: ...


def _get_json(url: str, params: dict) -> Any:
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_S)
    except requests.Timeout as e:
        raise WeatherError("timeout", str(e)) from e
    except requests.RequestException as e:
        raise WeatherError("connection", str(e)) from e
    if r.status_code != 200:
        raise WeatherError("http_error", f"HTTP {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except ValueError as e:
        raise WeatherError("malformed", "response is not JSON") from e


def forecast_params(lat: float, lon: float, fields: dict[str, list[str]]) -> dict[str, Any]:
    """Explicit lat/lon and explicit field lists per section; times in the location's own timezone."""
    params: dict[str, Any] = {"latitude": lat, "longitude": lon, "timezone": "auto",
                              "forecast_days": FORECAST_DAYS}
    for section in ("current", "hourly", "daily"):
        if fields.get(section):
            params[section] = ",".join(fields[section])
    return params


class OpenMeteoClient:
    def geocode(self, name: str) -> list[dict[str, Any]]:
        data = _get_json(GEOCODE_URL, {"name": name, "count": GEOCODE_COUNT, "language": "en"})
        if not isinstance(data, dict):
            raise WeatherError("malformed", "geocoding response is not an object")
        results = data.get("results") or []   # Open-Meteo omits 'results' when nothing matches
        if not isinstance(results, list):
            raise WeatherError("malformed", "geocoding 'results' is not a list")
        return results

    def forecast(self, lat, lon, fields):
        return _get_json(FORECAST_URL, forecast_params(lat, lon, fields))


class FixtureClient:
    """Serves recorded / hand-written JSON. `forecast_payload` may be a dict or a path to a JSON file."""
    def __init__(self, forecast_payload: dict | str | Path, geocode_results: dict[str, list] | None = None):
        if isinstance(forecast_payload, (str, Path)):
            forecast_payload = json.loads(Path(forecast_payload).read_text())
        self.payload = forecast_payload
        self.geo = {k.lower(): v for k, v in (geocode_results or {}).items()}
        self.forecast_calls: list[tuple] = []

    def geocode(self, name):
        return copy.deepcopy(self.geo.get(name.strip().lower(), []))

    def forecast(self, lat, lon, fields):
        self.forecast_calls.append((lat, lon, fields))
        return copy.deepcopy(self.payload)


class FaultInjectingClient:
    """Wraps a client and raises/returns a fault. fault in:
    forecast_timeout | forecast_connection | forecast_http_500 | forecast_malformed |
    geocode_empty | geocode_error"""
    FAULTS = {"forecast_timeout", "forecast_connection", "forecast_http_500", "forecast_malformed",
              "geocode_empty", "geocode_error"}

    def __init__(self, inner: WeatherClient, fault: str):
        if fault not in self.FAULTS:
            raise ValueError(f"unknown fault {fault!r}")
        self.inner, self.fault = inner, fault

    def geocode(self, name):
        if self.fault == "geocode_empty":
            return []
        if self.fault == "geocode_error":
            raise WeatherError("http_error", "injected geocoding failure")
        return self.inner.geocode(name)

    def forecast(self, lat, lon, fields):
        f = self.fault
        if f == "forecast_timeout":
            raise WeatherError("timeout", "injected")
        if f == "forecast_connection":
            raise WeatherError("connection", "injected")
        if f == "forecast_http_500":
            raise WeatherError("http_error", "injected HTTP 500")
        if f == "forecast_malformed":
            return {"unexpected": "payload"}
        return self.inner.forecast(lat, lon, fields)


def build_snapshot(raw: Any, fields: dict[str, list[str]], now_utc: datetime | None = None) -> dict[str, Any]:
    """Validate the payload's structure and return the snapshot the evaluator uses.

    Individual null values are allowed (they become UNKNOWN downstream). A missing or
    malformed requested section, or a missing time axis, makes the whole payload unusable.
    """
    if not isinstance(raw, dict) or raw.get("error"):
        raise WeatherError("malformed", "payload is not a weather object")
    snap: dict[str, Any] = {"timezone": raw.get("timezone"), "utc_offset_seconds": raw.get("utc_offset_seconds")}
    for section, names in fields.items():
        if not names:
            continue
        body = raw.get(section)
        if not isinstance(body, dict) or not isinstance(body.get("time"), (str, list)):
            raise WeatherError("unusable", f"payload has no usable '{section}' section")
        if section == "current":
            if not isinstance(body["time"], str):
                raise WeatherError("unusable", "current.time is not a string")
        else:
            if not (isinstance(body["time"], list) and body["time"]):
                raise WeatherError("unusable", f"{section}.time is not a non-empty list")
            for n in names:
                if n in body and not (isinstance(body[n], list) and len(body[n]) == len(body["time"])):
                    raise WeatherError("unusable", f"{section}.{n} does not align with {section}.time")
        snap[section] = body
    if "current" not in snap and "hourly" not in snap and "daily" not in snap:
        raise WeatherError("unusable", "no weather sections requested")
    # Location-local "now" anchors `today`/`tomorrow` windows. Prefer the API's own current.time;
    # if no current field was requested, derive it from the UTC clock plus the API's utc_offset_seconds.
    if "current" in snap:
        snap["now_local"] = snap["current"]["time"]
    else:
        off = raw.get("utc_offset_seconds")
        if not isinstance(off, (int, float)) or isinstance(off, bool):
            raise WeatherError("unusable", "payload has neither current.time nor utc_offset_seconds")
        local = (now_utc or datetime.now(timezone.utc)) + timedelta(seconds=off)
        snap["now_local"] = local.strftime("%Y-%m-%dT%H:%M")
    return snap
