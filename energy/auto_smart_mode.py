#!/usr/bin/env python3
"""Auto Smart Mode — overnight Tesla charging engine for the Octopus Go off-peak window.

Goal: the car is (almost) always at its target charge by the end of the cheap
window (default 00:30–05:30 UK time, i.e. Octopus Go) while never charging at the
peak rate unless the plan says the window alone is not enough.

How it works, once a minute (``--daemon``):
  1. Read the vehicle (state of charge, plugged in, charging state).
  2. Build tonight's plan: how many kWh are needed to reach the target, how long
     that takes on the home charger, and therefore when to start so it finishes
     by the end of the window.  If it will not fit, the ``shortfall_policy``
     decides: ``start_early`` (begin before the window, just enough), ``run_late``
     (keep going past the window end) or ``window_only`` (accept a partial charge).
  3. Act: start charging at the planned time, keep it going, stop it at the
     window end (window_only), and — if ``block_peak_charging`` is on — pause any
     charging that starts at the peak rate outside the plan (a "boost" request
     from the page overrides this).
  4. As belt-and-braces, push Tesla's own scheduled-charging time for the window
     start to the car, so it still starts on time if this engine is down.

Providers: ``dry-run`` (simulated car, safe default) and ``teslapy`` (Tesla Owner
API via the ``teslapy`` package; first run performs the browser OAuth flow).

Files (all in this directory unless overridden with ``ENERGY_DIR``):
  config.json   settings, editable from the page via energy_api.py
  state.json    live status + tonight's plan + log, read by the page
  requests.json one-shot commands from the page (boost / charge-now / refresh)
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
    "battery_kwh": 75.0,        # usable pack size (Model Y/3 Long Range ≈ 75)
    "charger_kw": 7.4,          # single-phase 32 A home charger
    "charge_amps": 32,
    "efficiency": 0.90,         # AC charging losses
    "buffer_minutes": 15,       # finish this long before the window ends
    "shortfall_policy": "start_early",   # start_early | run_late | window_only
    "block_peak_charging": True, # pause charging that starts outside the plan
    "push_native_schedule": True,# also set Tesla's own scheduled-charging time
    "plan_time": "21:00",        # (re)plan from this time each evening
    "poll_seconds": 60,
    "provider": "dry-run",       # dry-run | teslapy
    "tesla_email": "",
    "tesla_vehicle_index": 0,
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


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
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
    rate = float(cfg["charger_kw"]) * float(cfg["efficiency"])
    needed = max(0.0, (target - soc) / 100.0 * float(cfg["battery_kwh"]))
    minutes = int(round(needed / rate * 60)) if rate > 0 else 0
    ws, we = next_window(now, cfg["window_start"], cfg["window_end"])
    buffer = timedelta(minutes=int(cfg["buffer_minutes"]))
    latest_finish = we - buffer
    window_minutes = int((latest_finish - ws).total_seconds() // 60)
    policy = cfg["shortfall_policy"]

    if minutes == 0:
        return Plan(soc, target, 0.0, rate, 0, ws, we, ws, ws, True, policy, 0, soc,
                    "Already at target — nothing to do tonight.")

    fits = minutes <= window_minutes
    if fits:
        start = latest_finish - timedelta(minutes=minutes)
        start = max(start, ws)               # never earlier than the window
        end = start + timedelta(minutes=minutes)
        peak = 0
        exp = target
        note = f"Needs {needed:.1f} kWh ≈ {minutes} min; fits in the off-peak window."
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
    first = cheap[-1]  # most recent cheap slot
    vf = datetime.fromisoformat(first["valid_from"].replace("Z", "+00:00")).astimezone(tz)
    vt = datetime.fromisoformat(first["valid_to"].replace("Z", "+00:00")).astimezone(tz)
    return vf.strftime("%H:%M"), vt.strftime("%H:%M")


# ----------------------------------------------------------------------------- vehicle providers
class DryRunVehicle:
    """Simulated car so the engine and page can be exercised without Tesla access."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        sim = load_json(ENERGY_DIR / "sim.json", {})
        self.soc = float(sim.get("soc", 42))
        self.plugged = bool(sim.get("plugged_in", True))
        self.charging = bool(sim.get("charging", False))
        self.limit = int(sim.get("charge_limit", cfg["target_soc"]))
        self.last = datetime.fromisoformat(sim["ts"]) if sim.get("ts") else None

    def _save(self):
        save_json(ENERGY_DIR / "sim.json", {"soc": self.soc, "plugged_in": self.plugged,
                                             "charging": self.charging, "charge_limit": self.limit,
                                             "ts": datetime.now().astimezone().isoformat()})

    def read(self) -> dict:
        now = datetime.now().astimezone()
        if self.charging and self.last:
            hrs = (now - self.last).total_seconds() / 3600
            self.soc = min(self.limit, self.soc + hrs * self.cfg["charger_kw"] * self.cfg["efficiency"]
                           / self.cfg["battery_kwh"] * 100)
            if self.soc >= self.limit:
                self.charging = False
        self.last = now
        self._save()
        return {"soc": round(self.soc, 1), "plugged_in": self.plugged,
                "charging_state": "Charging" if self.charging else ("Stopped" if self.plugged else "Disconnected"),
                "charge_limit": self.limit, "online": True, "name": "Simulated Tesla"}

    def start(self): self.charging = self.plugged; self._save()
    def stop(self): self.charging = False; self._save()
    def set_limit(self, pct): self.limit = int(pct); self._save()
    def set_amps(self, amps): pass
    def set_scheduled_charging(self, enable, minutes_after_midnight): pass


