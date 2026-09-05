"""Market-arbitrage tally: current fixed plan vs Agile import + Agile Outgoing.

What it answers: "If I'd been on Agile (buying low / selling high on the
half-hourly wholesale market) with an app actively arbitraging my Powerwall,
how would my energy bill compare to my current Go + Outgoing plan?"

Data sources (no Octopus API key needed):
  * Prices  - Octopus public rate endpoints (current + Agile import/export).
  * Flows   - Tesla FleetAPI energy history (5-min buckets: real solar, home
              load, grid import/export), aggregated to 30-min UTC slots.

Method:
  * Baseline    = your ACTUAL grid import/export, costed on the current plan.
  * Counterfactual = re-simulate the battery doing ACTIVE ARBITRAGE on Agile
              prices, using the same real solar + house load, then cost the
              resulting grid flows on Agile import/Agile Outgoing.
  delta = baseline_net_cost - counterfactual_net_cost   (positive = Agile wins).

Caveat shown in the UI: this compares UNIT-RATE energy cost only; standing
charges differ a little between plans and are not modelled here.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import urllib.parse
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from octopus import Rate, _parse_iso

UTC = dt.timezone.utc
PRICES_BASE = "https://api.octopus.energy/v1"
SLOT_MIN = 30


# --------------------------------------------------------------------------
# Prices (public, no auth)
# --------------------------------------------------------------------------
def fetch_rates(tariff_code: str, frm: dt.datetime, to: dt.datetime,
                timeout: int = 30) -> list[Rate]:
    """Fetch half-hourly unit rates (p/kWh inc VAT) for a tariff, no auth."""
    product = _product_from_tariff(tariff_code)
    url = (f"{PRICES_BASE}/products/{product}/electricity-tariffs/"
           f"{tariff_code}/standard-unit-rates/")
    rates: list[Rate] = []
    params = {"period_from": frm.astimezone(UTC).isoformat(),
              "period_to": to.astimezone(UTC).isoformat()}
    sess = requests.Session()  # deliberately no auth: public endpoint
    next_url: Optional[str] = url
    first = True
    while next_url:
        r = sess.get(next_url, params=params if first else None, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        for row in d.get("results", []):
            rates.append(Rate(
                value_inc_vat=float(row["value_inc_vat"]),
                valid_from=_parse_iso(row["valid_from"]),
                valid_to=_parse_iso(row["valid_to"]) if row.get("valid_to") else None,
            ))
        next_url = d.get("next")
        first = False
    rates.sort(key=lambda x: x.valid_from)
    return rates


def _product_from_tariff(tariff_code: str) -> str:
    parts = tariff_code.split("-")
    return "-".join(parts[2:-1])


def price_at(rates: list[Rate], when: dt.datetime) -> Optional[float]:
    for r in rates:
        if r.covers(when):
            return r.value_inc_vat
    return None


# --------------------------------------------------------------------------
# Flows from Tesla FleetAPI energy history -> 30-min UTC slots
# --------------------------------------------------------------------------
@dataclass
class Slot:
    start: dt.datetime          # UTC slot start
    solar_kwh: float = 0.0      # PV generated
    load_kwh: float = 0.0       # home usage
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0


def _floor_slot(t: dt.datetime) -> dt.datetime:
    t = t.astimezone(UTC)
    minute = (t.minute // SLOT_MIN) * SLOT_MIN
    return t.replace(minute=minute, second=0, microsecond=0)


def fleet_energy_day(fleet, site_id: str, day: dt.date,
                     tz: str = "Europe/London") -> dict[dt.datetime, Slot]:
    """Return {slot_start_utc: Slot} for a local calendar day from Tesla history."""
    # end_date must be RFC3339 with a timezone offset, URL-encoded. period=day
    # returns ~5-min buckets up to that instant for the local calendar day.
    end_local = dt.datetime.combine(day, dt.time(23, 59, 59), tzinfo=ZoneInfo(tz))
    end_iso = urllib.parse.quote(end_local.isoformat())
    api = (f"api/1/energy_sites/{site_id}/calendar_history"
           f"?kind=energy&period=day&end_date={end_iso}")
    resp = fleet.poll(api) or {}
    series = (resp.get("response") or {}).get("time_series", []) or []
    slots: dict[dt.datetime, Slot] = {}
    for b in series:
        ts = b.get("timestamp")
        if not ts:
            continue
        try:
            t = dt.datetime.fromisoformat(ts)
        except ValueError:
            continue
        key = _floor_slot(t)
        s = slots.get(key) or Slot(start=key)
        s.solar_kwh += _wh(b.get("solar_energy_exported"))
        s.load_kwh += _wh(b.get("total_home_usage"))
        s.grid_import_kwh += _wh(b.get("grid_energy_imported"))
        s.grid_export_kwh += (
            _wh(b.get("grid_energy_exported_from_solar"))
            + _wh(b.get("grid_energy_exported_from_battery"))
            + _wh(b.get("grid_energy_exported_from_generator"))
        )
        slots[key] = s
    return slots


def _wh(v) -> float:
    try:
        return float(v) / 1000.0   # Wh -> kWh
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# Active-arbitrage battery simulation on Agile prices
# --------------------------------------------------------------------------
@dataclass
class BatteryModel:
    capacity_kwh: float = 13.5
    max_power_kw: float = 5.0
    charge_eff: float = 0.95
    discharge_eff: float = 0.95
    reserve_floor_pct: float = 10.0
    charge_below_pctile: float = 30.0
    export_above_pctile: float = 70.0
    arb_charge_hours: float = 3.0      # how many hours of cheapest slots to grid-charge in


def _pctile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    k = (len(ys) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (k - lo)


def simulate_arbitrage(slots: list[Slot], imp: list[float], exp: list[float],
                       bm: BatteryModel) -> dict:
    """Simulate the battery actively arbitraging on Agile prices (profit-gated).

    `imp`/`exp` are per-slot Agile import/export prices (p/kWh) aligned to slots.
    Perfect-foresight discipline so it never knowingly loses money:
      * Grid-charge ONLY during the cheapest `arb_charge_hours` of slots.
      * Free solar surplus always stored, then exported.
      * Outside charge slots, the battery peak-shaves (covers the house) to dodge
        pricier imports.
      * Battery energy is exported to the grid only when the export price beats
        the round-trip recharge cost (export*eff_rt >= cheapest import) AND is in
        the priciest `export_above_pctile` band.
    Returns simulated grid flows + the thresholds used.
    """
    cap = bm.capacity_kwh
    floor = cap * bm.reserve_floor_pct / 100.0
    slot_e = bm.max_power_kw * (SLOT_MIN / 60.0)   # max kWh battery throughput / slot
    ce, de = bm.charge_eff, bm.discharge_eff
    eff_rt = ce * de

    valid_imp = [p for p in imp if p is not None]
    valid_exp = [p for p in exp if p is not None]
    cheapest_imp = min(valid_imp) if valid_imp else 0.0
    export_thr = _pctile(valid_exp, bm.export_above_pctile)

    # Cheapest slots to grid-charge in (perfect foresight over the day).
    n_charge = max(1, round(bm.arb_charge_hours * 60 / SLOT_MIN))
    ranked = sorted((i for i in range(len(slots)) if imp[i] is not None),
                    key=lambda i: imp[i])
    charge_set = set(ranked[:n_charge])
    charge_thr = imp[ranked[n_charge - 1]] if ranked else 0.0

    soc = floor
    sim_import = 0.0
    sim_export = 0.0
    per_slot = []

    for i, s in enumerate(slots):
        ai = imp[i] if i < len(imp) else None
        ae = exp[i] if i < len(exp) else None
        surplus = max(0.0, s.solar_kwh - s.load_kwh)
        deficit = max(0.0, s.load_kwh - s.solar_kwh)
        g_imp = 0.0
        g_exp = 0.0
        budget = slot_e   # battery charge/discharge throughput for this slot

        # 1. Free solar surplus into the battery first.
        store = min(surplus, (cap - soc) / ce, budget)
        soc += store * ce
        surplus -= store
        budget -= store

        if i in charge_set:
            # Cheap window: grid-charge toward full, import the house's deficit too.
            g = min((cap - soc) / ce, budget)
            soc += g * ce
            g_imp += g
            g_imp += deficit            # grid->load directly (cheap now)
            g_exp += surplus            # any leftover solar
        else:
            # Peak-shave: cover the house from the battery, else import.
            avail = max(0.0, soc - floor)
            cover = min(deficit, avail * de, budget)
            soc -= cover / de
            deficit -= cover
            budget -= cover
            g_imp += deficit
            g_exp += surplus
            # Profitable export of stored energy at genuine price peaks.
            if (ae is not None and ae >= export_thr and ae * eff_rt >= cheapest_imp):
                avail = max(0.0, soc - floor)
                sell = min(avail * de, budget)
                soc -= sell / de
                g_exp += sell

        soc = min(max(soc, floor), cap)
        sim_import += g_imp
        sim_export += g_exp
        if ai is not None:
            per_slot.append({
                "t": s.start.isoformat(),
                "import_kwh": round(g_imp, 4),
                "export_kwh": round(g_exp, 4),
                "soc_kwh": round(soc, 3),
                "price_imp": ai, "price_exp": ae,
            })

    return {
        "sim_import_kwh": sim_import,
        "sim_export_kwh": sim_export,
        "per_slot": per_slot,
        "charge_thr_p": round(charge_thr, 2),
        "export_thr_p": round(export_thr, 2),
    }


# --------------------------------------------------------------------------
# Per-day tally
# --------------------------------------------------------------------------
def compute_day(fleet, site_id: str, day: dt.date, cfg: dict) -> Optional[dict]:
    """Compute the baseline-vs-Agile tally for one local day."""
    tz = cfg.get("powerwall", {}).get("timezone", "Europe/London")
    slots_map = fleet_energy_day(fleet, site_id, day, tz)
    if not slots_map:
        return None
    slots = [slots_map[k] for k in sorted(slots_map)]

    frm = slots[0].start
    to = slots[-1].start + dt.timedelta(minutes=SLOT_MIN)
    mk = cfg.get("market", {})
    cur_imp = fetch_rates(mk["current_import_tariff"], frm, to)
    cur_exp = fetch_rates(mk["current_export_tariff"], frm, to)
    ag_imp = fetch_rates(mk["agile_import_tariff"], frm, to)
    ag_exp = fetch_rates(mk["agile_export_tariff"], frm, to)

    def mid(s: Slot) -> dt.datetime:
        return s.start + dt.timedelta(minutes=SLOT_MIN // 2)

    agile_imp_series = [price_at(ag_imp, mid(s)) for s in slots]
    agile_exp_series = [price_at(ag_exp, mid(s)) for s in slots]

    # Baseline: actual flows on the current plan.
    base_imp_cost = sum(
        s.grid_import_kwh * (price_at(cur_imp, mid(s)) or 0.0) for s in slots) / 100.0
    base_exp_rev = sum(
        s.grid_export_kwh * (price_at(cur_exp, mid(s)) or 0.0) for s in slots) / 100.0
    base_net = base_imp_cost - base_exp_rev

    # Counterfactual: arbitrage on Agile with same solar+load.
    b = cfg.get("battery", {})
    bm = BatteryModel(
        capacity_kwh=b.get("capacity_kwh", 13.5),
        max_power_kw=b.get("max_power_kw", 5.0),
        charge_eff=b.get("charge_efficiency", 0.95),
        discharge_eff=b.get("discharge_efficiency", 0.95),
        reserve_floor_pct=b.get("reserve_floor_pct", 10.0),
        charge_below_pctile=b.get("charge_below_pctile", 30.0),
        export_above_pctile=b.get("export_above_pctile", 70.0),
        arb_charge_hours=b.get("arb_charge_hours", 3.0),
    )
    sim = simulate_arbitrage(slots, agile_imp_series, agile_exp_series, bm)
    cf_imp_cost = sum(
        (ps["import_kwh"]) * (ps["price_imp"] or 0.0) for ps in sim["per_slot"]) / 100.0
    cf_exp_rev = sum(
        (ps["export_kwh"]) * (ps["price_exp"] or 0.0) for ps in sim["per_slot"]) / 100.0
    cf_net = cf_imp_cost - cf_exp_rev

    return {
        "date": day.isoformat(),
        "solar_kwh": round(sum(s.solar_kwh for s in slots), 3),
        "load_kwh": round(sum(s.load_kwh for s in slots), 3),
        "actual_import_kwh": round(sum(s.grid_import_kwh for s in slots), 3),
        "actual_export_kwh": round(sum(s.grid_export_kwh for s in slots), 3),
        "baseline_import_cost": round(base_imp_cost, 4),
        "baseline_export_rev": round(base_exp_rev, 4),
        "baseline_net": round(base_net, 4),
        "agile_import_kwh": round(sim["sim_import_kwh"], 3),
        "agile_export_kwh": round(sim["sim_export_kwh"], 3),
        "counterfactual_import_cost": round(cf_imp_cost, 4),
        "counterfactual_export_rev": round(cf_exp_rev, 4),
        "counterfactual_net": round(cf_net, 4),
        "delta": round(base_net - cf_net, 4),   # +ve = Agile+arbitrage cheaper
        "charge_thr_p": sim["charge_thr_p"],
        "export_thr_p": sim["export_thr_p"],
    }


# --------------------------------------------------------------------------
# Persistence + cumulative
# --------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS market_tally (
    date TEXT PRIMARY KEY,
    solar_kwh REAL, load_kwh REAL,
    actual_import_kwh REAL, actual_export_kwh REAL,
    baseline_import_cost REAL, baseline_export_rev REAL, baseline_net REAL,
    agile_import_kwh REAL, agile_export_kwh REAL,
    counterfactual_import_cost REAL, counterfactual_export_rev REAL, counterfactual_net REAL,
    delta REAL, charge_thr_p REAL, export_thr_p REAL,
    computed_at TEXT
)
"""


