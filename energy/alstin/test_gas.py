"""Unit tests for gas unit conversion (pure function only)."""
import unittest

import gas


class TestToKwh(unittest.TestCase):
    def test_explicit_m3_converts(self):
        kwh, src = gas.to_kwh([2.0, 3.0], "m3", 11.1)
        self.assertEqual(src, "m3")
        self.assertEqual(kwh, [22.2, 33.3])

    def test_explicit_kwh_passes_through(self):
        kwh, src = gas.to_kwh([22.2, 33.3], "kwh", 11.1)
        self.assertEqual(src, "kwh")
        self.assertEqual(kwh, [22.2, 33.3])

    def test_auto_detects_m3_from_small_magnitude(self):
        # mean 2.5 < 40 -> treated as m3 and converted.
        kwh, src = gas.to_kwh([2.0, 3.0], "auto", 11.1)
        self.assertEqual(src, "m3")
        self.assertEqual(kwh, [22.2, 33.3])

    def test_auto_detects_kwh_from_large_magnitude(self):
        # mean 55 >= 40 -> treated as kWh, no conversion.
        kwh, src = gas.to_kwh([50.0, 60.0], "auto", 11.1)
        self.assertEqual(src, "kwh")
        self.assertEqual(kwh, [50.0, 60.0])

    def test_empty(self):
        self.assertEqual(gas.to_kwh([], "auto", 11.1), ([], "auto"))


if __name__ == "__main__":
    unittest.main()
