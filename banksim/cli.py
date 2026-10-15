"""
Command-line entry point.

    python -m banksim.cli snapshot                 # capital position today
    python -m banksim.cli run --scenario baseline  # five-year projection
    python -m banksim.cli stress                   # every scenario, compared
    python -m banksim.cli stress --json out.json   # machine-readable output

The `stress` command is the interesting one: it runs the same opening balance
sheet through every scenario and reports the CET1 drawdown, which is how a
supervisor reads a stress test.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from .bank import build_bank
from .engine import GrowthPolicy, compute_capital_position, run_simulation
from .report import (
    assumptions_appendix,
    banner,
    cr1,
    income_statement,
    km1,
    lr2,
    ov1,
    run_table,
)
from .scenario import standard_scenarios


def cmd_snapshot(args: argparse.Namespace) -> int:
    bank = build_bank()
    position = compute_capital_position(bank, args.year)
    print(banner(bank))
    print(km1(position))
    print(ov1(position))
    print(lr2(position))
    if args.assumptions:
        print(assumptions_appendix(bank.assumptions))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    bank = build_bank()
    scenarios = standard_scenarios(args.year, args.years)
    if args.scenario not in scenarios:
        print(f"unknown scenario {args.scenario!r}; "
              f"choose from {', '.join(scenarios)}", file=sys.stderr)
        return 2

    result = run_simulation(
        bank, scenarios[args.scenario], scenarios,
        start_year=args.year, years=args.years, growth=GrowthPolicy(),
    )

    print(banner(bank))
    print(run_table(result))
    if args.detail:
        for p in result.periods:
            print(income_statement(p))
            print(km1(p.capital, p))
            print(ov1(p.capital))
            print(cr1(bank, p))
    if args.assumptions:
        print(assumptions_appendix(bank.assumptions))
    if args.json:
        _write_json(args.json, {result.scenario: [p.summary() for p in result.periods]})
    return 0


def cmd_stress(args: argparse.Namespace) -> int:
    template = build_bank()
    scenarios = standard_scenarios(args.year, args.years)

    print(banner(template))
    payload: dict[str, list[dict]] = {}
    summary_rows = []

    for name, sc in scenarios.items():
        # Each scenario starts from the same opening balance sheet.
        bank = copy.deepcopy(template)
        result = run_simulation(
            bank, sc, scenarios, start_year=args.year, years=args.years
        )
        payload[name] = [p.summary() for p in result.periods]
        summary_rows.append((name, result))
        print(run_table(result))

    print("\nStress test comparison")
    print("-" * 78)
    header = (f"{'Scenario':<16}{'Min CET1':>10}{'Drawdown':>11}{'Min lev':>9}"
              f"{'Cum impair':>12}{'Cum PAT':>10}{'Buffer':>8}")
    print(header)
    print("-" * len(header))
    for name, result in summary_rows:
        in_buffer = any(p.capital.in_buffer for p in result.periods)
        print(f"{name:<16}"
              f"{result.min_cet1_ratio * 100:>9.2f}%"
              f"{result.cet1_drawdown() * 100:>10.2f}pp"
              f"{result.min_leverage_ratio * 100:>8.2f}%"
              f"{result.cumulative_impairment:>12,.0f}"
              f"{result.cumulative_profit_after_tax:>10,.0f}"
              f"{'USED' if in_buffer else '-':>8}")

    if args.assumptions:
        print(assumptions_appendix(template.assumptions))
    if args.json:
        _write_json(args.json, payload)
    return 0


def _write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nwrote {out}")


def main(argv: list[str] | None = None) -> int:
    # Shared options live on a parent parser so they are accepted either side
    # of the subcommand — `banksim --json x run` and `banksim run --json x`
    # both work, which is what anyone would expect from a CLI.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--year", type=int, default=2027,
                        help="first projected year (Basel 3.1 applies from 2027)")
    common.add_argument("--years", type=int, default=5, help="projection length")
    common.add_argument("--assumptions", action="store_true",
                        help="print the provenance appendix")
    common.add_argument("--json", help="also write results to this JSON file")

    parser = argparse.ArgumentParser(
        prog="banksim", parents=[common],
        description="Simulate a hypothetical UK wholesale bank end to end.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", parents=[common],
                            help="capital position on the opening book")
    p_snap.set_defaults(func=cmd_snapshot)

    p_run = sub.add_parser("run", parents=[common], help="project one scenario")
    p_run.add_argument("--scenario", default="baseline")
    p_run.add_argument("--detail", action="store_true",
                       help="print full statements for every year")
    p_run.set_defaults(func=cmd_run)

    p_stress = sub.add_parser("stress", parents=[common],
                              help="run every scenario and compare")
    p_stress.set_defaults(func=cmd_stress)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