def _conn(db_path: str) -> sqlite3.Connection:
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute(DDL)
    return c


def save_day(db_path: str, row: dict, computed_at: str) -> None:
    c = _conn(db_path)
    cols = [
        "date", "solar_kwh", "load_kwh", "actual_import_kwh", "actual_export_kwh",
        "baseline_import_cost", "baseline_export_rev", "baseline_net",
        "agile_import_kwh", "agile_export_kwh",
        "counterfactual_import_cost", "counterfactual_export_rev", "counterfactual_net",
        "delta", "charge_thr_p", "export_thr_p", "computed_at",
    ]
    vals = [row.get(k) for k in cols[:-1]] + [computed_at]
    ph = ",".join("?" * len(cols))
    c.execute(f"INSERT OR REPLACE INTO market_tally ({','.join(cols)}) VALUES ({ph})", vals)
    c.commit()
    c.close()


def load_days(db_path: str, limit: int = 60) -> list[dict]:
    c = _conn(db_path)
    rows = c.execute(
        "SELECT * FROM market_tally ORDER BY date DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return [dict(r) for r in reversed(rows)]


def has_day(db_path: str, day: str) -> bool:
    c = _conn(db_path)
    r = c.execute("SELECT 1 FROM market_tally WHERE date=?", (day,)).fetchone()
    c.close()
    return r is not None


def cumulative(rows: list[dict]) -> dict:
    n = len(rows)
    total = sum(r["delta"] for r in rows)
    base = sum(r["baseline_net"] for r in rows)
    cf = sum(r["counterfactual_net"] for r in rows)
    avg = total / n if n else 0.0
    return {
        "days": n,
        "total_delta": round(total, 2),
        "baseline_net_total": round(base, 2),
        "counterfactual_net_total": round(cf, 2),
        "avg_daily_delta": round(avg, 3),
        "annualised_delta": round(avg * 365, 2),
    }
