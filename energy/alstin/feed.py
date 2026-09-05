#!/usr/bin/env python3
"""Alstin Lodge Energy Controller - main loop.

Monitoring + dry-run by default. Control only fires when config.control.enabled
is true AND config.control.dry_run is false (enforced in controller.py).

Flags:
  --once          run a single cycle and exit
  --no-powerwall  skip the Powerwall (use a fake reading)
  --no-prices     skip Octopus (use empty rate lists)
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time

import yaml

import controller
import storage
from octopus import OctopusClient
from strategy import StrategyConfig, decide, price_at

UTC = dt.timezone.utc
log = logging.getLogger("feed")

SOLAR_REFRESH_S = 6 * 3600  # forecast + calibration change slowly


class SolarTargetCache:
    """Tonight's solar-aware charge target via solar.plan(), refreshed 6-hourly.

    Degrades gracefully: any failure (network, Fleet API, no forecast) leaves
    `target` as None and decide() falls back to the static config target.
    """

    def __init__(self, cfg: dict, pw):
        self.cfg = cfg
        self.pw = pw  # PowerwallController (for the Fleet client) or None
        self.target: float | None = None
        self.info: dict = {}
        self._last = 0.0

    def maybe_refresh(self) -> None:
        if (time.monotonic() - self._last) < SOLAR_REFRESH_S and self.target is not None:
            return
        self._last = time.monotonic()
        try:
            import solar

            fleet_client = self.pw.connect().client.fleet if self.pw else None
            if fleet_client is None:
                raise ValueError("no Powerwall connection for solar history")
            self.info = solar.plan(fleet_client, self.cfg)
            self.target = float(self.info["charge_target_pct"])
            log.info(
                "Solar-aware charge target %.0f%% for %s (PV forecast %.1f kWh, "
                "k=%.3f %s over %d days)",
                self.target, self.info["for_date"], self.info["pv_forecast_kwh"],
                self.info["yield_kwh_per_mj"],
                "calibrated" if self.info["calibrated"] else "default",
                self.info["calibration_days"],
            )
        except Exception as exc:
            self.target = None
            self.info = {"error": str(exc)}
            log.warning("Solar target unavailable (%s); using static target", exc)


def load_config(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def build_strategy_cfg(cfg: dict) -> StrategyConfig:
    s = cfg.get("strategy", {}) or {}
    return StrategyConfig(
        reserve_floor=float(s.get("reserve_floor", 10)),
        reserve_charge_target=float(s.get("reserve_charge_target", 100)),
        cheap_charge_hours=float(s.get("cheap_charge_hours", 3)),
        cheap_price_threshold_p=float(s.get("cheap_price_threshold_p", 15)),
        export_price_threshold_p=float(s.get("export_price_threshold_p", 30)),
    )


class PriceCache:
    """Fetches import + export rates for now..+24h, refreshed periodically."""

    def __init__(self, client: OctopusClient, cfg: dict, refresh_s: int):
        self.client = client
        self.import_code = cfg["octopus"].get("import_tariff_code")
        self.export_code = cfg["octopus"].get("export_tariff_code")
        self.refresh_s = refresh_s
        self.import_rates: list = []
        self.export_rates: list = []
        self._last = 0.0

    def maybe_refresh(self, now: dt.datetime, force: bool = False) -> None:
        if not force and (time.monotonic() - self._last) < self.refresh_s:
            return
        period_from = now - dt.timedelta(hours=1)
        period_to = now + dt.timedelta(hours=24)
        if self.import_code:
            self.import_rates = self.client.rates_for_tariff(
                self.import_code, period_from, period_to
            )
        if self.export_code:
            self.export_rates = self.client.rates_for_tariff(
                self.export_code, period_from, period_to
            )
        self._last = time.monotonic()
        log.info(
            "Prices refreshed: %d import, %d export slots",
            len(self.import_rates),
            len(self.export_rates),
        )


def cycle(cfg, strat_cfg, prices, pw, args, solar_cache=None) -> None:
    now = dt.datetime.now(UTC)

    # --- prices ---
    if prices is not None and not args.no_prices:
        prices.maybe_refresh(now)
        import_rates, export_rates = prices.import_rates, prices.export_rates
    else:
        import_rates, export_rates = [], []

    # --- powerwall reading ---
    if pw is not None and not args.no_powerwall:
        reading = pw.read()
        soc = reading.soc
        r = reading.as_dict()
    else:
        soc = float(cfg.get("simulate", {}).get("soc", 50))
        r = {
            "soc": soc,
            "solar_w": 0.0,
            "load_w": 0.0,
            "grid_w": 0.0,
            "battery_w": 0.0,
            "grid_status": "SIMULATED" if args.no_powerwall else "UNKNOWN",
        }

    charge_target = None
    if solar_cache is not None:
        solar_cache.maybe_refresh()
        charge_target = solar_cache.target

    decision = decide(now, import_rates, export_rates, soc, strat_cfg,
                      charge_target=charge_target)
    note = controller.apply(decision, pw if not args.no_powerwall else None, cfg.get("control", {}))

    imp = price_at(import_rates, now)
    exp = price_at(export_rates, now)

    record = {
        "ts": now.isoformat(),
        "soc": r["soc"],
        "solar_w": r["solar_w"],
        "load_w": r["load_w"],
        "grid_w": r["grid_w"],
        "battery_w": r["battery_w"],
        "grid_status": r["grid_status"],
        "import_p": imp,
        "export_p": exp,
        "action": decision.action,
        "mode": decision.mode,
        "reserve": decision.reserve,
        "grid_charging": decision.grid_charging,
        "note": note,
    }
    st = cfg.get("storage", {})
    storage.append(
        st.get("db_path", "energy.db"), st.get("csv_path", "energy.csv"), record
    )

    print(
        f"{now.strftime('%H:%M:%S')} | SoC {r['soc']:5.1f}% | "
        f"solar {r['solar_w']:6.0f}W load {r['load_w']:6.0f}W grid {r['grid_w']:7.0f}W | "
        f"imp {('%.2f' % imp) if imp is not None else '  n/a':>6}p "
        f"exp {('%.2f' % exp) if exp is not None else '  n/a':>6}p | "
        f"-> {decision.action.upper()} ({decision.reason})"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Alstin Lodge Energy Controller")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    ap.add_argument("--no-powerwall", action="store_true", help="skip Powerwall")
    ap.add_argument("--no-prices", action="store_true", help="skip Octopus prices")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = load_config(args.config)
    strat_cfg = build_strategy_cfg(cfg)

    # Octopus client (key from env, never the file)
    prices = None
    if not args.no_prices:
        api_key = os.environ.get("OCTOPUS_API_KEY", "")
        if not api_key:
            log.error("OCTOPUS_API_KEY not set; rerun with --no-prices or export it")
            return 2
        base = (cfg.get("octopus", {}) or {}).get("base_url", "https://api.octopus.energy/v1")
        client = OctopusClient(api_key, base_url=base)
        refresh_s = int((cfg.get("loop", {}) or {}).get("price_refresh_seconds", 3600))
        prices = PriceCache(client, cfg, refresh_s)
        prices.maybe_refresh(dt.datetime.now(UTC), force=True)

    # Powerwall (lazy; only connect if we will use it)
    pw = None
    if not args.no_powerwall:
        from powerwall import PowerwallController

        pw = PowerwallController(cfg.get("powerwall", {}))

    interval = int((cfg.get("loop", {}) or {}).get("interval_seconds", 300))

    # Solar-aware overnight charge target (config solar.enabled, default on).
    solar_cache = None
    if (cfg.get("solar", {}) or {}).get("enabled", True) and not args.no_powerwall:
        solar_cache = SolarTargetCache(cfg, pw)

    if args.once:
        cycle(cfg, strat_cfg, prices, pw, args, solar_cache)
        return 0

    log.info("Starting loop, interval %ds (Ctrl-C to stop)", interval)
    try:
        while True:
            try:
                cycle(cfg, strat_cfg, prices, pw, args, solar_cache)
            except Exception:
                log.exception("Cycle failed; continuing")
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
