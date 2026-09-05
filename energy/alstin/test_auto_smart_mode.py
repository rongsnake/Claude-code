"""python3 -m unittest energy/test_auto_smart_mode.py"""
import pathlib
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import auto_smart_mode as asm

TZ = ZoneInfo("Europe/London")
CFG = {**asm.DEFAULT_CONFIG, "battery_kwh": 13.5, "charge_kw": 5.0, "efficiency": 0.92,
       "buffer_minutes": 15, "target_soc": 100, "normal_reserve": 20, "charge_method": "reserve",
       "provider": "dry-run"}


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=TZ)


class WindowTests(unittest.TestCase):
    def test_evening_plans_for_tonight(self):
        ws, we = asm.next_window(at("2026-09-05T21:00"), "00:30", "05:30")
        self.assertEqual((ws, we), (at("2026-09-06T00:30"), at("2026-09-06T05:30")))

    def test_inside_window(self):
        ws, we = asm.next_window(at("2026-09-06T02:00"), "00:30", "05:30")
        self.assertEqual(ws, at("2026-09-06T00:30"))

    def test_after_window_rolls_to_next_night(self):
        ws, _ = asm.next_window(at("2026-09-06T06:00"), "00:30", "05:30")
        self.assertEqual(ws, at("2026-09-07T00:30"))

    def test_window_crossing_midnight(self):
        ws, we = asm.next_window(at("2026-09-05T21:00"), "23:30", "05:30")
        self.assertEqual((ws, we), (at("2026-09-05T23:30"), at("2026-09-06T05:30")))
        ws, we = asm.next_window(at("2026-09-06T01:00"), "23:30", "05:30")
        self.assertEqual((ws, we), (at("2026-09-05T23:30"), at("2026-09-06T05:30")))


class PlanTests(unittest.TestCase):
    def test_powerwall_from_35pct_starts_at_window_start_and_fits(self):
        p = asm.plan_charge(35, CFG, at("2026-09-05T21:00"))
        self.assertTrue(p.fits_in_window)
        self.assertEqual(p.start, at("2026-09-06T00:30"))     # not just-in-time
        self.assertLess(p.end, at("2026-09-06T05:15"))
        self.assertEqual(p.peak_minutes, 0)
        self.assertEqual(p.expected_soc, 100)

    def test_empty_powerwall_still_fits(self):
        p = asm.plan_charge(0, CFG, at("2026-09-05T21:00"))   # 13.5 kWh at 4.6 kW ≈ 176 min < 285
        self.assertTrue(p.fits_in_window)

    def test_start_early_when_it_does_not_fit(self):
        big = {**CFG, "battery_kwh": 40.5, "charge_kw": 5.0}   # three Powerwalls on one 5 kW feed
        p = asm.plan_charge(10, big, at("2026-09-05T21:00"))
        self.assertFalse(p.fits_in_window)
        self.assertLess(p.start, p.window_start)
        self.assertEqual(p.end, at("2026-09-06T05:15"))
        self.assertGreater(p.peak_minutes, 0)

    def test_run_late_policy(self):
        big = {**CFG, "battery_kwh": 40.5, "shortfall_policy": "run_late"}
        p = asm.plan_charge(10, big, at("2026-09-05T21:00"))
        self.assertEqual(p.start, p.window_start)
        self.assertGreater(p.end, p.window_end)

    def test_window_only_policy_reports_partial(self):
        big = {**CFG, "battery_kwh": 40.5, "shortfall_policy": "window_only"}
        p = asm.plan_charge(10, big, at("2026-09-05T21:00"))
        self.assertEqual(p.peak_minutes, 0)
        self.assertLess(p.expected_soc, 100)
        self.assertGreater(p.expected_soc, 10)

    def test_already_full(self):
        p = asm.plan_charge(100, CFG, at("2026-09-05T21:00"))
        self.assertEqual(p.minutes_needed, 0)
        self.assertIn("held", p.note)


class FakePowerwall:
    def __init__(self):
        self.soc, self.reserve, self.mode, self.calls = 35.0, 20, "self_consumption", []
        self.grid_charging = True

    def read(self):
        return {"soc": self.soc, "reserve": self.reserve, "mode": self.mode, "grid": "connected",
                "charging": self.soc < self.reserve, "online": True, "name": "Fake PW",
                "grid_charging": self.grid_charging}

    def set_reserve(self, p): self.reserve = int(p); self.calls.append(f"reserve{p}")
    def set_mode(self, m): self.mode = m; self.calls.append(f"mode:{m}")
    def set_grid_charging(self, on): self.grid_charging = bool(on); self.calls.append(f"grid:{on}")


