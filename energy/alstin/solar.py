"""SolarEdge <-> Tesla bridge: solar-aware overnight charge target.

Why: the Powerwall was charging to 100% in the cheap Go window every night,
so on sunny days the SolarEdge excess had nowhere to go and exported at the
Outgoing rate (12p) while the house later imported at the Go day rate (31p).
The fix is to leave exactly enough headroom overnight for tomorrow's PV.

The bridge has three parts:
  1. Open-Meteo daily shortwave radiation (past days + 2-day forecast, no key).
  2. Tesla's own meter of the SolarEdge AC output (daily kWh from the Fleet
     API calendar history) - so no SolarEdge credentials are required.
  3. A self-calibrating yield factor k (kWh per MJ/m^2) fitted on the days
     where both are known, used to turn tomorrow's radiation into kWh.

Pure maths lives in `calibrate()` and `charge_target_pct()` (unit-tested);
network access is isolated in the two fetchers and `plan()`.
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections import defaultdict
from statistics import median
from typing import Optional

import requests

log = logging.getLogger("solar")

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"

# Fallback yield before any calibration data exists. June calibration at
# Alstin Lodge gives ~0.9 kWh of AC output per MJ/m^2 of daily radiation.
DEFAULT_YIELD_KWH_PER_MJ = 0.9


# ---- fetchers --------------------------------------------------------------

def radiation_by_day(lat: float, lon: float, past_days: int = 14,
                     timeout: int = 20) -> dict[dt.date, float]:
    """Daily shortwave radiation sum (MJ/m^2): past `past_days` + 2-day forecast."""
    r = requests.get(OPEN_METEO, params={
        "latitude": lat,
        "longitude": lon,
        "daily": "shortwave_radiation_sum",
        "past_days": past_days,
        "forecast_days": 2,
        "timezone": "Europe/London",
    }, timeout=timeout)
    r.raise_for_status()
    d = r.json().get("daily", {})
    out: dict[dt.date, float] = {}
    for day, mj in zip(d.get("time", []), d.get("shortwave_radiation_sum", [])):
        if mj is not None:
            out[dt.date.fromisoformat(day)] = float(mj)
    return out


def tesla_solar_by_day(fleet, time_zone: str = "Europe/London") -> dict[dt.date, float]:
    """Daily PV kWh as metered by the Tesla gateway CT on the SolarEdge feed.

    Aggregates the Fleet API energy calendar history (sub-day slots) per day.
    Asks for a month but tolerates whatever window Tesla returns.
    """
    h = fleet.get_calendar_history(kind="energy", duration="month",
                                   time_zone=time_zone) or {}
    series = h.get("time_series", []) if isinstance(h, dict) else []
    acc: dict[dt.date, float] = defaultdict(float)
    for slot in series:
        ts = slot.get("timestamp", "")
        try:
            day = dt.date.fromisoformat(ts[:10])
        except ValueError:
            continue
        acc[day] += float(slot.get("solar_energy_exported", 0) or 0) / 1000.0
    return dict(acc)


# ---- pure maths ------------------------------------------------------------

def calibrate(radiation: dict[dt.date, float], solar_kwh: dict[dt.date, float],
              today: dt.date, min_radiation_mj: float = 2.0,
              min_solar_kwh: float = 0.5) -> tuple[Optional[float], int]:
    """Median yield k = kWh per MJ/m^2 over fully-elapsed days both sides know.

    Returns (k, days_used); k is None when fewer than 2 usable days overlap
    (caller falls back to DEFAULT_YIELD_KWH_PER_MJ). Today is excluded - its
    solar total is still accumulating and would bias k low.
    """
    ratios = []
    for day, mj in radiation.items():
        if day >= today or mj < min_radiation_mj:
            continue
        kwh = solar_kwh.get(day)
        if kwh is None or kwh < min_solar_kwh:
            continue
        ratios.append(kwh / mj)
    if len(ratios) < 2:
        return None, len(ratios)
    return median(ratios), len(ratios)


def next_daylight_date(now: dt.datetime) -> dt.date:
    """The daylight period the overnight charge must leave headroom for.

    Inside the Go window (00:30-05:30) and any time before noon that is
    today's date; after noon the next sunrise is tomorrow.
    """
    return now.date() if now.hour < 12 else now.date() + dt.timedelta(days=1)


def charge_target_pct(pv_kwh: float, day_load_kwh: float, capacity_kwh: float,
                      charge_efficiency: float = 0.95, min_pct: float = 35.0,
                      max_pct: float = 100.0) -> float:
    """Overnight SoC target leaving headroom for tomorrow's PV surplus.

    Surplus = forecast PV minus the load the house consumes while the sun is
    up (that part of PV never reaches the battery). On dull days the surplus
    is ~0 and the target stays at max (charge fully on cheap rate, as today).
    """
    surplus_kwh = max(0.0, pv_kwh - day_load_kwh) * charge_efficiency
    headroom_pct = 100.0 * surplus_kwh / capacity_kwh
    return round(min(max_pct, max(min_pct, 100.0 - headroom_pct)))


# ---- orchestration ---------------------------------------------------------

def plan(fleet, cfg: dict, now: Optional[dt.datetime] = None) -> dict:
    """Compute tonight's solar-aware charge target. Raises on network failure.

    cfg keys (all under config.yaml `solar:`, with `weather:` for coords and
    `battery:` for capacity/efficiency):
      enabled, day_load_kwh, min_charge_target_pct, calibration_days
    """
    now = now or dt.datetime.now()
    wx = cfg.get("weather", {}) or {}
    sol = cfg.get("solar", {}) or {}
    bat = cfg.get("battery", {}) or {}

    rad = radiation_by_day(wx.get("latitude", 51.06), wx.get("longitude", -1.31),
                           past_days=int(sol.get("calibration_days", 14)))
    actual = tesla_solar_by_day(fleet)

    k, days_used = calibrate(rad, actual, today=now.date())
    k_used = k if k is not None else float(
        sol.get("default_yield_kwh_per_mj", DEFAULT_YIELD_KWH_PER_MJ))

    target_day = next_daylight_date(now)
    rad_mj = rad.get(target_day)
    if rad_mj is None:
        raise ValueError(f"no radiation forecast for {target_day}")
    pv_kwh = k_used * rad_mj

    target = charge_target_pct(
        pv_kwh=pv_kwh,
        day_load_kwh=float(sol.get("day_load_kwh", 9.0)),
        capacity_kwh=float(bat.get("capacity_kwh", 13.5)),
        charge_efficiency=float(bat.get("charge_efficiency", 0.95)),
        min_pct=float(sol.get("min_charge_target_pct", 35.0)),
    )
    return {
        "charge_target_pct": target,
        "pv_forecast_kwh": round(pv_kwh, 1),
        "for_date": target_day.isoformat(),
        "radiation_mj_m2": rad_mj,
        "yield_kwh_per_mj": round(k_used, 3),
        "calibrated": k is not None,
        "calibration_days": days_used,
    }


# ---- multi-day outlook ------------------------------------------------------
# "Prospecting forward": Open-Meteo daily forecast out to `outlook_days`
# (cloud cover + radiation), harvest predicted with the same self-calibrated
# yield k as plan(). Every day's predictions are snapshotted into SQLite so
# the dashboard can grow a forecast-vs-actual track record by horizon.

def daily_forecast(lat: float, lon: float, past_days: int = 14,
                   forecast_days: int = 15, timeout: int = 20
                   ) -> dict[dt.date, dict]:
    """Per-day radiation (MJ/m^2), mean cloud (%) and WMO code.

    Covers `past_days` back (for calibration) and `forecast_days` forward
    (today inclusive). Open-Meteo serves at most 16 forecast days and pads
    unavailable tail days with nulls - kept as None (placeholders).
    """
    r = requests.get(OPEN_METEO, params={
        "latitude": lat,
        "longitude": lon,
        "daily": "shortwave_radiation_sum,cloud_cover_mean,weather_code",
        "past_days": past_days,
        "forecast_days": min(int(forecast_days), 16),
        "timezone": "Europe/London",
    }, timeout=timeout)
    r.raise_for_status()
    d = r.json().get("daily", {})
    out: dict[dt.date, dict] = {}
    rads = d.get("shortwave_radiation_sum") or []
    clouds = d.get("cloud_cover_mean") or []
    codes = d.get("weather_code") or []
    for i, day in enumerate(d.get("time", []) or []):
        try:
            date = dt.date.fromisoformat(day)
        except ValueError:
            continue
        rad = rads[i] if i < len(rads) else None
        out[date] = {
            "radiation": float(rad) if rad is not None else None,
            "cloud": clouds[i] if i < len(clouds) else None,
            "code": codes[i] if i < len(codes) else None,
        }
    return out


def build_outlook(daily: dict[dt.date, dict], k_used: float, today: dt.date,
                  horizon_days: int = 14) -> list[dict]:
    """Pure: one entry per day today..today+horizon_days.

    pred_kwh = k * radiation; days the feed cannot see yet (or missing
    entirely) become placeholders with pred_kwh None.
    """
    days = []
    for n in range(horizon_days + 1):
        date = today + dt.timedelta(days=n)
        e = daily.get(date) or {}
        rad = e.get("radiation")
        days.append({
            "date": date.isoformat(),
            "horizon_days": n,
            "radiation_mj_m2": rad,
            "cloud_cover_pct": e.get("cloud"),
            "weather_code": e.get("code"),
            "pred_kwh": round(k_used * rad, 1) if rad is not None else None,
            "placeholder": rad is None,
        })
    return days


_LOG_DDL = """
CREATE TABLE IF NOT EXISTS solar_forecast_log (
    forecast_date TEXT NOT NULL,
    target_date   TEXT NOT NULL,
    horizon_days  INTEGER NOT NULL,
    radiation_mj  REAL,
    cloud_pct     REAL,
    weather_code  INTEGER,
    pred_kwh      REAL,
    yield_kwh_per_mj REAL,
    calibrated    INTEGER,
    created_at    TEXT,
    PRIMARY KEY (forecast_date, target_date)
)
"""


def log_outlook(db_path: str, days: list[dict], k_used: float,
                calibrated: bool, forecast_date: dt.date) -> int:
    """Snapshot today's predictions; first snapshot of the day wins.

    INSERT OR IGNORE on (forecast_date, target_date) means reloading the
    dashboard later the same day does not overwrite the morning's view.
    Returns the number of newly-inserted rows.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_LOG_DDL)
        now_iso = dt.datetime.now().isoformat(timespec="seconds")
        n = 0
        for e in days:
            cur = conn.execute(
                "INSERT OR IGNORE INTO solar_forecast_log VALUES "
                "(?,?,?,?,?,?,?,?,?,?)",
                (forecast_date.isoformat(), e["date"], e["horizon_days"],
                 e["radiation_mj_m2"], e["cloud_cover_pct"], e["weather_code"],
                 e["pred_kwh"], round(k_used, 4), int(calibrated), now_iso))
            n += cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()


