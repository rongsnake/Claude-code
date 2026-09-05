"""Gas usage via the Octopus REST API — dormant until a key is configured.

Mirrors the SolarEdge cross-check (solaredge.py): the dashboard endpoint 404s
until both an Octopus API key and a gas meter point exist, so nothing breaks
while it is unconfigured.

To enable:
  1. Get your Octopus API key: octopus.energy dashboard -> Personal details ->
     "API access" (the key starting `sk_live_...`).
  2. Add it to .env on the Pi (mode 600, gitignored — never paste keys in chat):
       (umask 177 && echo 'OCTOPUS_API_KEY=sk_live_...' >> .env)
  3. The gas MPRN + meter serial are discovered automatically from your account
     (config.yaml `octopus.account_number`). To pin them, set
     `octopus.gas_mprn` / `octopus.gas_serial` in config.yaml.
  4. Restart energy-web. The Gas usage card lights up.

Units: Octopus reports gas in the meter's native unit. SMETS2 meters usually
report kWh directly; older/SMETS1 meters report m^3, which we convert with
`octopus.gas_kwh_per_m3` (UK average ~11.1). Set `octopus.gas_units` to
'kwh' or 'm3' to match your meter, or leave 'auto' to infer from magnitude.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Optional

import octopus

# A daily m^3 reading is single/low-double digits; a daily kWh reading is ~10x
# larger. If units are 'auto', a mean daily value above this is treated as kWh.
_AUTO_KWH_THRESHOLD = 40.0


def available() -> bool:
    return bool(os.environ.get("OCTOPUS_API_KEY"))


def _client() -> octopus.OctopusClient:
    key = os.environ.get("OCTOPUS_API_KEY")
    if not key:
        raise RuntimeError("OCTOPUS_API_KEY not set in env")
    return octopus.OctopusClient(key)


def _meter_point(client: octopus.OctopusClient, cfg: dict
                 ) -> tuple[str, str, Optional[str]]:
    """Resolve (mprn, serial, tariff) from config overrides or the account."""
    oc = cfg.get("octopus", {}) or {}
    mprn = str(oc.get("gas_mprn") or "").strip()
    serial = str(oc.get("gas_serial") or "").strip()
    if mprn and serial:
        return mprn, serial, oc.get("gas_tariff_code")
    points = client.account_gas_meter_points(oc.get("account_number", ""))
    if not points:
        raise RuntimeError("no gas meter point on this Octopus account")
    p = points[0]
    return (mprn or p.mpan, serial or p.serial, oc.get("gas_tariff_code") or p.tariff_code)


def to_kwh(values: list[float], units: str, kwh_per_m3: float) -> tuple[list[float], str]:
    """Convert native consumption to kWh. Pure: returns (kwh_values, source_unit)."""
    if not values:
        return [], units
    u = (units or "auto").lower()
    if u == "auto":
        mean = sum(values) / len(values)
        u = "kwh" if mean >= _AUTO_KWH_THRESHOLD else "m3"
    if u == "m3":
        return [round(v * kwh_per_m3, 2) for v in values], "m3"
    return [round(v, 2) for v in values], "kwh"


def daily_usage(cfg: dict, days: int = 14, now: Optional[dt.datetime] = None) -> dict:
    """Last `days` days of daily gas usage in kWh. Raises if unconfigured/empty."""
    oc = cfg.get("octopus", {}) or {}
    client = _client()
    mprn, serial, _tariff = _meter_point(client, cfg)

    now = now or dt.datetime.now(dt.timezone.utc)
    period_to = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_from = period_to - dt.timedelta(days=days)
    rows = client.gas_consumption(mprn, serial, period_from, period_to,
                                  group_by="day")
    # Octopus returns newest-first; sort ascending by interval start.
    rows = sorted(rows, key=lambda r: r.get("interval_start", ""))
    dates = [r.get("interval_start", "")[:10] for r in rows]
    raw = [float(r.get("consumption") or 0) for r in rows]

    kwh, src = to_kwh(raw, oc.get("gas_units", "auto"),
                      float(oc.get("gas_kwh_per_m3", 11.1)))
    points = [{"date": d, "kwh": k} for d, k in zip(dates, kwh)]
    total = round(sum(kwh), 1)
    return {
        "points": points,
        "total_kwh": total,
        "avg_kwh": round(total / len(points), 1) if points else 0.0,
        "source_unit": src,
        "mprn": mprn,
    }