class TeslaPyVehicle:
    """Tesla Owner API via `pip install teslapy`. Cache lives next to this file."""

    def __init__(self, cfg: dict):
        import teslapy  # noqa: F401  (import error surfaces clearly)
        self.tesla = teslapy.Tesla(cfg["tesla_email"], cache_file=str(ENERGY_DIR / "tesla_cache.json"))
        if not self.tesla.authorized:
            print("Open this URL, log in, then paste the resulting (blank-page) URL back here:")
            print(self.tesla.authorization_url())
            self.tesla.fetch_token(authorization_response=input("URL: ").strip())
        self.v = self.tesla.vehicle_list()[int(cfg["tesla_vehicle_index"])]
        self._awake_until = None

    def _wake(self):
        if not self.v.available():
            self.v.sync_wake_up()

    def read(self, wake: bool = True) -> dict:
        if not wake and not self.v.available():
            return {"online": False, "name": self.v["display_name"]}
        self._wake()
        d = self.v.get_vehicle_data()
        cs = d["charge_state"]
        return {"soc": cs["battery_level"], "plugged_in": cs["charging_state"] != "Disconnected",
                "charging_state": cs["charging_state"], "charge_limit": cs["charge_limit_soc"],
                "online": True, "name": d["display_name"],
                "charger_power_kw": cs.get("charger_power"), "minutes_to_full": cs.get("minutes_to_full_charge")}

    def start(self): self._wake(); self.v.command("START_CHARGE")
    def stop(self): self._wake(); self.v.command("STOP_CHARGE")
    def set_limit(self, pct): self._wake(); self.v.command("CHANGE_CHARGE_LIMIT", percent=int(pct))
    def set_amps(self, amps): self._wake(); self.v.command("CHARGING_AMPS", charging_amps=int(amps))
    def set_scheduled_charging(self, enable, minutes_after_midnight):
        self._wake(); self.v.command("SCHEDULED_CHARGING", enable=bool(enable), time=int(minutes_after_midnight))


def make_vehicle(cfg: dict):
    return TeslaPyVehicle(cfg) if cfg["provider"] == "teslapy" else DryRunVehicle(cfg)


