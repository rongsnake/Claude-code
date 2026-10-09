"""
The map: projection, where each city sits, and the routes trade travels.

The projection is equirectangular with the x axis scaled by cos 40°, in map
units of a tenth of a degree of latitude. It is not a projection a cartographer
would choose for the whole world; it is the one a portolan chart of the
Mediterranean resembles, keeps Europe close to true shape, and costs nothing
to compute in the browser. The coastline it is drawn with is derived once by
`tools/make_coastline.py` from Natural Earth and committed as `land.json`.

Routes are polylines through waypoints — the Adriatic and the Otranto strait,
Gibraltar, the Cape, the Malacca strait, Suez after 1869 — so that a galley
from Venice to Alexandria goes by sea and an East Indiaman from London to
Calcutta goes round Africa until the canal opens. Waypoint positions are
geography, not history; which routes exist when is HISTORICAL.
"""

from __future__ import annotations

import math

#: x-scale latitude: the parallel at which the chart is true to shape.
TRUE_LAT = 40.0
#: Map units per degree of latitude.
UNITS = 10.0
#: (lon0, lat0, lon1, lat1) of the theatre the game opens on: drawn finer.
EUROPE_BOX = (-25.0, 27.0, 45.0, 72.0)
#: The opening camera: the Mediterranean and the Channel.
OPENING_VIEW = (-11.0, 30.0, 36.0, 58.0)

_KX = math.cos(math.radians(TRUE_LAT)) * UNITS


def project(lon: float, lat: float) -> tuple[float, float]:
    """(lon, lat) in degrees → (x, y) in map units, y down."""
    return ((lon + 180.0) * _KX, (90.0 - lat) * UNITS)


def unproject(x: float, y: float) -> tuple[float, float]:
    return (x / _KX - 180.0, 90.0 - y / UNITS)


#: City positions (lon, lat). Ids match cities.py.
COORDS = {
    "venice": (12.34, 45.44), "florence": (11.25, 43.77), "genoa": (8.93, 44.41), "rome": (12.48, 41.89),
    "bruges": (3.22, 51.21), "london": (-0.09, 51.51), "avignon": (4.81, 43.95), "lyon": (4.84, 45.76),
    "antwerp": (4.40, 51.22), "augsburg": (10.90, 48.37), "seville": (-5.98, 37.39), "amsterdam": (4.90, 52.37),
    "frankfurt": (8.68, 50.11), "paris": (2.35, 48.86), "edinburgh": (-3.19, 55.95), "new_york": (-74.01, 40.71),
    "hong_kong": (114.17, 22.28), "singapore": (103.85, 1.29), "zurich": (8.54, 47.37),
    # the wider world
    "lisbon": (-9.14, 38.72), "alexandria": (29.92, 31.20), "constantinople": (28.98, 41.01),
    "goa": (73.83, 15.50), "calcutta": (88.36, 22.57), "bombay": (72.88, 19.08), "batavia": (106.81, -6.13),
    "canton": (113.26, 23.13), "buenos_aires": (-58.38, -34.60), "tokyo": (139.69, 35.69),
    "sydney": (151.21, -33.87), "dubai": (55.27, 25.20), "hamburg": (9.99, 53.55),
}

