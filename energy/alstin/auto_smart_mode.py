#!/usr/bin/env python3
"""Auto Smart Mode — charge the Tesla Powerwall from the grid in the Octopus Go off-peak window.

Goal: the home battery is full by the end of the cheap window (default 00:30–05:30
UK time, Octopus Go) every night, so the house runs on cheap stored energy through
the peak-rate day. It never grid-charges at the peak rate unless the plan says the
window alone is not enough.

How a Powerwall is made to charge from the grid: raise its **backup reserve** to the
target (100 %). The Powerwall then imports from the grid at full power until it reaches
the reserve, and will not discharge below it. At the end of the window the engine puts
the reserve back to your normal level (e.g. 20 %) and the mode back to
self-consumption, so the battery powers the house through the day.

Once a minute (``--daemon``):
  1. Read the Powerwall (state of charge, reserve, mode, grid status).
  2. Plan tonight: kWh needed to reach the target ÷ charge rate → start time so it is
     full ``buffer_minutes`` before the window ends.  If it will not fit, the
     ``shortfall_policy`` decides: ``start_early`` (begin before the window),
     ``run_late`` (keep going after it) or ``window_only`` (accept a partial charge).
  3. Act: at the planned start raise the reserve (remembering what it was); hold it
     until the window ends; then restore reserve + mode.  A "boost" request from the
     page raises the reserve now for N minutes regardless of tariff.
  4. Safety: whenever the engine finds the reserve raised by itself outside the plan
     (e.g. after a restart) it restores it, so the house is never left importing at
     the peak rate.

Providers:
  ``fleetapi``  the dashboard's own Tesla Fleet API client (pypowerwall's FleetAPI, token
                file ``.pypowerwall.fleetapi`` next to webapp.py) — chosen automatically
                when that file exists.  Note Tesla's cloud API caps the backup reserve at
                80 %, so the default charge method here is ``backup_mode``: switch the
                Powerwall to Backup-only for the window (it then fills to 100 % from the
                grid and holds), and back to self-powered afterwards.
  ``teslapy``   Tesla Owner API via the ``teslapy`` package (own login / token cache).
  ``dry-run``   simulated Powerwall (safe default when no Fleet API file exists).

Coexistence: the dashboard's optimiser loop (feed.py / alstin-lodge-energy.service)
also writes mode + reserve when ``control.enabled`` is true and ``dry_run`` false in
config.yaml.  Smart Mode reads config.yaml and refuses to act while that loop is live
(``state.conflict``), unless ``override_feed`` is set.

Files (in this directory unless overridden with ``ENERGY_DIR``):
  config.json   settings, editable from the page via energy_api.py
  state.json    live status + tonight's plan + log, read by the page
  requests.json one-shot commands from the page (boost / cancel / refresh)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ENERGY_DIR = Path(os.environ.get("ENERGY_DIR", Path(__file__).resolve().parent))
CONFIG_PATH = ENERGY_DIR / "config.json"
STATE_PATH = ENERGY_DIR / "state.json"
REQUESTS_PATH = ENERGY_DIR / "requests.json"

log = logging.getLogger("auto_smart_mode")

DEFAULT_CONFIG = {
    "enabled": True,
    "timezone": "Europe/London",
    # Octopus Go off-peak. (Intelligent Octopus Go is 23:30–05:30 — change window_start.)
    "window_start": "00:30",
    "window_end": "05:30",
    "target_soc": 100,          # % — "fully charge"
    "battery_kwh": 13.5,        # one Powerwall 2/3 = 13.5 kWh usable; two = 27
    "charge_kw": 5.0,           # grid charge rate (Powerwall 2 ≈ 5 kW, Powerwall 3 ≈ 11.5 kW)
    "efficiency": 0.92,         # AC→DC charging losses
    "buffer_minutes": 15,       # be full this long before the window ends
    "shortfall_policy": "start_early",   # start_early | run_late | window_only
    "normal_reserve": 20,       # % backup reserve to restore after the window
    "restore_mode": "self_consumption",  # operation mode to restore (self_consumption | autonomous)
    "charge_method": "backup_mode", # backup_mode (Backup-only for the window → fills to 100 %) | reserve (raise reserve only; Fleet API caps it at 80 %)
    "hold_until_window_end": True,  # keep the reserve raised until the window ends even once full
    "plan_time": "21:00",       # (re)plan from this time each evening (also Octopus lookup)
    "poll_seconds": 60,
    "provider": "auto",         # auto (fleetapi if .pypowerwall.fleetapi exists, else dry-run) | fleetapi | teslapy | dry-run
    "fleetapi_config": "",      # path to .pypowerwall.fleetapi (default: next to this file)
    "override_feed": False,     # act even if feed.py's live control is enabled in config.yaml
    "tesla_email": "",
    "tesla_cache_file": "",     # reuse an existing teslapy cache.json (e.g. the dashboard's); default ./tesla_cache.json
    "tesla_site_index": 0,
    # Optional: auto-detect the cheap window from Octopus' public tariff API.
    # e.g. product "GO-VAR-22-10-14", tariff "E-1R-GO-VAR-22-10-14-C" (C = London).
    "octopus_product": "",
    "octopus_tariff": "",
}


# ----------------------------------------------------------------------------- helpers
def parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def fmt(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="minutes") if dt else None


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str))
    tmp.replace(path)


def dashboard_config() -> dict:
    """The Alstin Lodge dashboard's config.yaml (same directory), or {} if absent."""
    try:
        import yaml
        return yaml.safe_load((ENERGY_DIR / "config.yaml").read_text()) or {}
    except Exception:  # noqa: BLE001  (no file, no yaml, bad yaml)
        return {}


