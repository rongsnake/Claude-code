"""Unit tests for the solar-aware charge target (pure functions only)."""
import datetime as dt
import unittest

import solar
from strategy import ACTION_CHARGE, ACTION_SELF_USE, StrategyConfig, decide


class FakeRate:
    def __init__(self, value, start, hours):
        self.value_inc_vat = value
        self.start = start
        self.end = start + dt.timedelta(hours=hours)

    def covers(self, when):
        return self.start <= when < self.end

    def duration_hours(self):
        return (self.end - self.start).total_seconds() / 3600


class TestChargeTarget(unittest.TestCase):
    def test_sunny_day_leaves_headroom(self):
        # 25 kWh PV - 9 kWh day load = 16 kWh surplus * 0.95 = 15.2 kWh
        # vs 13.5 kWh capacity -> headroom > capacity -> clamp to min.
        t = solar.charge_target_pct(25.0, 9.0, 13.5, 0.95, min_pct=35)
        self.assertEqual(t, 35)

    def test_mixed_day_partial_headroom(self):
        # 15 kWh PV - 9 = 6 * 0.95 = 5.7 kWh = 42.2% of 13.5 -> target ~58.
        t = solar.charge_target_pct(15.0, 9.0, 13.5, 0.95, min_pct=35)
        self.assertEqual(t, 58)

    def test_dull_day_charges_full(self):
        t = solar.charge_target_pct(4.0, 9.0, 13.5, 0.95, min_pct=35)
        self.assertEqual(t, 100)

    def test_never_below_min(self):
        t = solar.charge_target_pct(100.0, 0.0, 13.5, 0.95, min_pct=35)
        self.assertEqual(t, 35)


class TestCalibrate(unittest.TestCase):
    today = dt.date(2026, 6, 10)

    def test_median_yield(self):
        rad = {dt.date(2026, 6, 7): 20.0, dt.date(2026, 6, 8): 10.0,
               dt.date(2026, 6, 9): 30.0, self.today: 28.0}
        kwh = {dt.date(2026, 6, 7): 18.0, dt.date(2026, 6, 8): 9.6,
               dt.date(2026, 6, 9): 26.6, self.today: 5.0}
        k, n = solar.calibrate(rad, kwh, today=self.today)
        self.assertEqual(n, 3)  # today excluded (still accumulating)
        self.assertAlmostEqual(k, 0.9, places=2)

    def test_insufficient_data_returns_none(self):
        rad = {dt.date(2026, 6, 9): 30.0}
        kwh = {dt.date(2026, 6, 9): 26.6}
        k, n = solar.calibrate(rad, kwh, today=self.today)
        self.assertIsNone(k)
        self.assertEqual(n, 1)

    def test_skips_dud_days(self):
        rad = {dt.date(2026, 6, 8): 1.0, dt.date(2026, 6, 9): 30.0}
        kwh = {dt.date(2026, 6, 8): 0.1, dt.date(2026, 6, 9): 26.6}
        k, n = solar.calibrate(rad, kwh, today=self.today)
        self.assertIsNone(k)  # only one usable day after filtering
        self.assertEqual(n, 1)


class TestNextDaylightDate(unittest.TestCase):
    def test_go_window_targets_same_day(self):
        now = dt.datetime(2026, 6, 10, 1, 30)
        self.assertEqual(solar.next_daylight_date(now), dt.date(2026, 6, 10))

    def test_evening_targets_tomorrow(self):
        now = dt.datetime(2026, 6, 10, 22, 0)
        self.assertEqual(solar.next_daylight_date(now), dt.date(2026, 6, 11))


class TestDecideWithSolarTarget(unittest.TestCase):
    """charge_target overrides the static 100% target in Rule 1."""

    def setUp(self):
        self.cfg = StrategyConfig()
        self.now = dt.datetime(2026, 6, 10, 1, 0, tzinfo=dt.timezone.utc)
        cheap = FakeRate(8.63, self.now - dt.timedelta(hours=1), 5)
        self.import_rates = [cheap]
        self.export_rates = [FakeRate(12.0, self.now - dt.timedelta(hours=1), 24)]

    def test_charges_up_to_solar_target(self):
        d = decide(self.now, self.import_rates, self.export_rates, soc=30,
                   cfg=self.cfg, charge_target=58)
        self.assertEqual(d.action, ACTION_CHARGE)
        self.assertEqual(d.reserve, 58)
        self.assertIn("solar-aware", d.reason)

    def test_stops_charging_at_solar_target(self):
        d = decide(self.now, self.import_rates, self.export_rates, soc=60,
                   cfg=self.cfg, charge_target=58)
        self.assertNotEqual(d.action, ACTION_CHARGE)

    def test_no_target_falls_back_to_static(self):
        d = decide(self.now, self.import_rates, self.export_rates, soc=60,
                   cfg=self.cfg)
        self.assertEqual(d.action, ACTION_CHARGE)
        self.assertEqual(d.reserve, 100)


