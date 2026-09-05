"""Unit tests for the pure decision logic. Run: python3 -m pytest test_strategy.py
or simply: python3 test_strategy.py
"""
import datetime as dt
import unittest

from octopus import Rate
from strategy import (
    ACTION_CHARGE,
    ACTION_DISCHARGE,
    ACTION_EXPORT,
    ACTION_SELF_USE,
    MODE_AUTONOMOUS,
    MODE_SELF,
    StrategyConfig,
    cheapest_slots,
    decide,
    price_at,
)

UTC = dt.timezone.utc


def slot(value, start_h, end_h, day=1):
    """Half/whole-hour rate slot on 2026-01-`day` at the given UTC hours."""
    vf = dt.datetime(2026, 1, day, start_h, 0, tzinfo=UTC)
    vt = vf + dt.timedelta(hours=(end_h - start_h))
    return Rate(value_inc_vat=value, valid_from=vf, valid_to=vt)


def go_import_day():
    """Octopus Go-like day: cheap 00:00-05:00 (8p), pricey 05:00-24:00 (30p)."""
    rates = []
    for h in range(0, 5):
        rates.append(slot(8.0, h, h + 1))
    for h in range(5, 24):
        rates.append(slot(30.0, h, h + 1))
    return rates


def flat_export(value=15.0):
    return [slot(value, h, h + 1) for h in range(0, 24)]


CFG = StrategyConfig(
    reserve_floor=10,
    reserve_charge_target=100,
    cheap_charge_hours=3,
    cheap_price_threshold_p=15,
    export_price_threshold_p=30,
)


class TestHelpers(unittest.TestCase):
    def test_price_at(self):
        rates = go_import_day()
        self.assertEqual(price_at(rates, dt.datetime(2026, 1, 1, 2, 30, tzinfo=UTC)), 8.0)
        self.assertEqual(price_at(rates, dt.datetime(2026, 1, 1, 18, 0, tzinfo=UTC)), 30.0)
        self.assertIsNone(price_at(rates, dt.datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))

    def test_cheapest_slots_covers_hours(self):
        chosen = cheapest_slots(go_import_day(), 3)
        self.assertEqual(len(chosen), 3)  # three 1h cheap slots
        self.assertTrue(all(r.value_inc_vat == 8.0 for r in chosen))


class TestRules(unittest.TestCase):
    def test_rule1_charge_in_cheap_window(self):
        now = dt.datetime(2026, 1, 1, 2, 30, tzinfo=UTC)  # cheap window, 8p
        d = decide(now, go_import_day(), flat_export(15), soc=40, cfg=CFG)
        self.assertEqual(d.action, ACTION_CHARGE)
        self.assertEqual(d.mode, MODE_AUTONOMOUS)
        self.assertEqual(d.reserve, 100)
        self.assertTrue(d.grid_charging)

    def test_rule1_skipped_when_already_full(self):
        now = dt.datetime(2026, 1, 1, 2, 30, tzinfo=UTC)
        d = decide(now, go_import_day(), flat_export(15), soc=100, cfg=CFG)
        self.assertNotEqual(d.action, ACTION_CHARGE)  # SoC == target -> no charge

    def test_rule2_export_when_pays_well(self):
        now = dt.datetime(2026, 1, 1, 12, 0, tzinfo=UTC)  # mid-day
        # Import is 30p (not <= 15, not cheapest window), export 35p >= 30 threshold.
        d = decide(now, go_import_day(), flat_export(35), soc=80, cfg=CFG)
        self.assertEqual(d.action, ACTION_EXPORT)
        self.assertEqual(d.reserve, 10)
        self.assertFalse(d.grid_charging)

    def test_rule3_discharge_at_peak_import(self):
        now = dt.datetime(2026, 1, 1, 18, 0, tzinfo=UTC)  # 30p import
        d = decide(now, go_import_day(), flat_export(15), soc=80, cfg=CFG)
        self.assertEqual(d.action, ACTION_DISCHARGE)
        self.assertEqual(d.mode, MODE_SELF)
        self.assertEqual(d.reserve, 10)

    def test_rule3_no_discharge_below_floor(self):
        now = dt.datetime(2026, 1, 1, 18, 0, tzinfo=UTC)
        d = decide(now, go_import_day(), flat_export(15), soc=10, cfg=CFG)
        self.assertEqual(d.action, ACTION_SELF_USE)  # at floor -> just self-use

    def test_rule4_self_use_default(self):
        # Import 14p (<= threshold) but outside the 3h cheapest window; low export.
        now = dt.datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        rates = go_import_day_with_noon_outside()
        d = decide(now, rates, flat_export(15), soc=50, cfg=CFG)
        self.assertEqual(d.action, ACTION_SELF_USE)
        self.assertEqual(d.mode, MODE_SELF)

    def test_priority_charge_beats_export(self):
        # In cheap window AND export pays well -> charge wins (rule 1 first).
        now = dt.datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
        d = decide(now, go_import_day(), flat_export(40), soc=50, cfg=CFG)
        self.assertEqual(d.action, ACTION_CHARGE)


def go_import_day_with_noon_outside():
    """Cheap 00:00-03:00 (8p), then 14p elsewhere (<=15 but not cheapest window)."""
    rates = []
    for h in range(0, 3):
        rates.append(slot(8.0, h, h + 1))
    for h in range(3, 24):
        rates.append(slot(14.0, h, h + 1))
    return rates


if __name__ == "__main__":
    unittest.main(verbosity=2)