def seeded_defaults() -> dict:
    """DEFAULT_CONFIG with battery / tariff / timezone facts taken from config.yaml."""
    d = dict(DEFAULT_CONFIG)
    y = dashboard_config()
    b, st, pw = y.get("battery") or {}, y.get("strategy") or {}, y.get("powerwall") or {}
    if b.get("capacity_kwh"): d["battery_kwh"] = float(b["capacity_kwh"])
    if b.get("max_power_kw"): d["charge_kw"] = float(b["max_power_kw"])
    if b.get("charge_efficiency"): d["efficiency"] = float(b["charge_efficiency"])
    if st.get("reserve_floor") is not None: d["normal_reserve"] = int(st["reserve_floor"])
    if pw.get("timezone"): d["timezone"] = pw["timezone"]
    return d


def feed_control_live() -> bool:
    """True when feed.py is configured to write to the Powerwall (it would fight us)."""
    c = dashboard_config().get("control") or {}
    return bool(c.get("enabled", False)) and not bool(c.get("dry_run", True))


def load_config() -> dict:
    cfg = seeded_defaults()
    cfg.update(load_json(CONFIG_PATH, {}))
    if cfg["provider"] == "auto":
        fa = Path(cfg["fleetapi_config"] or (ENERGY_DIR / ".pypowerwall.fleetapi"))
        cfg["provider"] = "fleetapi" if fa.exists() else "dry-run"
    return cfg


# ----------------------------------------------------------------------------- planner
@dataclass
class Plan:
    soc: float
    target_soc: float
    energy_needed_kwh: float
    charge_rate_kw: float
    minutes_needed: int
    window_start: datetime
    window_end: datetime
    start: datetime
    end: datetime
    fits_in_window: bool
    policy: str
    peak_minutes: int
    expected_soc: float
    note: str

    def to_json(self) -> dict:
        d = asdict(self)
        for k in ("window_start", "window_end", "start", "end"):
            d[k] = fmt(d[k])
        return d


def next_window(now: datetime, start_hhmm: str, end_hhmm: str) -> tuple[datetime, datetime]:
    """The off-peak window we are planning for: the one in progress, else the next one."""
    ws, we = parse_hhmm(start_hhmm), parse_hhmm(end_hhmm)
    day = now.date()
    start = datetime.combine(day, ws, tzinfo=now.tzinfo)
    end = datetime.combine(day, we, tzinfo=now.tzinfo)
    if end <= start:                       # window crosses midnight (e.g. 23:30–05:30)
        end += timedelta(days=1)
        if now < end - timedelta(days=1):  # we're in the early-morning tail of last night's window
            start -= timedelta(days=1)
            end -= timedelta(days=1)
    if now >= end:                         # tonight's window is over: plan for tomorrow
        start += timedelta(days=1)
        end += timedelta(days=1)
    return start, end


