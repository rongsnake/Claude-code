"""python3 -m unittest energy/test_auto_smart_mode.py"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import auto_smart_mode as asm

TZ = ZoneInfo("Europe/London")
CFG = {**asm.DEFAULT_CONFIG, "battery_kwh": 75, "charger_kw": 7.4, "efficiency": 0.9,
       "buffer_minutes": 15, "target_soc": 100}


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
    def test_fits_and_finishes_just_before_window_end(self):
        p = asm.plan_charge(70, CFG, at("2026-09-05T21:00"))
        self.assertTrue(p.fits_in_window)
        self.assertEqual(p.peak_minutes, 0)
        self.assertEqual(p.end, at("2026-09-06T05:15"))
        self.assertGreaterEqual(p.start, p.window_start)
        self.assertEqual(p.expected_soc, 100)

    def test_start_early_when_it_does_not_fit(self):
        p = asm.plan_charge(30, CFG, at("2026-09-05T21:00"))
        self.assertFalse(p.fits_in_window)
        self.assertLess(p.start, p.window_start)
        self.assertEqual(p.end, at("2026-09-06T05:15"))
        self.assertGreater(p.peak_minutes, 0)
        self.assertEqual(p.expected_soc, 100)

    def test_run_late_policy(self):
        p = asm.plan_charge(30, {**CFG, "shortfall_policy": "run_late"}, at("2026-09-05T21:00"))
        self.assertEqual(p.start, p.window_start)
        self.assertGreater(p.end, p.window_end)

    def test_window_only_policy_reports_partial(self):
        p = asm.plan_charge(30, {**CFG, "shortfall_policy": "window_only"}, at("2026-09-05T21:00"))
        self.assertEqual(p.peak_minutes, 0)
        self.assertLess(p.expected_soc, 100)
        self.assertGreater(p.expected_soc, 30)

    def test_already_full(self):
        p = asm.plan_charge(100, CFG, at("2026-09-05T21:00"))
        self.assertEqual(p.minutes_needed, 0)
        self.assertIn("nothing to do", p.note)


class EngineTests(unittest.TestCase):
    """Drive the engine with a fake car through an evening → night → morning."""

    def setUp(self):
        import tempfile, pathlib
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        asm.ENERGY_DIR, asm.CONFIG_PATH = self.tmp, self.tmp / "config.json"
        asm.STATE_PATH, asm.REQUESTS_PATH = self.tmp / "state.json", self.tmp / "requests.json"
        asm.save_json(asm.CONFIG_PATH, {**CFG, "provider": "dry-run"})

        class Fake:
            soc, plugged, charging, calls = 60, True, False, []
            def read(self, wake=True):
                return {"soc": self.soc, "plugged_in": self.plugged, "online": True,
                        "charging_state": "Charging" if self.charging else "Stopped", "charge_limit": 100}
            def start(self): self.charging = True; self.calls.append("start")
            def stop(self): self.charging = False; self.calls.append("stop")
            def set_limit(self, p): self.calls.append(f"limit{p}")
            def set_amps(self, a): pass
            def set_scheduled_charging(self, e, m): self.calls.append(f"sched{m}")
        self.car = Fake()
        self.eng = asm.Engine(asm.load_config(), self.car)

    def test_peak_charging_is_paused_and_night_charging_started(self):
        self.car.charging = True
        self.eng.tick(at("2026-09-05T19:00"))          # plugged in at peak: pause it
        self.assertIn("stop", self.car.calls)
        self.assertIn("sched30", self.car.calls)        # native schedule pushed for 00:30
        self.eng.tick(at("2026-09-05T23:00"))          # before planned start: nothing
        self.assertNotIn("start", self.car.calls)
        self.eng.tick(at("2026-09-06T02:00"))          # inside the plan: start
        self.assertIn("start", self.car.calls)
        self.assertEqual(self.eng.state["mode"], "charging")

    def test_boost_overrides_tariff(self):
        asm.save_json(asm.REQUESTS_PATH, {"boost_minutes": 30})
        self.eng.tick(at("2026-09-05T19:00"))
        self.assertIn("start", self.car.calls)
        self.assertEqual(self.eng.state["mode"], "boost")

    def test_disabled_mode_does_nothing(self):
        asm.save_json(asm.CONFIG_PATH, {**CFG, "enabled": False})
        self.car.charging = True
        self.eng.tick(at("2026-09-05T19:00"))
        self.assertEqual(self.car.calls, [])
        self.assertEqual(self.eng.state["mode"], "off")


if __name__ == "__main__":
    unittest.main()
