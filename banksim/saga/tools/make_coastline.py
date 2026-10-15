"""
Derive the game map's coastline from Natural Earth.

One-off tool, run by hand when the map needs regenerating; the build reads its
output (`banksim/saga/land.json`) and never touches the source. Stdlib only.

    npm pack world-atlas@2            # Natural Earth 4.1.0 as TopoJSON (public domain data, ISC packaging)
    tar -xzf world-atlas-2.0.2.tgz -C somewhere/
    python -I -m banksim.saga.tools.make_coastline somewhere/package/land-50m.json

What it does:

  1. Decodes the TopoJSON `land` object (quantised, delta-encoded arcs).
  2. Projects with the game's projection (`geo.project`): equirectangular with
     the x axis scaled by cos 40°, which keeps Europe and the Mediterranean
     close to true shape at the latitudes the game starts in.
  3. Simplifies each ring with Douglas–Peucker, finer inside the European
     theatre than outside it, and drops islands too small to matter at the
     zoom they will be seen at — keeping the Mediterranean's.
  4. Writes the rings as compact SVG path data in map units, rounded to 0.1.

Provenance: Natural Earth, public domain (naturalearthdata.com), via
world-atlas 2.0.2 (Mike Bostock, ISC).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from banksim.saga.geo import project, EUROPE_BOX

OUT = Path(__file__).resolve().parent.parent / "land.json"


def decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring_coords(ring: list[int], arcs) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in ring:
        a = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
        out.extend(a if not out else a[1:])
    return out


def polygons(topo: dict):
    arcs = decode_arcs(topo)
    obj = topo["objects"]["land"]
    geoms = obj["geometries"] if obj["type"] == "GeometryCollection" else [obj]
    for g in geoms:
        if g["type"] == "Polygon":
            yield [ring_coords(r, arcs) for r in g["arcs"]]
        elif g["type"] == "MultiPolygon":
            for p in g["arcs"]:
                yield [ring_coords(r, arcs) for r in p]


def dp(points, tol):
    """Douglas–Peucker, iterative."""
    if len(points) < 4:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring, tol):
    """A closed ring starts and ends on one point, which gives Douglas–Peucker
    a zero-length baseline; split at the vertex farthest from the start and
    simplify each half."""
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 4:
        return ring + ring[:1]
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    a = dp(ring[: far + 1], tol)
    b = dp(ring[far:] + ring[:1], tol)
    return a[:-1] + b


#: Douglas–Peucker tolerance in map units: ≈0.08° inside the European theatre, ≈0.25° outside.
TOL_EU, TOL_WORLD = 0.8, 2.5


def simplify_by_region(lonlat, proj):
    """Simplify a ring with a tolerance that depends on where each stretch of
    coast lies, so Eurasia's European coast is drawn finely and its Siberian
    one coarsely. The ring is cut into runs of consecutive vertices inside or
    outside the European box; each run is simplified with its own tolerance,
    keeping its end vertices so the runs still join."""
    n = len(proj) - (1 if proj[0] == proj[-1] else 0)
    if n < 4:
        return proj
    flags = [in_europe(*lonlat[i]) for i in range(n)]
    if all(flags) or not any(flags):
        return simplify_ring(proj, TOL_EU if flags[0] else TOL_WORLD)
    # rotate so the ring starts at a region boundary
    start = next(i for i in range(n) if flags[i] != flags[i - 1])
    order = list(range(start, n)) + list(range(0, start))
    out, run = [], [order[0]]
    for i in order[1:] + [order[0]]:
        if flags[i] == flags[run[0]] and i != order[0]:
            run.append(i)
            continue
        pts = [proj[j] for j in run] + [proj[i]]
        simp = dp(pts, TOL_EU if flags[run[0]] else TOL_WORLD)
        out.extend(simp[:-1])
        run = [i]
    return out + out[:1]


def area(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def in_europe(lon, lat):
    lo0, la0, lo1, la1 = EUROPE_BOX
    return lo0 <= lon <= lo1 and la0 <= lat <= la1


def main(src: str) -> None:
    topo = json.loads(Path(src).read_text())
    paths = []
    kept = dropped = 0
    for poly in polygons(topo):
        outer = poly[0]
        # skip Antarctica and the high Arctic: the game never goes there
        if max(lat for _, lat in outer) < -55 or min(lat for _, lat in outer) > 78:
            dropped += 1
            continue
        cx = sum(lon for lon, _ in outer) / len(outer)
        cy = sum(lat for _, lat in outer) / len(outer)
        eu = in_europe(cx, cy)
        # a ring that crosses the antimeridian (Chukotka) would draw a stripe
        # across the whole map when it jumps from +180° to −180°; unwrap it
        # eastward so the jump never happens — the tail runs off the right edge
        if max(lon for lon, _ in outer) > 170 and min(lon for lon, _ in outer) < -170:
            outer = [(lon + 360 if lon < -150 else lon, lat) for lon, lat in outer]
        proj = [project(lon, max(-60.0, min(80.0, lat))) for lon, lat in outer]
        a = area(proj)
        if a < (6.0 if eu else 60.0):  # map units²: ~0.25 sq° in Europe, ~2.5 elsewhere
            dropped += 1
            continue
        ring = simplify_by_region(outer, proj)
        if len(ring) < 4:
            dropped += 1
            continue
        d = "M" + "L".join(f"{x:.1f} {y:.1f}".replace(".0 ", " ").replace(".0L", "L") for x, y in ring[:-1]) + "Z"
        paths.append({"d": d, "eu": eu})
        kept += 1
    OUT.write_text(json.dumps({
        "source": "Natural Earth 1:50m land, public domain, via world-atlas 2.0.2 (ISC)",
        "projection": "equirectangular, x scaled by cos 40°, 10 map units per degree of latitude",
        "paths": paths,
    }, separators=(",", ":")))
    size = OUT.stat().st_size
    print(f"kept {kept} rings, dropped {dropped}; wrote {OUT.name} ({size/1024:.0f} KiB)")


if __name__ == "__main__":
    main(sys.argv[1])
