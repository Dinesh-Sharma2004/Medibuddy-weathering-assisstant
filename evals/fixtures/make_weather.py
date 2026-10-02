"""Regenerates evals/fixtures/weather/*.json: hand-written Open-Meteo-shaped payloads (NOT recorded live data).
Fixed 'now' = 2026-09-04T13:30 local so logic evals never depend on the real date or weather.
Run: python evals/fixtures/make_weather.py
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "weather"
DAY = datetime(2026, 9, 4)
HOURS = [(DAY + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]


def payload(current=None, hourly=None, daily=None):
    cur = {"time": "2026-09-04T13:30", "interval": 900, "temperature_2m": 25, "wind_speed_10m": 5,
           "precipitation": 0, "weather_code": 0, "surface_pressure": 1010, "relative_humidity_2m": 40}
    cur.update(current or {})
    hr = {"uv_index": [1] * 48, "precipitation": [0] * 48, "precipitation_probability": [0] * 48}
    for name, spec in (hourly or {}).items():
        if isinstance(spec, dict):
            for h, v in spec.items():
                hr[name][int(h)] = v
        else:
            hr[name] = [spec] * 48
    dl = {"precipitation_sum": [0, 0]}
    dl.update(daily or {})
    return {"latitude": 23.25, "longitude": 77.4, "utc_offset_seconds": 19800, "timezone": "Asia/Kolkata",
            "current": cur, "hourly": {"time": HOURS, **hr}, "daily": {"time": ["2026-09-04", "2026-09-05"], **dl}}


FILES = {
    "calm": payload(),
    "wind_50": payload({"wind_speed_10m": 50}),
    "wind_40": payload({"wind_speed_10m": 40}),
    "wind_40_1": payload({"wind_speed_10m": 40.1}),
    "wind_null": payload({"wind_speed_10m": None}),
    "unknown_and_uv": payload({"wind_speed_10m": None}, hourly={"uv_index": {"12": 9}}),
    "uv_high": payload(hourly={"uv_index": {"12": 9}}),
    "conflict": payload({"wind_speed_10m": 65}, hourly={"uv_index": {"12": 9}}),
    "rain_evening": payload(hourly={"precipitation_probability": {"20": 90}}),
    "picnic_good": payload({"temperature_2m": 22, "wind_speed_10m": 10}, hourly={"precipitation_probability": {"12": 5}}),
    "heat_40": payload({"temperature_2m": 40}),
    "storm": payload({"weather_code": 95, "wind_speed_10m": 65, "surface_pressure": 990, "precipitation": 4},
                     hourly={"precipitation": {str(h): 1.0 for h in range(8, 20)},
                             "precipitation_probability": {str(h): 90 for h in range(8, 22)}}),
    "tomorrow_rain": payload(daily={"precipitation_sum": [0, 60]}),
    "cold_3": payload({"temperature_2m": 3}),
    "kids_rain": payload({"precipitation": 2}),
    "malformed": {"unexpected": "payload"},
}
# ---------------------------------------------------------------------------
# User-suite fixtures (prefix u_): payloads for the REAL SOPs in sops/sops.yaml.
# Kept separate from payload()/FILES so the fixture-suite files above stay byte-identical.
# upayload() carries every `current` field the real SOPs read (sane, non-triggering defaults),
# plus hourly snowfall/apparent_temperature and daily temperature_2m_min, so a case only has to
# override the one or two fields its target SOP checks.
# ---------------------------------------------------------------------------
def upayload(current=None, hourly=None, daily=None):
    cur = {"time": "2026-09-04T13:30", "interval": 900,
           "temperature_2m": 22, "apparent_temperature": 22, "wet_bulb_temperature_2m": 16,
           "surface_temperature": 24, "wind_speed_10m": 6, "wind_gusts_10m": 10,
           "precipitation": 0, "weather_code": 1, "cloud_cover": 40, "visibility": 20000,
           "snow_depth": 0, "is_day": 1, "relative_humidity_2m": 45}
    cur.update(current or {})
    hr = {"snowfall": [0.0] * 48, "apparent_temperature": [22] * 48}
    for name, spec in (hourly or {}).items():
        if isinstance(spec, dict):
            hr.setdefault(name, [0.0] * 48)
            for h, v in spec.items():
                hr[name][int(h)] = v
        else:
            hr[name] = [spec] * 48
    dl = {"temperature_2m_min": [15, 15], "precipitation_sum": [0, 0]}
    dl.update(daily or {})
    return {"latitude": 23.25, "longitude": 77.4, "utc_offset_seconds": 19800, "timezone": "Asia/Kolkata",
            "current": cur, "hourly": {"time": HOURS, **hr}, "daily": {"time": ["2026-09-04", "2026-09-05"], **dl}}


UFILES = {
    "u_calm": upayload(),                                                            # nothing triggers -> no_guidance
    "u_fog": upayload({"weather_code": 45, "visibility": 400}),                       # WA-01
    "u_snowsquall": upayload({"weather_code": 73, "visibility": 600, "wind_gusts_10m": 50}),  # WA-02
    "u_icing": upayload({"weather_code": 66, "temperature_2m": -2}),                  # WA-03
    "u_hail": upayload({"weather_code": 96}),                                         # WA-04 (gust/precip low -> WA-20 FALSE)
    "u_treksnow": upayload(hourly={"snowfall": {h: 0.6 for h in range(8, 18)}}),      # WA-05 (today-window sum = 6 cm)
    "u_snowdepth": upayload({"snow_depth": 0.3}),                                     # WA-06
    "u_coldcamp": upayload(hourly={"apparent_temperature": {h: 2 for h in range(18, 24)}}),  # WA-07 (overnight min = 2)
    "u_frost": upayload(daily={"temperature_2m_min": [1, 5]}),                        # WA-08
    "u_heatwork": upayload({"apparent_temperature": 32, "wet_bulb_temperature_2m": 29}),     # WA-09 + WA-10 (multi-match)
    "u_hotpaw": upayload({"surface_temperature": 50}),                               # WA-11
    "u_petsnow": upayload({"snow_depth": 0.1, "weather_code": 73}),                   # WA-12
    "u_coldppl": upayload({"apparent_temperature": 4}),                              # WA-13 + WA-14
    "u_wetelec": upayload({"precipitation": 1, "weather_code": 61}),                  # WA-15 (rain, not thunder)
    "u_elec_null": upayload({"precipitation": None, "weather_code": 61}),             # WA-15 UNKNOWN -> data_unavailable
    "u_gust45": upayload({"wind_gusts_10m": 45}),                                     # WA-16 boundary (inclusive)
    "u_gust44": upayload({"wind_gusts_10m": 44.9}),                                   # WA-16 boundary (just below)
    "u_runoff": upayload(hourly={"precipitation": {h: 1.5 for h in range(8, 18)}}),   # WA-17 (today-window rain = 15 mm)
    "u_clearnight": upayload({"is_day": 0, "cloud_cover": 10, "visibility": 20000, "precipitation": 0}),  # WA-18
    "u_photo": upayload({"visibility": 20000, "cloud_cover": 50, "precipitation": 0, "wind_speed_10m": 10}),  # WA-19
    "u_storm": upayload({"weather_code": 95, "wind_gusts_10m": 50, "precipitation": 6}),  # WA-20 override
}

for name, data in {**FILES, **UFILES}.items():
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=1) + "\n")
print(f"wrote {len(FILES) + len(UFILES)} files to {OUT}")