# ----------------------------------------------------------------------------- engine
class Engine:
    def __init__(self, cfg: dict, vehicle):
        self.cfg = cfg
        self.vehicle = vehicle
        self.tz = ZoneInfo(cfg["timezone"])
        self.state = load_json(STATE_PATH, {"log": []})
        self.state.setdefault("log", [])
        self._native_pushed_for = self.state.get("native_schedule_pushed_for")

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

        # Boost = charge now regardless of tariff, until the given time.
        if "boost_minutes" in req:
            until = now + timedelta(minutes=int(req["boost_minutes"]))
            self.state["boost_until"] = fmt(until)
            self.note(f"Boost requested: charging at any rate until {until:%H:%M}.")
        if req.get("cancel_boost"):
            self.state.pop("boost_until", None)
            self.note("Boost cancelled.")
        boost_until = self.state.get("boost_until")
        boosting = bool(boost_until) and datetime.fromisoformat(boost_until) > now
        if boost_until and not boosting:
            self.state.pop("boost_until", None)

        # Read the car. Outside the action periods only read it if it is already awake,
        # so we don't keep it from sleeping (vampire drain).
        plan_prev = self.state.get("plan")
        in_action = bool(plan_prev and plan_prev.get("start") and
                         datetime.fromisoformat(plan_prev["start"]) - timedelta(minutes=2) <= now
                         <= datetime.fromisoformat(plan_prev["end"]) + timedelta(minutes=5))
        must_wake = in_action or boosting or req.get("refresh") or self._is_plan_time(now) \
            or "vehicle" not in self.state
        try:
            v = self.vehicle.read(wake=True) if not isinstance(self.vehicle, DryRunVehicle) and must_wake \
                else (self.vehicle.read() if isinstance(self.vehicle, DryRunVehicle) else self.vehicle.read(wake=False))
        except Exception as e:  # noqa: BLE001
            self.note(f"Vehicle read failed: {e}", "warning")
            self.state["error"] = str(e)
            self.save()
            return
        self.state.pop("error", None)
        if v.get("online"):
            v["ts"] = now.isoformat(timespec="seconds")
            self.state["vehicle"] = v
        v = self.state.get("vehicle", v)

        # Optional: refresh window from Octopus once a day.
        if self._is_plan_time(now) and self.cfg.get("octopus_product"):
            win = octopus_offpeak_window(self.cfg["octopus_product"], self.cfg["octopus_tariff"])
            if win and win != (self.cfg["window_start"], self.cfg["window_end"]):
                self.note(f"Octopus tariff says off-peak is {win[0]}–{win[1]}; using it.")
                self.cfg["window_start"], self.cfg["window_end"] = win
                save_json(CONFIG_PATH, {**load_json(CONFIG_PATH, {}), "window_start": win[0], "window_end": win[1]})

        # Plan (cheap; recomputed every tick from the latest SoC).
        soc = float(v.get("soc", 0))
        plan = plan_charge(soc, self.cfg, now)
        self.state["plan"] = plan.to_json()
        self.state["boosting"] = boosting

        if not self.cfg["enabled"]:
            self.state["mode"] = "off"
            self.save()
            return

        # Belt-and-braces: Tesla's own schedule for the window start (once per window).
        key = fmt(plan.window_start)
        if self.cfg["push_native_schedule"] and self._native_pushed_for != key:
            try:
                ws = plan.window_start
                self.vehicle.set_scheduled_charging(True, ws.hour * 60 + ws.minute)
                self.vehicle.set_limit(self.cfg["target_soc"])
                self._native_pushed_for = key
                self.state["native_schedule_pushed_for"] = key
                self.note(f"Pushed Tesla scheduled charging for {ws:%H:%M} and limit {self.cfg['target_soc']}%.")
            except Exception as e:  # noqa: BLE001
                self.note(f"Could not push native schedule: {e}", "warning")

        charging = v.get("charging_state") == "Charging"
        plugged = bool(v.get("plugged_in"))
        want = boosting or (plan.start <= now < plan.end and soc < plan.target_soc)
        self.state["mode"] = "boost" if boosting else ("charging" if want else "waiting")

        if want and plugged and not charging:
            self._act("start", plan)
        elif not want and charging and not boosting and self.cfg["block_peak_charging"]:
            # Charging outside the plan: only intervene at the peak rate. Inside the
            # window but after the plan's end (already at target) we leave it alone.
            in_window = plan.window_start <= now < plan.window_end
            if not in_window:
                self._act("stop", plan)
        if want and not plugged:
            self.state["mode"] = "not plugged in"
            if not self.state.get("warned_unplugged") == key:
                self.note("Planned start reached but the car is not plugged in.", "warning")
                self.state["warned_unplugged"] = key
        self.save()

    def _is_plan_time(self, now: datetime) -> bool:
        pt = parse_hhmm(self.cfg["plan_time"])
        return now.hour == pt.hour and now.minute == pt.minute

    def _act(self, what: str, plan: Plan) -> None:
        try:
            if what == "start":
                self.vehicle.set_limit(self.cfg["target_soc"])
                self.vehicle.set_amps(self.cfg["charge_amps"])
                self.vehicle.start()
                self.note(f"Started charging ({plan.soc:.0f}% → {plan.target_soc:.0f}%, ends ~{plan.end:%H:%M}).")
            else:
                self.vehicle.stop()
                self.note(f"Paused charging: peak rate now; plan resumes at {plan.start:%H:%M}.")
        except Exception as e:  # noqa: BLE001
            self.note(f"Command {what} failed: {e}", "warning")


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

    if a.init_config or not CONFIG_PATH.exists():
        if not CONFIG_PATH.exists():
            save_json(CONFIG_PATH, DEFAULT_CONFIG)
            print(f"wrote {CONFIG_PATH}")
        if a.init_config:
            return 0
    cfg = load_config()
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(a.now).astimezone(tz) if a.now else datetime.now(tz)

    if a.plan is not None:
        print(json.dumps(plan_charge(a.plan, cfg, now).to_json(), indent=2))
        return 0

    eng = Engine(cfg, make_vehicle(cfg))
    if a.daemon:
        eng.note("Auto Smart Mode engine started.")
        while True:
            try:
                eng.tick()
            except Exception as e:  # noqa: BLE001
                log.exception("tick failed: %s", e)
            time.sleep(int(load_config()["poll_seconds"]))
    eng.tick(now)
    print(json.dumps({k: eng.state.get(k) for k in ("mode", "vehicle", "plan")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