#: Named waypoints at sea. Geography, each checked by test_saga_geo to lie at
#: sea on the coastline the game draws.
WAYPOINTS = {
    # the Adriatic, Ionian and Aegean
    "adriatic": (15.2, 43.3), "otranto": (18.95, 40.2), "ionian": (19.5, 37.0), "ionian_w": (16.6, 37.6),
    "passero": (15.3, 36.45), "matapan": (22.4, 35.9), "crete_sw": (23.3, 35.0), "crete_s": (25.0, 34.55),
    "aegean": (25.3, 38.0), "lesbos_w": (25.6, 39.3), "dardanelles": (26.1, 40.0),
    # the Tyrrhenian and the western basin
    "ligurian": (8.6, 43.2), "ligurian_e": (9.8, 43.4), "tyrrhenian_n": (10.0, 42.2), "tyrrhenian": (11.5, 39.5),
    "sicily_sw": (12.0, 37.25), "sardinia_s": (9.0, 38.3), "sardinia_w": (7.6, 40.0), "sardinia_sw": (7.8, 38.6),
    "corsica_w": (7.8, 42.0), "baleares_s": (2.5, 38.6), "alboran": (-2.5, 36.2), "gibraltar": (-5.6, 35.95),
    "lion_gulf": (4.5, 42.8),
    # the Atlantic coast of Europe
    "cape_st_vincent": (-9.6, 36.8), "finisterre": (-10.0, 43.2), "ushant": (-5.6, 48.6), "dover": (1.6, 51.0),
    "north_sea": (3.5, 53.5),
    # Suez, the Red Sea and Arabia
    "port_said": (32.3, 31.6), "suez": (32.55, 29.9), "gulf_suez": (33.15, 28.6), "gubal": (34.0, 27.55),
    "red_sea_n": (35.0, 26.2), "red_sea_m": (36.8, 23.0), "red_sea": (38.6, 20.0), "red_sea_s": (41.0, 16.0),
    "bab": (43.35, 12.65), "aden": (45.0, 12.3), "gulf_aden_e": (50.0, 13.2), "socotra_n": (54.0, 13.3),
    "arabian_sea": (65.0, 15.0), "ras_hadd": (61.0, 21.5), "hormuz": (56.75, 26.55),
    # round Africa
    "canaries": (-18.5, 29.6), "cape_verde": (-21.0, 15.5), "st_helena": (-6.0, -16.0), "cape": (19.0, -36.5),
    "agulhas_e": (24.0, -35.5), "natal": (33.5, -30.5), "mozambique": (41.0, -20.0), "comoro_n": (44.0, -10.5),
    # the Indian Ocean and the straits
    "ceylon_s": (80.6, 5.3), "ceylon_e": (82.3, 6.5), "bengal": (88.0, 17.0), "kerala": (75.5, 9.0),
    "andaman_w": (91.0, 10.0), "nicobar_n": (94.5, 8.5), "andaman_s": (93.0, 6.0), "malacca_n": (97.0, 6.5),
    "malacca": (100.4, 3.0), "malacca_s": (102.2, 1.95), "piai": (103.35, 1.15), "singapore_strait": (104.2, 1.2),
    "indian_s": (70.0, -28.0), "java_s": (105.0, -9.0), "sunda": (105.75, -5.95), "indian_e": (100.0, -20.0),
    # the China seas and Japan
    "south_china_s": (106.0, 3.0), "south_china": (112.0, 12.0), "java_sea_w": (108.5, -5.0),
    "karimata": (109.0, -1.5), "natuna_w": (106.5, 3.5), "luzon_strait": (121.5, 20.8), "japan_s": (135.0, 32.0),
    "izu_s": (139.5, 34.3),
    # Australia
    "cape_leeuwin": (114.0, -36.0), "bight": (129.0, -36.5), "bass": (146.5, -39.6), "gabo": (150.5, -37.8),
    # the Atlantic crossings and South America
    "azores": (-28.0, 38.0), "mid_atlantic": (-45.0, 40.0), "newfoundland": (-52.0, 44.0),
    "brazil_ne": (-32.0, -6.0), "bahia": (-37.5, -13.5), "abrolhos": (-38.0, -19.0), "rio": (-41.5, -23.8),
    "santa_catarina": (-47.0, -28.5), "rio_plata": (-55.0, -35.5), "plata_in": (-57.0, -35.0),
}

#: Legs that run overland by canal: drawn, but exempt from the sea check.
CANAL_LEGS = {("port_said", "suez"), ("suez", "port_said")}

# reusable chains of waypoints
_CHANNEL = ["dover", "ushant", "finisterre"]
_IBERIA_IN = ["cape_st_vincent", "gibraltar", "alboran"]
_WMED_E = ["baleares_s", "sardinia_s", "sicily_sw", "passero"]
_TO_SUEZ = ["crete_sw", "crete_s", "port_said", "suez"]
_RED_SEA = ["gulf_suez", "gubal", "red_sea_n", "red_sea_m", "red_sea", "red_sea_s", "bab", "aden", "gulf_aden_e", "socotra_n"]
_SUEZ_ROUTE = _CHANNEL + _IBERIA_IN + _WMED_E + _TO_SUEZ + _RED_SEA
_CAPE = ["canaries", "cape_verde", "st_helena", "cape", "agulhas_e", "natal", "mozambique", "comoro_n"]
_MALACCA = ["malacca_n", "malacca", "malacca_s", "piai", "singapore_strait"]
_BRAZIL = ["canaries", "cape_verde", "brazil_ne", "bahia", "abrolhos", "rio", "santa_catarina", "rio_plata", "plata_in"]

