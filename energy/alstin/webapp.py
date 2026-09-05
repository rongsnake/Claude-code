"""energy.gcburton.org - Alstin Lodge energy dashboard.

Served behind Caddy basic_auth (user 'gareth') via the cloudflared tunnel, so
the app itself trusts the proxy and does no auth of its own. Exposes live
Powerwall inputs, a weather forecast, LIVE battery controls, and the
current-plan-vs-Agile-arbitrage tally (see market.py).
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import market
import weather

BASE = Path(__file__).resolve().parent
CFG = yaml.safe_load((BASE / "config.yaml").read_text()) or {}
DB = str(BASE / (CFG.get("storage", {}).get("db_path", "energy.db")))
TZ = CFG.get("powerwall", {}).get("timezone", "Europe/London")

app = FastAPI(title="Alstin Lodge Energy", docs_url=None, redoc_url=None)

_fleet = None


def fleet():
    """Lazily build a FleetAPI client (handles its own token refresh)."""
    global _fleet
    if _fleet is None:
        from pypowerwall.fleetapi.fleetapi import FleetAPI
        _fleet = FleetAPI(configfile=str(BASE / ".pypowerwall.fleetapi"))
    return _fleet


# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE / "web" / "index.html").read_text()


@app.get("/api/live")
def live():
    try:
        f = fleet()
        s = f.get_live_status(force=True) or {}
        info_mode = f.get_operating_mode()
        reserve = f.get_battery_reserve()
        grid_charging = f.get_grid_charging()
        return {
            "soc_pct": s.get("percentage_charged"),
            "solar_w": s.get("solar_power"),
            "load_w": s.get("load_power"),
            "grid_w": s.get("grid_power"),
            "battery_w": s.get("battery_power"),
            "grid_status": s.get("grid_status"),
            "island_status": s.get("island_status"),
            "storm_mode": s.get("storm_mode_active"),
            "timestamp": s.get("timestamp"),
            "mode": info_mode,
            "reserve_pct": reserve,
            "grid_charging": grid_charging,
        }
    except Exception as e:  # surface upstream errors to the UI
        raise HTTPException(502, f"FleetAPI live read failed: {e}")


@app.get("/api/battery/history")
def battery_history():
    """Powerwall state-of-charge over today (Tesla calendar history, ~15-min slots).

    `soe` is the battery's state of energy in %, the same quantity as the live
    State-of-charge card. Tesla serves midnight-to-now for the local day.
    """
    try:
        f = fleet()
        h = f.get_calendar_history(kind="soe", duration="day", time_zone=TZ) or {}
        series = h.get("time_series", []) if isinstance(h, dict) else []
        points = [{"t": s.get("timestamp"), "soe": s.get("soe")}
                  for s in series if s.get("timestamp") and s.get("soe") is not None]
        return {"points": points, "reserve_pct": f.get_battery_reserve()}
    except Exception as e:
        raise HTTPException(502, f"battery history failed: {e}")


@app.get("/api/settings")
def get_settings():
    try:
        f = fleet()
        return {
            "mode": f.get_operating_mode(force=True),
            "reserve_pct": f.get_battery_reserve(force=True),
            "grid_charging": f.get_grid_charging(force=True),
        }
    except Exception as e:
        raise HTTPException(502, f"FleetAPI settings read failed: {e}")


class Settings(BaseModel):
    mode: str | None = None            # self_consumption | autonomous | backup
    reserve_pct: int | None = None     # 0-100
    grid_charging: bool | None = None


@app.post("/api/settings")
def set_settings(body: Settings):
    """LIVE control: writes straight to the Powerwall via Tesla Fleet API."""
    f = fleet()
    applied = {}
    errors = {}
    try:
        if body.mode is not None:
            if body.mode not in ("self_consumption", "autonomous", "backup"):
                raise HTTPException(400, f"invalid mode {body.mode!r}")
            r = f.set_operating_mode(body.mode)
            applied["mode"] = body.mode if r is not False else None
            if r is False:
                errors["mode"] = "rejected by Fleet API"
        if body.reserve_pct is not None:
            rp = int(body.reserve_pct)
            if not 0 <= rp <= 100:
                raise HTTPException(400, "reserve_pct must be 0-100")
            r = f.set_battery_reserve(rp)
            applied["reserve_pct"] = rp if r is not False else None
            if r is False:
                errors["reserve_pct"] = "rejected by Fleet API"
        if body.grid_charging is not None:
            r = f.set_grid_charging("on" if body.grid_charging else "off")
            applied["grid_charging"] = body.grid_charging if r is not False else None
            if r is False:
                errors["grid_charging"] = "rejected by Fleet API"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"FleetAPI write failed: {e}")
    # Read back the confirmed state.
    confirmed = get_settings()
    return {"applied": applied, "errors": errors, "confirmed": confirmed}


_solar_cache: dict = {"at": None, "data": None}


@app.get("/api/solar")
def get_solar():
    """Tonight's solar-aware charge target (the SolarEdge<->Tesla bridge)."""
    import solar

    now = dt.datetime.now()
    if _solar_cache["at"] and (now - _solar_cache["at"]) < dt.timedelta(minutes=30):
        return _solar_cache["data"]
    try:
        data = solar.plan(fleet(), CFG, now=now)
    except Exception as e:
        raise HTTPException(502, f"solar plan failed: {e}")
    _solar_cache.update(at=now, data=data)
    return data