def tally_solar_by_day(db_path: str) -> dict[dt.date, float]:
    """Actual daily PV kWh already cached by the market tally (long history)."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT date, solar_kwh FROM market_tally").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    out = {}
    for date, kwh in rows:
        try:
            if kwh is not None:
                out[dt.date.fromisoformat(date)] = float(kwh)
        except ValueError:
            continue
    return out


ACCURACY_BUCKETS = ((0, 1, "0-1d"), (2, 3, "2-3d"), (4, 7, "4-7d"), (8, 14, "8-14d"))


def forecast_accuracy(db_path: str, actual_by_day: dict[dt.date, float],
                      today: dt.date, min_matched: int = 7) -> dict:
    """Pure-ish: logged predictions vs actual harvest, summarised by horizon.

    A prediction matches when its target day has fully elapsed and an actual
    PV total >= 0.05 kWh exists. Errors are |pred-actual|/actual (median APE
    per horizon bucket). `available` flips on at `min_matched` matches -
    until then the dashboard shows a placeholder with progress.
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(_LOG_DDL)
            rows = conn.execute(
                "SELECT target_date, horizon_days, pred_kwh, forecast_date "
                "FROM solar_forecast_log WHERE pred_kwh IS NOT NULL").fetchall()
            first = conn.execute(
                "SELECT MIN(forecast_date) FROM solar_forecast_log").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        rows, first = [], None

    by_bucket: dict[str, list] = defaultdict(list)
    matched = 0
    for target, horizon, pred, _fc in rows:
        try:
            tdate = dt.date.fromisoformat(target)
        except ValueError:
            continue
        if tdate >= today:
            continue
        actual = actual_by_day.get(tdate)
        if actual is None or actual < 0.05:
            continue
        matched += 1
        ape = 100.0 * abs(pred - actual) / max(actual, 0.1)
        for lo, hi, name in ACCURACY_BUCKETS:
            if lo <= horizon <= hi:
                by_bucket[name].append(ape)
                break

    return {
        "available": matched >= min_matched,
        "matched": matched,
        "min_required": min_matched,
        "since": first,
        "by_horizon": [
            {"bucket": name, "n": len(by_bucket[name]),
             "median_ape_pct": round(median(by_bucket[name]), 1)}
            for _lo, _hi, name in ACCURACY_BUCKETS if by_bucket[name]
        ],
    }