#: Routes between cities. `via` is the waypoint chain; `sea` routes carry
#: ships, land routes couriers, `air` routes the wire and the jet. `from_year`
#: and `until` bound when they run: the Cape route opens in 1498, Suez in 1869.
ROUTES = [
    # the Mediterranean, from 1300
    {"a": "venice", "b": "alexandria", "via": ["adriatic", "otranto", "ionian", "matapan", "crete_sw", "crete_s"], "sea": True, "from_year": 1300},
    {"a": "venice", "b": "constantinople", "via": ["adriatic", "otranto", "ionian", "matapan", "aegean", "lesbos_w", "dardanelles"], "sea": True, "from_year": 1300},
    {"a": "genoa", "b": "constantinople", "via": ["ligurian_e", "tyrrhenian_n", "tyrrhenian", "sicily_sw", "passero", "matapan", "aegean", "lesbos_w", "dardanelles"], "sea": True, "from_year": 1300},
    {"a": "venice", "b": "genoa", "via": ["adriatic", "otranto", "ionian_w", "passero", "sicily_sw", "tyrrhenian", "tyrrhenian_n", "ligurian_e"], "sea": True, "from_year": 1300},
    {"a": "genoa", "b": "seville", "via": ["ligurian", "corsica_w", "sardinia_w", "sardinia_sw", "baleares_s", "alboran", "gibraltar"], "sea": True, "from_year": 1300},
    {"a": "venice", "b": "bruges", "via": ["adriatic", "otranto", "ionian_w", "passero", "sicily_sw", "sardinia_s", "baleares_s", "alboran", "gibraltar", "cape_st_vincent", "finisterre", "ushant", "dover"], "sea": True, "from_year": 1314},
    {"a": "genoa", "b": "london", "via": ["ligurian", "corsica_w", "sardinia_w", "sardinia_sw", "baleares_s", "alboran", "gibraltar", "cape_st_vincent", "finisterre", "ushant"], "sea": True, "from_year": 1300},
    {"a": "lisbon", "b": "london", "via": ["finisterre", "ushant"], "sea": True, "from_year": 1300},
    {"a": "genoa", "b": "alexandria", "via": ["ligurian_e", "tyrrhenian_n", "tyrrhenian", "sicily_sw", "passero", "crete_sw", "crete_s"], "sea": True, "from_year": 1300},
    {"a": "rome", "b": "avignon", "via": ["tyrrhenian_n", "ligurian_e", "lion_gulf"], "sea": True, "from_year": 1309, "until": 1380},
    # overland, from 1300
    {"a": "venice", "b": "florence", "sea": False, "from_year": 1300},
    {"a": "florence", "b": "rome", "sea": False, "from_year": 1300},
    {"a": "florence", "b": "genoa", "sea": False, "from_year": 1300},
    {"a": "venice", "b": "augsburg", "sea": False, "from_year": 1300},
    {"a": "genoa", "b": "lyon", "sea": False, "from_year": 1300},
    {"a": "lyon", "b": "avignon", "sea": False, "from_year": 1300},
    {"a": "lyon", "b": "paris", "sea": False, "from_year": 1300},
    {"a": "paris", "b": "bruges", "sea": False, "from_year": 1300},
    {"a": "bruges", "b": "london", "via": ["dover"], "sea": True, "from_year": 1300},
    {"a": "bruges", "b": "antwerp", "sea": False, "from_year": 1300},
    {"a": "antwerp", "b": "amsterdam", "sea": False, "from_year": 1300},
    {"a": "augsburg", "b": "frankfurt", "sea": False, "from_year": 1300},
    {"a": "frankfurt", "b": "antwerp", "sea": False, "from_year": 1300},
    {"a": "augsburg", "b": "zurich", "sea": False, "from_year": 1300},
    {"a": "zurich", "b": "lyon", "sea": False, "from_year": 1300},
    {"a": "seville", "b": "lisbon", "sea": False, "from_year": 1300},
    {"a": "london", "b": "edinburgh", "sea": False, "from_year": 1300},
    {"a": "amsterdam", "b": "hamburg", "sea": False, "from_year": 1300},
    {"a": "amsterdam", "b": "london", "via": ["north_sea"], "sea": True, "from_year": 1300},
    {"a": "hamburg", "b": "london", "via": ["north_sea"], "sea": True, "from_year": 1300},
    {"a": "frankfurt", "b": "hamburg", "sea": False, "from_year": 1300},
    {"a": "paris", "b": "london", "sea": False, "from_year": 1300},
    # the Carreira da Índia and the Atlantic, from 1498
    {"a": "lisbon", "b": "goa", "via": _CAPE + ["arabian_sea"], "sea": True, "from_year": 1498},
    {"a": "seville", "b": "new_york", "via": ["canaries", "mid_atlantic"], "sea": True, "from_year": 1500},
    {"a": "lisbon", "b": "buenos_aires", "via": _BRAZIL, "sea": True, "from_year": 1580},
    {"a": "goa", "b": "canton", "via": ["kerala", "ceylon_s", "andaman_s"] + _MALACCA + ["south_china_s", "south_china"], "sea": True, "from_year": 1557},
    # the companies' routes round the Cape, 1600–1869
    {"a": "amsterdam", "b": "batavia", "via": ["north_sea"] + _CHANNEL + ["canaries", "cape_verde", "st_helena", "cape", "indian_s", "java_s", "sunda"], "sea": True, "from_year": 1602, "until": 1870},
    {"a": "london", "b": "calcutta", "via": _CHANNEL + _CAPE + ["ceylon_s", "ceylon_e", "bengal"], "sea": True, "from_year": 1690, "until": 1870},
    {"a": "london", "b": "bombay", "via": _CHANNEL + _CAPE + ["arabian_sea"], "sea": True, "from_year": 1668, "until": 1870},
    {"a": "calcutta", "b": "canton", "via": ["bengal", "andaman_w", "nicobar_n"] + _MALACCA + ["south_china_s", "south_china"], "sea": True, "from_year": 1700},
    {"a": "batavia", "b": "canton", "via": ["java_sea_w", "karimata", "natuna_w", "south_china"], "sea": True, "from_year": 1620},
    {"a": "london", "b": "new_york", "via": ["dover", "ushant", "azores", "mid_atlantic", "newfoundland"], "sea": True, "from_year": 1700},
    {"a": "amsterdam", "b": "new_york", "via": ["north_sea", "dover", "ushant", "azores", "mid_atlantic"], "sea": True, "from_year": 1625},
    {"a": "london", "b": "buenos_aires", "via": _CHANNEL + _BRAZIL, "sea": True, "from_year": 1820},
    # Suez and steam, from 1869
    {"a": "london", "b": "bombay", "via": _SUEZ_ROUTE + ["arabian_sea"], "sea": True, "from_year": 1870},
    {"a": "london", "b": "calcutta", "via": _SUEZ_ROUTE + ["ceylon_s", "ceylon_e", "bengal"], "sea": True, "from_year": 1870},
    {"a": "london", "b": "hong_kong", "via": _SUEZ_ROUTE + ["ceylon_s", "andaman_s"] + _MALACCA + ["south_china_s", "south_china"], "sea": True, "from_year": 1870},
    {"a": "london", "b": "singapore", "via": _SUEZ_ROUTE + ["ceylon_s", "andaman_s", "malacca_n", "malacca", "malacca_s"], "sea": True, "from_year": 1870},
    {"a": "london", "b": "sydney", "via": _SUEZ_ROUTE + ["ceylon_s", "indian_e", "cape_leeuwin", "bight", "bass", "gabo"], "sea": True, "from_year": 1870},
    {"a": "london", "b": "dubai", "via": _SUEZ_ROUTE + ["ras_hadd", "hormuz"], "sea": True, "from_year": 1971},
    {"a": "hong_kong", "b": "singapore", "via": ["south_china", "south_china_s", "singapore_strait"], "sea": True, "from_year": 1870},
    {"a": "hong_kong", "b": "tokyo", "via": ["luzon_strait", "japan_s", "izu_s"], "sea": True, "from_year": 1870},
    # the wire and the jet: modern links are drawn as arcs, not sea lanes
    {"a": "london", "b": "new_york", "sea": False, "air": True, "from_year": 1950},
    {"a": "london", "b": "hong_kong", "sea": False, "air": True, "from_year": 1950},
    {"a": "new_york", "b": "tokyo", "sea": False, "air": True, "from_year": 1950},
    {"a": "london", "b": "singapore", "sea": False, "air": True, "from_year": 1950},
    {"a": "london", "b": "dubai", "sea": False, "air": True, "from_year": 1975},
    {"a": "london", "b": "zurich", "sea": False, "air": True, "from_year": 1950},
    {"a": "frankfurt", "b": "new_york", "sea": False, "air": True, "from_year": 1950},
    {"a": "london", "b": "sydney", "sea": False, "air": True, "from_year": 1960},
    {"a": "tokyo", "b": "sydney", "sea": False, "air": True, "from_year": 1970},
]


