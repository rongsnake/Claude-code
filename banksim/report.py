"""
Reporting: Pillar 3-shaped tables, rendered as plain text.

The table names follow the PRA's disclosure templates so that anyone who has
read a real Pillar 3 report knows what they are looking at:

    UK KM1   key metrics (capital, RWAs, leverage, liquidity)
    UK OV1   overview of risk-weighted exposure amounts
    UK CR1   credit quality of exposures (here, the IFRS 9 stage split)
    UK LR2   leverage ratio common disclosure
    UK LIQ1  liquidity coverage ratio

Every report is prefixed with a provenance banner. The rule this project
inherits is that synthetic figures are never presented as real ones, and a
capital report is exactly the kind of artefact that gets screenshotted out of
context — so the banner is not optional and not removable by a flag.
"""

from __future__ import annotations

from .bank import Bank
from .capital import CapitalPosition, output_floor_rate
from .engine import PeriodResult, SimulationResult
from .units import AssumptionSet, Provenance, fmt_gbp_m, fmt_pct, safe_div

WIDTH = 78


def banner(bank: Bank) -> str:
    stylised = bank.assumptions.stylised_share()
    return (
        "=" * WIDTH + "\n"
        f"  {bank.name} — HYPOTHETICAL BANK, SIMULATED FIGURES\n"
        "  Not a real institution. No figure below is drawn from any firm's\n"
        "  accounts or regulatory returns. Regulatory parameters are the rules\n"
        "  as published; the balance sheet, P&L and scenarios are invented.\n"
        f"  Registered inputs: {len(bank.assumptions)}, of which "
        f"{stylised:.0%} are stylised.\n"
        + "=" * WIDTH
    )


def _row(label: str, value: str, width: int = WIDTH) -> str:
    dots = max(2, width - len(label) - len(value) - 2)
    return f"{label} {'.' * dots} {value}"


def _section(title: str) -> str:
    return f"\n{title}\n{'-' * min(len(title), WIDTH)}"


# ---------------------------------------------------------------------------
# UK KM1 — key metrics
# ---------------------------------------------------------------------------