def outlook(fleet, cfg: dict, db_path: str,
            now: Optional[dt.datetime] = None) -> dict:
    """The dashboard's multi-day solar prospect. Raises on network failure.

    Same calibration as plan(); each call also snapshots today's predictions
    into `solar_forecast_log` (idempotent per day) so accuracy history accrues.
    """
    now = now or dt.datetime.now()
    today = now.date()
    wx = cfg.get("weather", {}) or {}
    sol = cfg.get("solar", {}) or {}

    horizon = int(sol.get("outlook_days", 14))
    daily = daily_forecast(
        wx.get("latitude", 51.06), wx.get("longitude", -1.31),
        past_days=int(sol.get("calibration_days", 14)),
        forecast_days=horizon + 1)

    rad = {d: e["radiation"] for d, e in daily.items()
           if e["radiation"] is not None}
    actual = tally_solar_by_day(db_path)
    actual.update(tesla_solar_by_day(fleet))  # Tesla wins where both exist

    k, days_used = calibrate(rad, actual, today=today)
    k_used = k if k is not None else float(
        sol.get("default_yield_kwh_per_mj", DEFAULT_YIELD_KWH_PER_MJ))

    days = build_outlook(daily, k_used, today, horizon_days=horizon)
    try:
        log_outlook(db_path, days, k_used, k is not None, today)
    except sqlite3.Error as e:  # logging must never break the outlook
        log.warning("forecast log write failed: %s", e)

    return {
        "days": days,
        "yield_kwh_per_mj": round(k_used, 3),
        "calibrated": k is not None,
        "calibration_days": days_used,
        "accuracy": forecast_accuracy(
            db_path, actual, today,
            min_matched=int(sol.get("accuracy_min_days", 7))),
        "generated_at": now.isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    # Daily cron entry point: snapshot predictions even if nobody opens the
    # dashboard, so the accuracy history accrues unattended.
    #   .venv/bin/python solar.py --snapshot
    import json
    import sys
    from pathlib import Path

    import yaml

    if "--snapshot" in sys.argv:
        base = Path(__file__).resolve().parent
        cfg = yaml.safe_load((base / "config.yaml").read_text()) or {}
        db = str(base / (cfg.get("storage", {}).get("db_path", "energy.db")))
        from pypowerwall.fleetapi.fleetapi import FleetAPI
        f = FleetAPI(configfile=str(base / ".pypowerwall.fleetapi"))
        result = outlook(f, cfg, db)
        print(json.dumps({"ok": True, "days": len(result["days"]),
                          "calibrated": result["calibrated"],
                          "matched": result["accuracy"]["matched"]}))
    else:
        print("usage: solar.py --snapshot", file=sys.stderr)
        sys.exit(2)
