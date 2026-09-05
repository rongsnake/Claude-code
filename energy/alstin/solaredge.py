"""Optional direct SolarEdge Monitoring API client.

NOT required for the solar-aware charge target - solar.py uses Tesla's own
meter of the SolarEdge AC output. This client exists for cross-checks (is the
Tesla solar CT reading what the inverter actually produced?) and inverter
health, once an API key exists.

To enable:
  1. Log in at https://monitoring.solaredge.com (site owner/admin account).
  2. Admin -> Site Access -> API Access: accept the T&Cs, generate a key,
     note the numeric Site ID shown on the same page.
  3. Add to .env (mode 600, gitignored):
       SOLAREDGE_API_KEY=...
       SOLAREDGE_SITE_ID=...

Free-tier rate limit is 300 requests/day per site - poll gently.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Optional

import requests

BASE = "https://monitoringapi.solaredge.com"


def _creds() -> tuple[Optional[str], Optional[str]]:
    return os.environ.get("SOLAREDGE_API_KEY"), os.environ.get("SOLAREDGE_SITE_ID")


def available() -> bool:
    key, site = _creds()
    return bool(key and site)


def overview(timeout: int = 20) -> dict:
    """Current power + lifetime/today energy straight from the inverter."""
    key, site = _creds()
    if not (key and site):
        raise RuntimeError("SOLAREDGE_API_KEY / SOLAREDGE_SITE_ID not set in env")
    r = requests.get(f"{BASE}/site/{site}/overview",
                     params={"api_key": key}, timeout=timeout)
    r.raise_for_status()
    o = r.json().get("overview", {})
    return {
        "current_power_w": (o.get("currentPower") or {}).get("power"),
        "today_kwh": ((o.get("lastDayData") or {}).get("energy") or 0) / 1000.0,
        "month_kwh": ((o.get("lastMonthData") or {}).get("energy") or 0) / 1000.0,
        "lifetime_kwh": ((o.get("lifeTimeData") or {}).get("energy") or 0) / 1000.0,
        "last_update": o.get("lastUpdateTime"),
    }


def energy_by_day(days: int = 14, timeout: int = 20) -> dict[str, float]:
    """Daily production kWh for the last `days` days, keyed by ISO date."""
    key, site = _creds()
    if not (key and site):
        raise RuntimeError("SOLAREDGE_API_KEY / SOLAREDGE_SITE_ID not set in env")
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    r = requests.get(f"{BASE}/site/{site}/energy", params={
        "api_key": key, "timeUnit": "DAY",
        "startDate": start.isoformat(), "endDate": end.isoformat(),
    }, timeout=timeout)
    r.raise_for_status()
    vals = (r.json().get("energy") or {}).get("values") or []
    return {v["date"][:10]: (v.get("value") or 0) / 1000.0 for v in vals}