_outlook_cache: dict = {"at": None, "data": None}


@app.get("/api/solar/outlook")
def get_solar_outlook():
    """Multi-day solar prospect: cloud, radiation, predicted harvest, accuracy."""
    import solar

    now = dt.datetime.now()
    if _outlook_cache["at"] and (now - _outlook_cache["at"]) < dt.timedelta(minutes=30):
        return _outlook_cache["data"]
    try:
        data = solar.outlook(fleet(), CFG, DB, now=now)
    except Exception as e:
        raise HTTPException(502, f"solar outlook failed: {e}")
    for d in data["days"]:  # decorate with the UI's weather labels/emoji
        d["desc"] = weather.describe(d.get("weather_code"))
    _outlook_cache.update(at=now, data=data)
    return data


@app.get("/api/solaredge")
def get_solaredge():
    """Inverter-side cross-check; 404 until SOLAREDGE_API_KEY/_SITE_ID exist."""
    import solaredge

    if not solaredge.available():
        raise HTTPException(404, "SolarEdge API key not configured (see solaredge.py)")
    try:
        return solaredge.overview()
    except Exception as e:
        raise HTTPException(502, f"SolarEdge API failed: {e}")


_gas_cache: dict = {"at": None, "data": None}


@app.get("/api/gas")
def get_gas(days: int = 14):
    """Daily gas usage (kWh). 404 until OCTOPUS_API_KEY + a gas meter exist."""
    import gas

    if not gas.available():
        raise HTTPException(404, "gas not configured (set OCTOPUS_API_KEY — see gas.py)")
    now = dt.datetime.now(dt.timezone.utc)
    if _gas_cache["at"] and (now - _gas_cache["at"]) < dt.timedelta(hours=6):
        return _gas_cache["data"]
    try:
        data = gas.daily_usage(CFG, days=days, now=now)
    except Exception as e:
        raise HTTPException(502, f"gas fetch failed: {e}")
    _gas_cache.update(at=now, data=data)
    return data


@app.get("/api/weather")
def get_weather():
    w = CFG.get("weather", {})
    try:
        data = weather.forecast(w.get("latitude", 51.06), w.get("longitude", -1.31))
        data["label"] = w.get("label", "")
        cur = data["current"]
        cur["desc"] = weather.describe(cur.get("weather_code"))
        return data
    except Exception as e:
        raise HTTPException(502, f"weather fetch failed: {e}")


@app.get("/api/prices")
def prices():
    """Today's import/export prices: current plan + Agile, for the chart."""
    mk = CFG.get("market", {})
    now = dt.datetime.now(dt.timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(hours=48)

    def series(tariff):
        try:
            rs = market.fetch_rates(tariff, start, end)
        except Exception:
            return []
        # A flat/open-ended tariff (e.g. fixed Outgoing) returns one rate; draw it
        # as a horizontal reference line across the visible window.
        if len(rs) == 1 and rs[0].valid_to is None:
            p = rs[0].value_inc_vat
            return [{"t": start.isoformat(), "p": p}, {"t": end.isoformat(), "p": p}]
        return [{"t": r.valid_from.isoformat(), "p": r.value_inc_vat} for r in rs]

    return {
        "current_import": series(mk["current_import_tariff"]),
        "current_export": series(mk["current_export_tariff"]),
        "agile_import": series(mk["agile_import_tariff"]),
        "agile_export": series(mk["agile_export_tariff"]),
        "tariffs": mk,
    }


@app.get("/api/tally")
def tally(days: int = 14, refresh: bool = False):
    """Daily current-vs-Agile tally + cumulative delta.

    Completed days are cached in `market_tally`; today is always recomputed
    (it is partial). `refresh=true` recomputes every day in the window.
    """
    f = fleet()
    sid = f.site_id
    today = dt.datetime.now().date()
    computed_at = dt.datetime.now(dt.timezone.utc).isoformat()
    errors = []
    for i in range(days, -1, -1):
        day = today - dt.timedelta(days=i)
        ds = day.isoformat()
        is_today = (day == today)
        if not is_today and not refresh and market.has_day(DB, ds):
            continue
        try:
            row = market.compute_day(f, sid, day, CFG)
            if row:
                market.save_day(DB, row, computed_at)
        except Exception as e:
            errors.append({"date": ds, "error": str(e)})

    rows = market.load_days(DB, limit=max(days + 1, 60))
    return JSONResponse({
        "rows": rows,
        "cumulative": market.cumulative(rows),
        "errors": errors,
        "method": ("Baseline = your actual grid flows on Go + Outgoing. "
                   "Counterfactual = battery actively arbitraging on Agile "
                   "import + Agile Outgoing with the same solar & load. "
                   "Unit-rate energy cost only; standing charges not modelled."),
    })


@app.get("/api/health")
def health():
    return {"ok": True, "site_id": getattr(fleet(), "site_id", None)}