def route_names(route: dict) -> list[str]:
    return [route["a"], *route.get("via", []), route["b"]]


def route_points(route: dict) -> list[tuple[float, float]]:
    """The projected polyline for a route, city to city through its waypoints."""
    names = route_names(route)
    pts = []
    for n in names:
        lon, lat = COORDS.get(n) or WAYPOINTS[n]
        x, y = project(lon, lat)
        pts.append((round(x, 1), round(y, 1)))
    return pts


def projected_cities() -> dict[str, tuple[float, float]]:
    return {k: tuple(round(v, 1) for v in project(*ll)) for k, ll in COORDS.items()}


#: When each place became regularly known to European merchants: until then
#: it lies in the fog, marked only by its rumour. Europe, the Mediterranean and
#: the Levant are known from the start. HISTORICAL in the dates (Portuguese
#: arrival, or the first European account a merchant would have acted on);
#: STYLISED in treating knowledge as a single year.
KNOWN = {
    "goa": 1498, "bombay": 1498, "calcutta": 1517, "singapore": 1511, "batavia": 1512, "canton": 1514,
    "hong_kong": 1514, "tokyo": 1543, "new_york": 1524, "buenos_aires": 1516, "sydney": 1770, "dubai": 1507,
}

#: What the map calls a place before it is known: the names on medieval
#: charts and in Marco Polo for the hubs that rumour put at the edge of the
#: world. Shown faint and italic in the fog.
RUMOUR = {
    "goa": "Calicut", "calcutta": "Bengala", "canton": "Cathay", "batavia": "the Spice Islands",
    "tokyo": "Cipangu", "new_york": "Antillia", "buenos_aires": "terra incognita", "sydney": "Terra Australis",
    "dubai": "Ormus", "singapore": "Malacca",
}

#: The camera's widest frame: from the Americas to Japan and Australia.
WORLD_VIEW = (-100.0, -45.0, 160.0, 70.0)


def _box(view):
    lo0, la0, lo1, la1 = view
    x0, y1 = project(lo0, la0)
    x1, y0 = project(lo1, la1)
    return [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)]


def payload() -> dict:
    """Everything the page needs to draw the world, in map units."""
    import json
    from pathlib import Path

    land = json.loads((Path(__file__).resolve().parent / "land.json").read_text())
    return {
        "land": [p["d"] for p in land["paths"]],
        "land_source": land["source"],
        "cities": projected_cities(),
        "known": KNOWN,
        "rumour": RUMOUR,
        "routes": [
            {"a": r["a"], "b": r["b"], "sea": r["sea"], "air": r.get("air", False),
             "from": r["from_year"], "until": r.get("until", 9999), "pts": route_points(r)}
            for r in ROUTES
        ],
        "opening_view": _box(OPENING_VIEW),
        "world_view": _box(WORLD_VIEW),
        "units_per_degree": UNITS,
        "kx": round(_KX, 6),
    }