class TestBuildOutlook(unittest.TestCase):
    today = dt.date(2026, 6, 11)

    def daily(self):
        d = {}
        for n in range(15):
            date = self.today + dt.timedelta(days=n)
            d[date] = {"radiation": 20.0, "cloud": 50, "code": 2}
        d[self.today + dt.timedelta(days=14)]["radiation"] = None  # API tail
        return d

    def test_one_entry_per_day_with_predictions(self):
        days = solar.build_outlook(self.daily(), k_used=1.5, today=self.today,
                                   horizon_days=14)
        self.assertEqual(len(days), 15)
        self.assertEqual(days[0]["date"], "2026-06-11")
        self.assertEqual(days[0]["pred_kwh"], 30.0)  # 1.5 * 20
        self.assertFalse(days[0]["placeholder"])

    def test_missing_radiation_becomes_placeholder(self):
        days = solar.build_outlook(self.daily(), k_used=1.5, today=self.today,
                                   horizon_days=14)
        self.assertTrue(days[14]["placeholder"])
        self.assertIsNone(days[14]["pred_kwh"])

    def test_day_absent_from_feed_is_placeholder(self):
        days = solar.build_outlook({}, k_used=1.5, today=self.today,
                                   horizon_days=2)
        self.assertEqual(len(days), 3)
        self.assertTrue(all(d["placeholder"] for d in days))


class TestForecastLogAndAccuracy(unittest.TestCase):
    today = dt.date(2026, 6, 11)

    def setUp(self):
        import tempfile
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db = self.tmp.name

    def tearDown(self):
        import os
        os.unlink(self.db)

    def _days(self, base_date, pred=24.0):
        return [{"date": (base_date + dt.timedelta(days=n)).isoformat(),
                 "horizon_days": n, "radiation_mj_m2": 16.0,
                 "cloud_cover_pct": 40, "weather_code": 2,
                 "pred_kwh": pred, "placeholder": False} for n in range(3)]

    def test_log_is_idempotent_per_day(self):
        days = self._days(self.today)
        n1 = solar.log_outlook(self.db, days, 1.5, True, self.today)
        n2 = solar.log_outlook(self.db, days, 1.5, True, self.today)
        self.assertEqual(n1, 3)
        self.assertEqual(n2, 0)  # same forecast_date -> ignored

    def test_accuracy_placeholder_until_enough_matches(self):
        # Log 3 predictions made 2 days ago; only 2 target days have elapsed.
        made = self.today - dt.timedelta(days=2)
        solar.log_outlook(self.db, self._days(made, pred=24.0), 1.5, True, made)
        actual = {made: 20.0, made + dt.timedelta(days=1): 30.0}
        acc = solar.forecast_accuracy(self.db, actual, self.today,
                                      min_matched=7)
        self.assertFalse(acc["available"])
        self.assertEqual(acc["matched"], 2)
        self.assertEqual(acc["min_required"], 7)

    def test_accuracy_by_horizon_when_enough(self):
        # Daily snapshots, each predicting 24 for the next day; actuals 20
        # -> APE = 20% at horizon 0-1d. (i=1 targets today, which is still
        # accumulating and rightly excluded -> 7 elapsed matches.)
        for i in range(8, 1, -1):
            made = self.today - dt.timedelta(days=i)
            days = [{"date": (made + dt.timedelta(days=1)).isoformat(),
                     "horizon_days": 1, "radiation_mj_m2": 16.0,
                     "cloud_cover_pct": 40, "weather_code": 2,
                     "pred_kwh": 24.0, "placeholder": False}]
            solar.log_outlook(self.db, days, 1.5, True, made)
        actual = {self.today - dt.timedelta(days=i): 20.0 for i in range(9)}
        acc = solar.forecast_accuracy(self.db, actual, self.today,
                                      min_matched=7)
        self.assertTrue(acc["available"])
        self.assertEqual(acc["matched"], 7)
        b = {x["bucket"]: x for x in acc["by_horizon"]}
        self.assertIn("0-1d", b)
        self.assertEqual(b["0-1d"]["n"], 7)
        self.assertAlmostEqual(b["0-1d"]["median_ape_pct"], 20.0, places=1)

    def test_unmatched_days_are_skipped(self):
        made = self.today - dt.timedelta(days=1)
        solar.log_outlook(self.db, self._days(made), 1.5, True, made)
        acc = solar.forecast_accuracy(self.db, {}, self.today, min_matched=1)
        self.assertEqual(acc["matched"], 0)
        self.assertFalse(acc["available"])


if __name__ == "__main__":
    unittest.main()