class FakeFleetAPI:
    """Mimics pypowerwall.fleetapi.FleetAPI for the provider test."""
    def __init__(self):
        self.reserve, self.mode, self.disallow = 20, "self_consumption", True
        self.posts = []

    def get_live_status(self, force=False):
        return {"percentage_charged": 41.2, "grid_power": 3200, "battery_power": -3000, "grid_status": "Active"}

    def get_site_info(self, force=False):
        return {"backup_reserve_percent": self.reserve, "default_real_mode": self.mode, "site_name": "Alstin Lodge",
                "components": {"disallow_charge_from_grid_with_solar_installed": self.disallow}}

    def get_grid_charging(self, force=False): return not self.disallow
    def set_battery_reserve(self, r): self.reserve = r; self.posts.append(("reserve", r)); return {"ok": True}
    def set_operating_mode(self, m): self.mode = m; self.posts.append(("mode", m)); return {"ok": True}
    def set_grid_charging(self, m): self.disallow = (m == "off"); self.posts.append(("grid", m)); return {"ok": True}


class EngineTests(unittest.TestCase):
    """Drive the engine with a fake Powerwall through an evening → night → morning."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        asm.ENERGY_DIR, asm.CONFIG_PATH = self.tmp, self.tmp / "config.json"
        asm.STATE_PATH, asm.REQUESTS_PATH = self.tmp / "state.json", self.tmp / "requests.json"
        asm.save_json(asm.CONFIG_PATH, {**CFG, "provider": "dry-run"})
        self.pw = FakePowerwall()
        self.eng = asm.Engine(asm.load_config(), self.pw)

    def test_full_night(self):
        self.eng.tick(at("2026-09-05T21:00"))            # evening: nothing
        self.assertEqual(self.pw.calls, []); self.assertEqual(self.eng.state["mode"], "waiting")
        self.eng.tick(at("2026-09-06T00:30"))            # window start: reserve → 100
        self.assertEqual(self.pw.calls, ["reserve100"]); self.assertEqual(self.eng.state["mode"], "charging")
        self.assertEqual(self.eng.state["raised"]["reserve"], 20)
        self.pw.soc = 100
        self.eng.tick(at("2026-09-06T03:00"))            # full: held, no extra calls
        self.assertEqual(self.pw.calls, ["reserve100"]); self.assertEqual(self.eng.state["mode"], "holding")
        self.eng.tick(at("2026-09-06T05:30"))            # window end: reserve back to 20
        self.assertEqual(self.pw.calls, ["reserve100", "reserve20"]); self.assertNotIn("raised", self.eng.state)
        self.assertEqual(self.pw.reserve, 20); self.assertEqual(self.eng.state["mode"], "waiting")
        self.eng.tick(at("2026-09-06T09:00"))            # daytime: nothing more
        self.assertEqual(len(self.pw.calls), 2)

    def test_reserve_lowered_externally_is_reasserted(self):
        self.eng.tick(at("2026-09-06T00:30"))
        self.pw.reserve = 20                              # someone changed it in the Tesla app
        self.eng.tick(at("2026-09-06T01:00"))
        self.assertEqual(self.pw.reserve, 100)

    def test_boost_raises_now_and_restores_after(self):
        asm.save_json(asm.REQUESTS_PATH, {"boost_minutes": 30})
        self.eng.tick(at("2026-09-05T19:00"))
        self.assertEqual(self.pw.reserve, 100); self.assertEqual(self.eng.state["mode"], "boost")
        self.eng.tick(at("2026-09-05T19:31"))
        self.assertEqual(self.pw.reserve, 20); self.assertEqual(self.eng.state["mode"], "waiting")

    def test_disabling_mid_window_restores(self):
        self.eng.tick(at("2026-09-06T00:30"))
        asm.save_json(asm.CONFIG_PATH, {**CFG, "enabled": False})
        self.eng.tick(at("2026-09-06T01:00"))
        self.assertEqual(self.pw.reserve, 20); self.assertEqual(self.eng.state["mode"], "off")

    def test_restart_after_window_restores_stale_raise(self):
        self.eng.tick(at("2026-09-06T00:30"))
        eng2 = asm.Engine(asm.load_config(), self.pw)     # engine restarted at 07:00 with state on disk
        eng2.tick(at("2026-09-06T07:00"))
        self.assertEqual(self.pw.reserve, 20)

    def test_grid_charging_is_enabled_when_off(self):
        self.pw.grid_charging = False
        self.eng.tick(at("2026-09-06T00:30"))
        self.assertIn("grid:True", self.pw.calls)

    def test_conflict_with_live_feed_controller_stands_down(self):
        (self.tmp / "config.yaml").write_text("control:\n  enabled: true\n  dry_run: false\n")
        self.eng.tick(at("2026-09-06T00:30"))
        self.assertEqual(self.pw.calls, []); self.assertEqual(self.eng.state["mode"], "conflict")
        asm.save_json(asm.CONFIG_PATH, {**CFG, "override_feed": True})
        self.eng.tick(at("2026-09-06T00:31"))
        self.assertEqual(self.pw.reserve, 100)

    def test_backup_mode_method(self):
        asm.save_json(asm.CONFIG_PATH, {**CFG, "charge_method": "backup_mode"})
        self.eng.tick(at("2026-09-06T00:30"))
        self.assertEqual(self.pw.mode, "backup")
        self.eng.tick(at("2026-09-06T05:30"))
        self.assertEqual(self.pw.mode, "self_consumption"); self.assertEqual(self.pw.reserve, 20)


class ProviderAndSeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        asm.ENERGY_DIR, asm.CONFIG_PATH = self.tmp, self.tmp / "config.json"
        asm.STATE_PATH, asm.REQUESTS_PATH = self.tmp / "state.json", self.tmp / "requests.json"

    def test_defaults_seeded_from_dashboard_config_yaml(self):
        (self.tmp / "config.yaml").write_text(
            "battery:\n  capacity_kwh: 27\n  max_power_kw: 10\n  charge_efficiency: 0.95\n"
            "strategy:\n  reserve_floor: 10\npowerwall:\n  timezone: Europe/London\n")
        cfg = asm.load_config()
        self.assertEqual((cfg["battery_kwh"], cfg["charge_kw"], cfg["efficiency"], cfg["normal_reserve"]), (27.0, 10.0, 0.95, 10))
        self.assertEqual(cfg["provider"], "dry-run")            # no .pypowerwall.fleetapi → simulated
        (self.tmp / ".pypowerwall.fleetapi").write_text("{}")
        self.assertEqual(asm.load_config()["provider"], "fleetapi")

    def test_fleetapi_provider_reads_and_writes(self):
        f = FakeFleetAPI()
        pw = asm.FleetApiPowerwall({**CFG, "provider": "fleetapi"}, client=f)
        r = pw.read()
        self.assertEqual((r["soc"], r["reserve"], r["mode"], r["grid_charging"], r["grid_kw"], r["charging"]),
                         (41.2, 20, "self_consumption", False, 3.2, True))
        pw.set_grid_charging(True); pw.set_reserve(100); pw.set_mode("backup")
        self.assertEqual(f.posts, [("grid", "on"), ("reserve", 100), ("mode", "backup")])
        self.assertTrue(f.get_grid_charging())

    def test_full_night_through_fleetapi_in_backup_mode(self):
        f = FakeFleetAPI()
        asm.save_json(asm.CONFIG_PATH, {**CFG, "provider": "fleetapi", "charge_method": "backup_mode", "normal_reserve": 10})
        eng = asm.Engine(asm.load_config(), asm.FleetApiPowerwall(asm.load_config(), client=f))
        eng.tick(at("2026-09-06T00:30"))
        self.assertEqual(f.posts, [("grid", "on"), ("reserve", 100), ("mode", "backup")])
        f.mode = "self_consumption"                               # app user changed it mid-window
        eng.tick(at("2026-09-06T02:00"))
        self.assertEqual(f.posts[-1], ("mode", "backup"))
        eng.tick(at("2026-09-06T05:30"))
        self.assertEqual(f.posts[-2:], [("reserve", 10), ("mode", "self_consumption")])
        self.assertEqual(eng.state["mode"], "waiting")


if __name__ == "__main__":
    unittest.main()
