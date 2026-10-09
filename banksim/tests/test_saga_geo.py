"""
The map's geography: projection, city positions, and sea lanes that stay at sea.

The last is the one worth having. A sea route is a polyline through
waypoints; a mistyped waypoint, or a straight leg that cuts a corner, sends a
galley across the Peloponnese or an East Indiaman across Sumatra. These tests
sample every sea leg and check each sample against the coastline the game
draws — the same `land.json` — so the map can never show a ship sailing over
land without a test failing.
"""

import json
import math
import unittest
from pathlib import Path

from banksim.saga import CITIES, SOVEREIGNS
from banksim.saga.geo import (
    COORDS, ROUTES, WAYPOINTS, OPENING_VIEW, CANAL_LEGS, project, unproject, route_points, route_names, projected_cities,
)

LAND = Path(__file__).resolve().parent.parent / "saga" / "land.json"
#: Distance from a port, in map units (a tenth of a degree), within which a
#: sea lane may touch land: London is up the Thames and Seville up the
#: Guadalquivir, and a port's own coast is coarse at the map's resolution.
PORT_SLACK = 22.0
#: Sample spacing along each leg, in map units.
STEP = 3.0


def _rings():
    data = json.loads(LAND.read_text())
    rings = []
    for p in data["paths"]:
        for sub in p["d"].strip("Z").split("Z"):
            pts = []
            for tok in sub.lstrip("M").split("L"):
                x, y = tok.split()
                pts.append((float(x), float(y)))
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            rings.append((pts, (min(xs), min(ys), max(xs), max(ys))))
    return rings


def _inside(x, y, ring):
    pts, (x0, y0, x1, y1) = ring
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class ProjectionTests(unittest.TestCase):
    def test_round_trip(self):
        for lon, lat in [(12.34, 45.44), (-74.0, 40.7), (151.2, -33.9), (0, 0)]:
            x, y = project(lon, lat)
            lo, la = unproject(x, y)
            self.assertAlmostEqual(lo, lon, places=9)
            self.assertAlmostEqual(la, lat, places=9)

    def test_north_is_up_and_east_is_right(self):
        lx, ly = project(-0.09, 51.51)   # London
        vx, vy = project(12.34, 45.44)   # Venice
        self.assertGreater(vx, lx)
        self.assertGreater(vy, ly)

    def test_opening_view_contains_the_rialto_and_the_channel(self):
        lo0, la0, lo1, la1 = OPENING_VIEW
        for cid in ("venice", "london", "bruges", "genoa", "florence"):
            lon, lat = COORDS[cid]
            self.assertTrue(lo0 <= lon <= lo1 and la0 <= lat <= la1, cid)


class CoordinateTests(unittest.TestCase):
    def test_every_city_has_a_position(self):
        for c in CITIES:
            self.assertIn(c["id"], COORDS, c["id"])

    def test_every_sovereign_seat_is_a_city(self):
        ids = {c["id"] for c in CITIES}
        for sid, s in SOVEREIGNS.items():
            self.assertIn(s["seat"], ids, sid)
            for _, cid in s.get("seat_by_year", []):
                self.assertIn(cid, ids, sid)

    def test_waypoints_are_at_sea(self):
        rings = _rings()
        for k, (lon, lat) in WAYPOINTS.items():
            if k in ("suez",):  # the canal's southern end sits in the isthmus at this resolution
                continue
            x, y = project(lon, lat)
            self.assertFalse(any(_inside(x, y, r) for r in rings), f"waypoint {k} at {lon}, {lat} is on land")

    def test_positions_are_on_the_globe(self):
        for k, (lon, lat) in list(COORDS.items()) + list(WAYPOINTS.items()):
            self.assertTrue(-180 <= lon <= 180 and -60 <= lat <= 80, k)

    def test_cities_sit_on_or_near_land(self):
        # every city is a port or inland: its position is on land, or within
        # a port's slack of it (the coastline is coarse at 1:50m)
        rings = _rings()
        for cid, (x, y) in projected_cities().items():
            near = any(_inside(x + dx, y + dy, r) for r in rings
                       for dx, dy in ((0, 0), (PORT_SLACK, 0), (-PORT_SLACK, 0), (0, PORT_SLACK), (0, -PORT_SLACK)))
            self.assertTrue(near, cid)


class RouteTests(unittest.TestCase):
    def test_endpoints_and_waypoints_exist(self):
        city_ids = {c["id"] for c in CITIES}
        for r in ROUTES:
            self.assertIn(r["a"], city_ids, r)
            self.assertIn(r["b"], city_ids, r)
            for w in r.get("via", []):
                self.assertIn(w, WAYPOINTS, (r["a"], r["b"], w))

    def test_years_are_sane(self):
        for r in ROUTES:
            self.assertTrue(1300 <= r["from_year"] <= 2027, r)
            if "until" in r:
                self.assertGreater(r["until"], r["from_year"], r)

    def test_sea_lanes_stay_at_sea(self):
        rings = _rings()
        problems = []
        for r in ROUTES:
            if not r["sea"]:
                continue
            pts = route_points(r)
            names = route_names(r)
            ends = (pts[0], pts[-1])
            for k, ((x0, y0), (x1, y1)) in enumerate(zip(pts, pts[1:])):
                if (names[k], names[k + 1]) in CANAL_LEGS:
                    continue
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) / STEP))
                for i in range(n + 1):
                    t = i / n
                    x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                    if min(math.hypot(x - ex, y - ey) for ex, ey in ends) < PORT_SLACK:
                        continue
                    if any(_inside(x, y, ring) for ring in rings):
                        lon, lat = unproject(x, y)
                        problems.append(f"{r['a']}→{r['b']} crosses land at {lon:.1f}°, {lat:.1f}°")
                        break
        self.assertEqual(problems, [], "\n" + "\n".join(dict.fromkeys(problems)))

    def test_land_json_is_present_and_sourced(self):
        data = json.loads(LAND.read_text())
        self.assertGreater(len(data["paths"]), 50)
        self.assertIn("Natural Earth", data["source"])


if __name__ == "__main__":
    unittest.main()
