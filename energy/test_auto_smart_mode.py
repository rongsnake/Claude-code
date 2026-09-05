"""python3 -m unittest energy/test_auto_smart_mode.py"""
import pathlib
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import auto_smart_mode as asm

TZ = ZoneInfo("Europe/London")
CFG = {**asm.DEFAULT_CONFIG, "battery_kwh": 13.5, "charge_kw": 5.0, "efficiency": 0.92,
       "buffer_minutes": 15, "target_soc": 100, "normal_reserve": 20}


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

    def read(self):
        return {"soc": self.soc, "reserve": self.reserve, "mode": self.mode, "grid": "connected",
                "charging": self.soc < self.reserve, "online": True, "name": "Fake PW"}

    def set_reserve(self, p): self.reserve = int(p); self.calls.append(f"reserve{p}")
    def set_mode(self, m): self.mode = m; self.calls.append(f"mode:{m}")


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

    def test_backup_mode_method(self):
        asm.save_json(asm.CONFIG_PATH, {**CFG, "charge_method": "backup_mode"})
        self.eng.tick(at("2026-09-06T00:30"))
        self.assertEqual(self.pw.mode, "backup")
        self.eng.tick(at("2026-09-06T05:30"))
        self.assertEqual(self.pw.mode, "self_consumption"); self.assertEqual(self.pw.reserve, 20)


if __name__ == "__main__":
    unittest.main()