def plan_charge(soc: float, cfg: dict, now: datetime) -> Plan:
    target = float(cfg["target_soc"])
    rate = float(cfg["charge_kw"]) * float(cfg["efficiency"])
    needed = max(0.0, (target - soc) / 100.0 * float(cfg["battery_kwh"]))
    minutes = int(round(needed / rate * 60)) if rate > 0 else 0
    ws, we = next_window(now, cfg["window_start"], cfg["window_end"])
    buffer = timedelta(minutes=int(cfg["buffer_minutes"]))
    latest_finish = we - buffer
    window_minutes = int((latest_finish - ws).total_seconds() // 60)
    policy = cfg["shortfall_policy"]

    if minutes == 0:
        return Plan(soc, target, 0.0, rate, 0, ws, we, ws, ws, True, policy, 0, soc,
                    "Already at target — the reserve is simply held through the window.")

    fits = minutes <= window_minutes
    if fits:
        # Start at the window start, not just-in-time: while the reserve is raised the
        # house runs on cheap grid instead of draining the battery, so earlier is better.
        start = ws
        end = start + timedelta(minutes=minutes)
        peak = 0
        exp = target
        note = f"Needs {needed:.1f} kWh ≈ {minutes} min from the grid; full by {end:%H:%M}, then held until {we:%H:%M}."
    elif policy == "start_early":
        end = latest_finish
        start = end - timedelta(minutes=minutes)
        peak = int((ws - start).total_seconds() // 60)
        exp = target
        note = (f"Needs {needed:.1f} kWh ≈ {minutes} min — {peak} min more than the window. "
                f"Starting early at the peak rate so it is full by {latest_finish:%H:%M}.")
    elif policy == "run_late":
        start = ws
        end = ws + timedelta(minutes=minutes)
        peak = int((end - latest_finish).total_seconds() // 60)
        exp = target
        note = (f"Needs {needed:.1f} kWh ≈ {minutes} min — overrunning the window by {peak} min "
                f"at the peak rate; full at {end:%H:%M}.")
    else:  # window_only
        start, end = ws, latest_finish
        peak = 0
        got = rate * window_minutes / 60.0
        exp = round(min(target, soc + got / float(cfg["battery_kwh"]) * 100.0), 1)
        note = (f"Needs {needed:.1f} kWh ≈ {minutes} min but the window gives {window_minutes} min; "
                f"charging off-peak only — expect about {exp:.0f}%.")
    if start <= now < end:
        note += " (in progress)"
    return Plan(soc, target, round(needed, 2), round(rate, 3), minutes, ws, we, start, end,
                fits, policy, max(0, peak), exp, note)


# ----------------------------------------------------------------------------- Octopus
def octopus_offpeak_window(product: str, tariff: str) -> tuple[str, str] | None:
    """Detect the cheap block from Octopus' public unit-rate API. Returns (HH:MM, HH:MM)."""
    if not (product and tariff):
        return None
    try:
        import requests
        url = (f"https://api.octopus.energy/v1/products/{product}/electricity-tariffs/"
               f"{tariff}/standard-unit-rates/?page_size=48")
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        rates = r.json().get("results", [])
    except Exception as e:  # noqa: BLE001
        log.warning("Octopus rate lookup failed: %s", e)
        return None
    if not rates:
        return None
    cheapest = min(x["value_inc_vat"] for x in rates)
    cheap = sorted((x for x in rates if abs(x["value_inc_vat"] - cheapest) < 1e-6),
                   key=lambda x: x["valid_from"])
    if not cheap:
        return None
    tz = ZoneInfo("Europe/London")
    slot = cheap[-1]  # most recent cheap slot
    vf = datetime.fromisoformat(slot["valid_from"].replace("Z", "+00:00")).astimezone(tz)
    vt = datetime.fromisoformat(slot["valid_to"].replace("Z", "+00:00")).astimezone(tz)
    return vf.strftime("%H:%M"), vt.strftime("%H:%M")


# ----------------------------------------------------------------------------- Powerwall providers
class DryRunPowerwall:
    """Simulated Powerwall so the engine and page can be exercised without Tesla access."""

    HOUSE_KW = 0.6  # overnight house load when discharging

    def __init__(self, cfg: dict):
        self.cfg = cfg
        sim = load_json(ENERGY_DIR / "sim.json", {})
        self.soc = float(sim.get("soc", 35))
        self.reserve = int(sim.get("reserve", cfg["normal_reserve"]))
        self.mode = sim.get("mode", "self_consumption")
        self.last = datetime.fromisoformat(sim["ts"]) if sim.get("ts") else None

    def _save(self):
        save_json(ENERGY_DIR / "sim.json", {"soc": self.soc, "reserve": self.reserve, "mode": self.mode,
                                             "ts": datetime.now().astimezone().isoformat()})

    def read(self) -> dict:
        now = datetime.now().astimezone()
        if self.last:
            hrs = (now - self.last).total_seconds() / 3600
            cap = float(self.cfg["battery_kwh"])
            if self.soc < self.reserve or self.mode == "backup":
                self.soc = min(max(self.reserve, self.soc), self.soc + hrs * self.cfg["charge_kw"] * self.cfg["efficiency"] / cap * 100)
                if self.mode == "backup":
                    self.soc = min(100.0, self.soc)
            else:
                self.soc = max(float(self.reserve), self.soc - hrs * self.HOUSE_KW / cap * 100)
        self.last = now
        self._save()
        charging = self.soc < self.reserve or (self.mode == "backup" and self.soc < 100)
        return {"soc": round(self.soc, 1), "reserve": self.reserve, "mode": self.mode,
                "grid": "connected", "charging": charging, "online": True, "name": "Simulated Powerwall",
                "capacity_kwh": float(self.cfg["battery_kwh"])}

    def set_reserve(self, pct: int): self.reserve = int(pct); self._save()
    def set_mode(self, mode: str): self.mode = mode; self._save()


class TeslaPyPowerwall:
    """Tesla energy site via `pip install teslapy` (Owner API). Token cache reusable."""

    def __init__(self, cfg: dict):
        import teslapy  # noqa: F401
        cache = cfg.get("tesla_cache_file") or str(ENERGY_DIR / "tesla_cache.json")
        self.tesla = teslapy.Tesla(cfg["tesla_email"], cache_file=cache)
        if not self.tesla.authorized:
            print("Open this URL, log in, then paste the resulting (blank-page) URL back here:")
            print(self.tesla.authorization_url())
            self.tesla.fetch_token(authorization_response=input("URL: ").strip())
        self.b = self.tesla.battery_list()[int(cfg["tesla_site_index"])]

    def read(self) -> dict:
        d = self.b.get_battery_data()
        cap = float(d.get("total_pack_energy") or 0) / 1000.0
        left = float(d.get("energy_left") or 0) / 1000.0
        soc = float(d.get("percentage_charged") or (left / cap * 100 if cap else 0))
        pm = d.get("power_reading") or [{}]
        grid_kw = float((pm[0] or {}).get("grid_power") or 0) / 1000.0
        return {"soc": round(soc, 1), "reserve": int(d.get("backup", {}).get("backup_reserve_percent", 0)),
                "mode": d.get("operation") or d.get("default_real_mode"), "grid": d.get("grid_status"),
                "charging": grid_kw > 0.2 and soc < 100, "grid_kw": round(grid_kw, 2), "online": True,
                "name": d.get("site_name", "Powerwall"), "capacity_kwh": round(cap, 1)}

    def set_reserve(self, pct: int): self.b.set_backup_reserve_percent(int(pct))
    def set_mode(self, mode: str): self.b.set_operation(mode)


class FleetApiPowerwall:
    """The dashboard's own Tesla Fleet API client (pypowerwall.fleetapi.FleetAPI).

    Reuses ``.pypowerwall.fleetapi`` (client id/secret + tokens; FleetAPI refreshes
    the access token itself), so no second Tesla login is needed.
    """

    def __init__(self, cfg: dict, client=None):
        if client is None:
            from pypowerwall.fleetapi.fleetapi import FleetAPI
            client = FleetAPI(configfile=cfg.get("fleetapi_config") or str(ENERGY_DIR / ".pypowerwall.fleetapi"))
        self.f = client
        self._cap = float(cfg["battery_kwh"])

    def read(self) -> dict:
        live = self.f.get_live_status(force=True) or {}
        info = self.f.get_site_info(force=True) or {}
        grid_w = float(live.get("grid_power") or 0)
        soc = float(live.get("percentage_charged") or 0)
        return {"soc": round(soc, 1), "reserve": int(info.get("backup_reserve_percent") or 0),
                "mode": info.get("default_real_mode"), "grid": live.get("grid_status"),
                "grid_charging": self.f.get_grid_charging(), "grid_kw": round(grid_w / 1000.0, 2),
                "charging": grid_w > 200 and float(live.get("battery_power") or 0) < -200,
                "online": True, "name": info.get("site_name") or "Powerwall", "capacity_kwh": self._cap}

    @staticmethod
    def _ok(r, what):
        if r is False:
            raise RuntimeError(f"Fleet API rejected {what}")

    def set_reserve(self, pct: int): self._ok(self.f.set_battery_reserve(int(pct)), f"reserve {pct}%")
    def set_mode(self, mode: str): self._ok(self.f.set_operating_mode(mode), f"mode {mode}")
    def set_grid_charging(self, on: bool): self._ok(self.f.set_grid_charging("on" if on else "off"), "grid charging")


def make_powerwall(cfg: dict):
    p = cfg["provider"]
    if p == "fleetapi":
        return FleetApiPowerwall(cfg)
    if p == "teslapy":
        return TeslaPyPowerwall(cfg)
    return DryRunPowerwall(cfg)


# ----------------------------------------------------------------------------- engine
class Engine:
    def __init__(self, cfg: dict, pw):
        self.cfg = cfg
        self.pw = pw
        self.tz = ZoneInfo(cfg["timezone"])
        self.state = load_json(STATE_PATH, {"log": []})
        self.state.setdefault("log", [])

    # -- state/log
    def note(self, msg: str, level: str = "info") -> None:
        getattr(log, level)(msg)
        self.state["log"].append({"ts": datetime.now(self.tz).isoformat(timespec="seconds"), "msg": msg})
        self.state["log"] = self.state["log"][-200:]

    def save(self) -> None:
        self.state["last_tick"] = datetime.now(self.tz).isoformat(timespec="seconds")
        self.state["enabled"] = bool(self.cfg["enabled"])
        self.state["provider"] = self.cfg["provider"]
        save_json(STATE_PATH, self.state)

    def take_requests(self) -> dict:
        req = load_json(REQUESTS_PATH, {})
        if req:
            save_json(REQUESTS_PATH, {})
        return req

    # -- the decision, once a minute
    def tick(self, now: datetime | None = None) -> None:
        self.cfg = load_config()
        now = now or datetime.now(self.tz)
        req = self.take_requests()

        # Boost = grid-charge now regardless of tariff, until the given time.
        if "boost_minutes" in req:
            until = now + timedelta(minutes=int(req["boost_minutes"]))
            self.state["boost_until"] = fmt(until)
            self.note(f"Boost requested: grid-charging at any rate until {until:%H:%M}.")
        if req.get("cancel_boost"):
            self.state.pop("boost_until", None)
            self.note("Boost cancelled.")
        boost_until = self.state.get("boost_until")
        boosting = bool(boost_until) and datetime.fromisoformat(boost_until) > now
        if boost_until and not boosting:
            self.state.pop("boost_until", None)

        try:
            v = self.pw.read()
        except Exception as e:  # noqa: BLE001
            self.note(f"Powerwall read failed: {e}", "warning")
            self.state["error"] = str(e)
            self.save()
            return
        self.state.pop("error", None)
        v["ts"] = now.isoformat(timespec="seconds")
        self.state["battery"] = v

        # Optional: refresh window from Octopus once a day.
        if self._is_plan_time(now) and self.cfg.get("octopus_product"):
            win = octopus_offpeak_window(self.cfg["octopus_product"], self.cfg["octopus_tariff"])
            if win and win != (self.cfg["window_start"], self.cfg["window_end"]):
                self.note(f"Octopus tariff says off-peak is {win[0]}–{win[1]}; using it.")
                self.cfg["window_start"], self.cfg["window_end"] = win
                save_json(CONFIG_PATH, {**load_json(CONFIG_PATH, {}), "window_start": win[0], "window_end": win[1]})

        soc = float(v.get("soc", 0))
        plan = plan_charge(soc, self.cfg, now)
        self.state["plan"] = plan.to_json()
        self.state["boosting"] = boosting
        raised = self.state.get("raised")          # what we changed, so we can put it back

        if not self.cfg["enabled"]:
            self.state["mode"] = "off"
            if raised:
                self._restore(raised, "Auto Smart Mode switched off")
            self.save()
            return

        # The dashboard's own optimiser loop would fight us if it is live.
        if feed_control_live() and not self.cfg["override_feed"]:
            self.state["conflict"] = ("feed.py live control is enabled in config.yaml (control.enabled true, "
                                      "dry_run false) — Smart Mode is standing down. Disable one of them.")
            self.state["mode"] = "conflict"
            if raised:
                self._restore(raised, "feed.py live control detected")
            self.save()
            return
        self.state.pop("conflict", None)

        hold_end = plan.window_end if self.cfg["hold_until_window_end"] else plan.end
        want = boosting or (plan.start <= now < hold_end)
        raised_before = raised
        if want and not raised:
            self._raise(v, plan, boosting)
        elif not want and raised:
            self._restore(raised, f"window over at {hold_end:%H:%M}" if now >= hold_end else "outside the plan")
        raised = self.state.get("raised")

        if raised:
            self.state["mode"] = "boost" if boosting else ("holding" if soc >= plan.target_soc - 0.5 else "charging")
            # Somebody (the Tesla app?) lowered the reserve under us — re-assert it. (The reading
            # predates a raise made this tick, so only check on later ticks.)
            if raised_before and not boosting:
                try:
                    if self.cfg["charge_method"] == "backup_mode" and v.get("mode") not in (None, "backup"):
                        self.pw.set_mode("backup")
                        self.note(f"Mode was {v.get('mode')} — set back to backup for the window.")
                    elif self.cfg["charge_method"] == "reserve" and int(v.get("reserve", 0)) < min(int(plan.target_soc), 80):
                        self.pw.set_reserve(int(plan.target_soc))
                        self.note(f"Reserve was {v.get('reserve')}% — set back to {plan.target_soc:.0f}%.")
                except Exception as e:  # noqa: BLE001
                    self.note(f"Could not re-assert: {e}", "warning")
        else:
            self.state["mode"] = "waiting"
        self.save()

    def _is_plan_time(self, now: datetime) -> bool:
        pt = parse_hhmm(self.cfg["plan_time"])
        return now.hour == pt.hour and now.minute == pt.minute

    def _raise(self, v: dict, plan: Plan, boosting: bool) -> None:
        target = int(plan.target_soc)
        prev = {"reserve": int(v.get("reserve", self.cfg["normal_reserve"])), "mode": v.get("mode") or self.cfg["restore_mode"],
                "grid_charging": v.get("grid_charging")}
        try:
            if v.get("grid_charging") is False and hasattr(self.pw, "set_grid_charging"):
                self.pw.set_grid_charging(True)          # otherwise it cannot pull from the grid at all
            self.pw.set_reserve(target)
            if self.cfg["charge_method"] == "backup_mode":
                self.pw.set_mode("backup")
            self.state["raised"] = {**prev, "at": fmt(datetime.now(self.tz))}
            why = "boost" if boosting else f"planned start ({plan.soc:.0f}% → {target}%, full ~{plan.end:%H:%M})"
            self.note(f"Grid charging on: reserve {prev['reserve']}% → {target}% — {why}.")
        except Exception as e:  # noqa: BLE001
            self.note(f"Could not raise the reserve: {e}", "warning")

    def _restore(self, raised: dict, why: str) -> None:
        reserve = int(self.cfg["normal_reserve"]) if self.cfg.get("normal_reserve") is not None else int(raised.get("reserve", 20))
        mode = self.cfg["restore_mode"] or raised.get("mode") or "self_consumption"
        try:
            self.pw.set_reserve(reserve)
            if self.cfg["charge_method"] == "backup_mode" or raised.get("mode") not in (None, mode):
                self.pw.set_mode(mode)
            self.state.pop("raised", None)
            self.note(f"Grid charging off: reserve back to {reserve}%, mode {mode} — {why}.")
        except Exception as e:  # noqa: BLE001
            self.note(f"Could not restore the reserve: {e}", "warning")


# ----------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--daemon", action="store_true", help="run forever, one tick per poll_seconds")
    ap.add_argument("--once", action="store_true", help="one tick then exit")
    ap.add_argument("--plan", type=float, metavar="SOC", help="print tonight's plan for a given SoC %% and exit")
    ap.add_argument("--init-config", action="store_true", help="write config.json with defaults if missing")
    ap.add_argument("--now", help="ISO timestamp to plan as-of (testing)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not CONFIG_PATH.exists():
        save_json(CONFIG_PATH, seeded_defaults())
        print(f"wrote {CONFIG_PATH}")
    if a.init_config:
        return 0
    cfg = load_config()
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(a.now).astimezone(tz) if a.now else datetime.now(tz)

    if a.plan is not None:
        print(json.dumps(plan_charge(a.plan, cfg, now).to_json(), indent=2))
        return 0

    eng = Engine(cfg, make_powerwall(cfg))
    if a.daemon:
        eng.note("Auto Smart Mode engine started.")
        while True:
            try:
                eng.tick()
            except Exception as e:  # noqa: BLE001
                log.exception("tick failed: %s", e)
            time.sleep(int(load_config()["poll_seconds"]))
    eng.tick(now)
    print(json.dumps({k: eng.state.get(k) for k in ("mode", "battery", "plan", "raised")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
