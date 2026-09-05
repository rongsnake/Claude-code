#!/usr/bin/env python3
"""Discover Octopus account details and prices, optionally writing config.yaml.

Reads OCTOPUS_API_KEY from the environment. Prints meter points, the current
import (Go) and export (Outgoing) tariff codes, the inferred region, and the
next 24h of unit rates. With --write, fills those into config.yaml.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import yaml

from octopus import OctopusClient, parse_tariff_code

UTC = dt.timezone.utc


def _classify(meter_points):
    """Return (import_mp, export_mp) best guesses from the meter points."""
    imp = exp = None
    for mp in meter_points:
        if mp.is_export:
            exp = exp or mp
        else:
            imp = imp or mp
    return imp, exp


def _print_rates(client, label, tariff_code, now):
    if not tariff_code:
        print(f"  {label}: (no tariff code)")
        return
    rates = client.rates_for_tariff(tariff_code, now, now + dt.timedelta(hours=24))
    print(f"  {label} ({tariff_code}) - next 24h, {len(rates)} slots:")
    for r in rates:
        vt = r.valid_to.strftime("%H:%M") if r.valid_to else "----"
        print(
            f"    {r.valid_from.strftime('%a %H:%M')}-{vt}  "
            f"{r.value_inc_vat:6.2f} p/kWh"
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Octopus account/price discovery")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--account", help="override account number")
    ap.add_argument("--write", action="store_true", help="write findings to config.yaml")
    args = ap.parse_args(argv)

    api_key = os.environ.get("OCTOPUS_API_KEY", "")
    if not api_key:
        print("ERROR: OCTOPUS_API_KEY is not set in the environment.", file=sys.stderr)
        return 2

    # account number from arg, then config
    cfg = {}
    if os.path.exists(args.config):
        with open(args.config) as fh:
            cfg = yaml.safe_load(fh) or {}
    account = args.account or (cfg.get("octopus", {}) or {}).get("account_number")
    if not account:
        print("ERROR: no account number (pass --account or set it in config).", file=sys.stderr)
        return 2

    base = (cfg.get("octopus", {}) or {}).get("base_url", "https://api.octopus.energy/v1")
    client = OctopusClient(api_key, base_url=base)
    now = dt.datetime.now(UTC)

    print(f"Account: {account}")
    meter_points = client.account_meter_points(account)
    if not meter_points:
        print("  No electricity meter points found.")
        return 1

    for mp in meter_points:
        kind = "EXPORT" if mp.is_export else "IMPORT"
        print(f"  [{kind}] MPAN {mp.mpan}  serial {mp.serial}  tariff {mp.tariff_code}")

    imp_mp, exp_mp = _classify(meter_points)
    import_code = imp_mp.tariff_code if imp_mp else None
    export_code = exp_mp.tariff_code if exp_mp else None

    region = None
    for code in (import_code, export_code):
        if code:
            try:
                region = parse_tariff_code(code)[1]
                break
            except ValueError:
                pass
    print(f"\nInferred region: {region}")

    print("\nPrices:")
    _print_rates(client, "Import", import_code, now)
    _print_rates(client, "Export", export_code, now)

    if args.write:
        cfg.setdefault("octopus", {})
        cfg["octopus"]["account_number"] = account
        cfg["octopus"]["base_url"] = base
        cfg["octopus"]["region"] = region
        cfg["octopus"]["import_tariff_code"] = import_code
        cfg["octopus"]["export_tariff_code"] = export_code
        if imp_mp:
            cfg["octopus"]["import_mpan"] = imp_mp.mpan
            cfg["octopus"]["meter_serial"] = imp_mp.serial
        if exp_mp:
            cfg["octopus"]["export_mpan"] = exp_mp.mpan
        with open(args.config, "w") as fh:
            yaml.safe_dump(cfg, fh, sort_keys=False)
        print(f"\nWrote Octopus details into {args.config}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