def km1(position: CapitalPosition, period: PeriodResult | None = None) -> str:
    of = position.own_funds
    req = position.requirements
    lines = [_section(f"UK KM1 — Key metrics ({position.year})")]

    lines += [
        _row("Common Equity Tier 1 capital", fmt_gbp_m(of.cet1)),
        _row("Tier 1 capital", fmt_gbp_m(of.tier1)),
        _row("Total capital", fmt_gbp_m(of.total_capital(position.rwa.credit))),
        _row("Total risk-weighted exposure amount", fmt_gbp_m(position.total_rwa)),
        "",
        _row("CET1 ratio", fmt_pct(position.cet1_ratio)),
        _row("Tier 1 ratio", fmt_pct(position.tier1_ratio)),
        _row("Total capital ratio", fmt_pct(position.total_capital_ratio)),
        "",
        _row("Pillar 1 CET1 requirement", fmt_pct(0.045)),
        _row("Pillar 2A (CET1 portion)", fmt_pct(0.5625 * req.pillar2a)),
        _row("Capital conservation buffer", fmt_pct(0.025)),
        _row("Countercyclical capital buffer", fmt_pct(req.ccyb)),
        _row("Systemic buffer (G-SII/O-SII/SRB)", fmt_pct(req.systemic_buffer)),
        _row("  = Overall CET1 requirement", fmt_pct(req.cet1_with_buffers)),
        _row("PRA buffer (Pillar 2B, on top)", fmt_pct(req.pra_buffer)),
        _row("CET1 headroom to requirement", fmt_pct(position.cet1_headroom_pct)),
        _row("  in cash terms", fmt_gbp_m(position.cet1_headroom_gbp_m)),
        "",
        _row("Leverage ratio", fmt_pct(position.leverage_ratio)),
        _row("Leverage requirement", fmt_pct(position.leverage_requirement)),
        _row("Total exposure measure", fmt_gbp_m(position.exposure_measure.total)),
        "",
        _row("MREL resources / RWAs", fmt_pct(position.mrel_ratio)),
        _row("MREL requirement", fmt_pct(position.mrel_requirement_rwa)),
        "",
        _row("Binding constraint", position.binding_constraint),
        _row("Within combined buffer?", "YES" if position.in_buffer else "no"),
        _row("Maximum distributable amount", fmt_pct(position.max_distributable_share, 0)),
    ]
    if period is not None:
        lines += [
            "",
            _row("Liquidity coverage ratio", fmt_pct(period.lcr_ratio, 1)),
            _row("Net stable funding ratio", fmt_pct(period.nsfr_ratio, 1)),
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UK OV1 — RWA overview
# ---------------------------------------------------------------------------


def ov1(position: CapitalPosition) -> str:
    rwa = position.rwa
    floor = output_floor_rate(position.year)
    lines = [_section(f"UK OV1 — Overview of risk-weighted exposure amounts ({position.year})")]
    lines.append(f"{'Risk type':<42}{'RWA (£m)':>14}{'Capital (£m)':>16}")
    lines.append("-" * WIDTH)

    for label, value in (
        ("Credit risk", rwa.credit),
        ("Counterparty credit risk (SA-CCR)", rwa.counterparty_credit),
        ("Credit valuation adjustment (BA-CVA)", rwa.cva),
        ("Market risk (FRTB standardised)", rwa.market),
        ("Operational risk (standardised)", rwa.operational),
        ("Securitisation", rwa.securitisation),
        ("Other", rwa.other),
    ):
        if value:
            lines.append(f"{label:<42}{value:>14,.0f}{0.08 * value:>16,.0f}")

    lines.append("-" * WIDTH)
    lines.append(f"{'Total before output floor':<42}{rwa.live_total:>14,.0f}"
                 f"{0.08 * rwa.live_total:>16,.0f}")
    lines.append(f"{'Memo: all-standardised total':<42}{rwa.sa_total:>14,.0f}")
    lines.append(f"{'Output floor rate':<42}{floor:>13.1%}")
    lines.append(f"{'Floored comparator':<42}{floor * rwa.sa_total:>14,.0f}")
    lines.append(f"{'Output floor add-on':<42}{position.output_floor_impact:>14,.0f}")
    lines.append(f"{'Headroom before the floor binds':<42}"
                 f"{position.output_floor_headroom:>14,.0f}")
    lines.append("=" * WIDTH)
    lines.append(f"{'TOTAL RWAs':<42}{position.total_rwa:>14,.0f}"
                 f"{0.08 * position.total_rwa:>16,.0f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UK CR1 — credit quality
# ---------------------------------------------------------------------------


def cr1(bank: Bank, period: PeriodResult) -> str:
    """Credit quality of the lending book, as captured at the end of the year.

    The liquidity portfolio is excluded: central bank reserves and gilts carry
    no meaningful ECL and including them makes the coverage ratio meaningless.
    """
    lines = [_section(f"UK CR1 — Credit quality and IFRS 9 staging ({period.year})")]
    lines.append(f"{'Stage':<30}{'Gross (£m)':>16}{'ECL (£m)':>14}{'Coverage':>12}")
    lines.append("-" * WIDTH)
    for stage, label in ((1, "Stage 1 (12-month ECL)"),
                         (2, "Stage 2 (lifetime ECL)"),
                         (3, "Stage 3 (credit-impaired)")):
        balance = period.stage_balances.get(stage, 0.0)
        ecl = period.stage_ecl.get(stage, 0.0)
        lines.append(f"{label:<30}{balance:>16,.0f}{ecl:>14,.0f}"
                     f"{safe_div(ecl, balance):>12.2%}")
    gross = sum(period.stage_balances.values())
    total_ecl = sum(period.stage_ecl.values())
    lines.append("-" * WIDTH)
    lines.append(f"{'Total':<30}{gross:>16,.0f}{total_ecl:>14,.0f}"
                 f"{safe_div(total_ecl, gross):>12.2%}")
    lines.append("")
    lines.append(_row("Impairment charge for the year",
                      fmt_gbp_m(period.income.impairment)))
    lines.append(_row("Stage 2 share of the lending book",
                      fmt_pct(safe_div(period.stage2_balance, gross), 1)))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UK LR2 — leverage
# ---------------------------------------------------------------------------


def lr2(position: CapitalPosition) -> str:
    em = position.exposure_measure
    lines = [_section(f"UK LR2 — Leverage ratio common disclosure ({position.year})")]
    lines += [
        _row("On-balance-sheet exposures", fmt_gbp_m(em.on_balance_sheet)),
        _row("Derivative exposures (SA-CCR)", fmt_gbp_m(em.derivative_exposure)),
        _row("Securities financing transactions", fmt_gbp_m(em.sft_exposure)),
        _row("Off-balance-sheet items (post-CCF)", fmt_gbp_m(em.off_balance_sheet)),
        _row("Less: excluded central bank claims", f"({fmt_gbp_m(em.central_bank_claims_excluded)})"),
        _row("Total exposure measure", fmt_gbp_m(em.total)),
        "",
        _row("Tier 1 capital", fmt_gbp_m(position.own_funds.tier1)),
        _row("Leverage ratio", fmt_pct(position.leverage_ratio)),
        _row("Minimum requirement", fmt_pct(position.leverage_cfg.minimum)),
        _row("Additional leverage ratio buffer",
             fmt_pct(position.leverage_cfg.alrb_share * position.requirements.systemic_buffer)),
        _row("Countercyclical leverage buffer",
             fmt_pct(position.leverage_cfg.cclb_share * position.requirements.ccyb)),
        _row("General leverage buffer", fmt_pct(position.leverage_cfg.general_buffer)),
        _row("Total leverage requirement", fmt_pct(position.leverage_requirement)),
        _row("Headroom", fmt_pct(position.leverage_headroom_pct)),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Income statement and run summary
# ---------------------------------------------------------------------------


def income_statement(period: PeriodResult) -> str:
    inc = period.income
    lines = [_section(f"Income statement ({period.year})")]
    for label, value in (
        ("Net interest income", inc.net_interest_income),
        ("Markets revenue", inc.markets_revenue),
        ("Fee and advisory income", inc.fee_revenue),
        ("Other income", inc.other_income),
    ):
        lines.append(_row(label, fmt_gbp_m(value)))
    lines.append(_row("Total operating income", fmt_gbp_m(inc.total_revenue)))
    lines.append("")
    for label, value in sorted(inc.cost_detail.items()):
        if value:
            lines.append(_row(f"  {label.replace('_', ' ').capitalize()}",
                              f"({fmt_gbp_m(value)})"))
    lines.append(_row("Total operating costs", f"({fmt_gbp_m(inc.operating_costs)})"))
    lines.append(_row("Pre-provision operating profit",
                      fmt_gbp_m(inc.pre_provision_operating_profit)))
    lines.append(_row("Impairment charge", f"({fmt_gbp_m(inc.impairment)})"))
    lines.append(_row("Profit before tax", fmt_gbp_m(inc.profit_before_tax)))
    lines.append(_row("Tax (corporation tax, surcharge, levy)", f"({fmt_gbp_m(inc.tax)})"))
    lines.append(_row("Profit after tax", fmt_gbp_m(inc.profit_after_tax)))
    lines.append("")
    lines.append(_row("Cost:income ratio", fmt_pct(inc.cost_income_ratio, 1)))
    lines.append(_row("Return on tangible equity", fmt_pct(period.rote, 1)))
    lines.append(_row("Dividend", fmt_gbp_m(period.dividend)))

    lines.append(_section("Revenue by business"))
    for name, value in sorted(inc.revenue_detail.items(), key=lambda kv: -kv[1]):
        lines.append(_row(f"  {name}", fmt_gbp_m(value)))
    return "\n".join(lines)


def run_table(result: SimulationResult) -> str:
    """The five-year path — the table a stress test actually reports."""
    lines = [_section(f"Projection — scenario: {result.scenario}")]
    # The MDA column shows the payout cap once the bank is inside its combined
    # buffer, and a dash while it is above it.
    header = (f"{'Year':<6}{'Revenue':>10}{'PBT':>10}{'Impair':>9}"
              f"{'CET1%':>8}{'Lev%':>7}{'RWA':>10}{'RoTE':>8}{'MDA':>6}")
    lines.append(header)
    lines.append("-" * len(header))
    for p in result.periods:
        lines.append(
            f"{p.year:<6}"
            f"{p.income.total_revenue:>10,.0f}"
            f"{p.income.profit_before_tax:>10,.0f}"
            f"{p.income.impairment:>9,.0f}"
            f"{p.capital.cet1_ratio * 100:>8.2f}"
            f"{p.capital.leverage_ratio * 100:>7.2f}"
            f"{p.capital.total_rwa:>10,.0f}"
            f"{p.rote * 100:>8.1f}"
            f"{(f'{p.capital.max_distributable_share:.0%}' if p.capital.in_buffer else '-'):>6}"
        )
    lines.append("-" * len(header))
    lines.append(_row("Minimum CET1 ratio", fmt_pct(result.min_cet1_ratio)))
    lines.append(_row("Peak-to-trough CET1 drawdown",
                      f"{result.cet1_drawdown() * 100:.2f}pp"))
    lines.append(_row("Minimum leverage ratio", fmt_pct(result.min_leverage_ratio)))
    lines.append(_row("Cumulative impairment", fmt_gbp_m(result.cumulative_impairment)))
    lines.append(_row("Cumulative profit after tax",
                      fmt_gbp_m(result.cumulative_profit_after_tax)))

    notes = [n for p in result.periods for n in p.notes]
    if notes:
        lines.append(_section("Notes"))
        seen = set()
        for n in notes:
            key = n.split(":")[0]
            if key not in seen:
                lines.append(f"  * {n}")
                seen.add(key)
    return "\n".join(lines)


def assumptions_appendix(assumptions: AssumptionSet) -> str:
    lines = [_section("Appendix — inputs and their provenance")]
    for p in Provenance:
        items = assumptions.by_provenance(p)
        if not items:
            continue
        lines.append(f"\n  {p.value.upper()}")
        for a in items:
            lines.append(f"    - {a.describe()}")
            if a.note:
                lines.append(f"      {a.note}")
    return "\n".join(lines)
