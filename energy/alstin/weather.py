"""Open-Meteo weather client (free, no API key).

Used by the dashboard to show current conditions and a short solar-relevant
forecast (cloud cover + shortwave radiation drive PV output).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import requests

BASE = "https://api.open-meteo.com/v1/forecast"


def forecast(lat: float, lon: float, hours: int = 24, timeout: int = 20) -> dict:
    """Return current weather + an hourly forecast slice for the next `hours`.

    Shape:
      {
        "current": {"temp_c", "cloud_cover_pct", "is_day", "weather_code", "time"},
        "hourly":  [{"time", "temp_c", "cloud_cover_pct", "shortwave_wm2",
                     "precip_prob_pct"}, ...],
        "today_solar_mj_m2": float | None,   # daily shortwave radiation sum
      }
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,cloud_cover,is_day,weather_code",
        "hourly": "temperature_2m,cloud_cover,shortwave_radiation,precipitation_probability",
        "daily": "shortwave_radiation_sum",
        "timezone": "Europe/London",
        "forecast_days": 2,
    }
    r = requests.get(BASE, params=params, timeout=timeout)
    r.raise_for_status()
    d = r.json()

    cur = d.get("current", {})
    out_current = {
        "temp_c": cur.get("temperature_2m"),
        "cloud_cover_pct": cur.get("cloud_cover"),
        "is_day": bool(cur.get("is_day")),
        "weather_code": cur.get("weather_code"),
        "time": cur.get("time"),
    }

    h = d.get("hourly", {})
    times = h.get("time", []) or []
    now = dt.datetime.now()
    hourly = []
    for i, t in enumerate(times):
        try:
            tt = dt.datetime.fromisoformat(t)
        except ValueError:
            continue
        if tt < now - dt.timedelta(hours=1):
            continue
        hourly.append({
            "time": t,
            "temp_c": _idx(h.get("temperature_2m"), i),
            "cloud_cover_pct": _idx(h.get("cloud_cover"), i),
            "shortwave_wm2": _idx(h.get("shortwave_radiation"), i),
            "precip_prob_pct": _idx(h.get("precipitation_probability"), i),
        })
        if len(hourly) >= hours:
            break

    daily = d.get("daily", {})
    solar_sum = daily.get("shortwave_radiation_sum") or []
    today_solar = solar_sum[0] if solar_sum else None

    return {"current": out_current, "hourly": hourly, "today_solar_mj_m2": today_solar}


def _idx(seq: Optional[list], i: int):
    if seq is None or i >= len(seq):
        return None
    return seq[i]


# Minimal WMO weather-code -> short label/emoji for the UI.
WMO = {
    0: ("Clear", "☀️"), 1: ("Mainly clear", "\U0001f324️"),
    2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "\U0001f32b️"), 48: ("Rime fog", "\U0001f32b️"),
    51: ("Light drizzle", "\U0001f327️"), 53: ("Drizzle", "\U0001f327️"),
    55: ("Heavy drizzle", "\U0001f327️"), 61: ("Light rain", "\U0001f327️"),
    63: ("Rain", "\U0001f327️"), 65: ("Heavy rain", "\U0001f327️"),
    71: ("Light snow", "\U0001f328️"), 73: ("Snow", "\U0001f328️"),
    75: ("Heavy snow", "\U0001f328️"), 80: ("Showers", "\U0001f326️"),
    81: ("Showers", "\U0001f326️"), 82: ("Heavy showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm", "⛈️"),
    99: ("Thunderstorm", "⛈️"),
}


def describe(code) -> dict:
    label, emoji = WMO.get(code, ("—", ""))
    return {"label": label, "emoji": emoji}
