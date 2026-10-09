"""
Build the static Kingsgate simulator page.

Mirrors the pattern the CDS side of this repo uses: run everything offline in
Python, bake the results into a single self-contained HTML file, and let the
page be pure presentation. No server, no build step, no dependencies — it opens
from the filesystem and it deploys by copying one file.

The split between what is pre-computed and what the page recomputes is the
design decision worth understanding:

  * **Pre-computed here** — anything that needs the risk engines or that
    compounds through time: RWAs by risk type on both bases, the P&L, ECL and
    staging, the exposure measure, liquidity ratios. These are run across a grid
    of scenario x unrated-corporate approach x dividend policy, because each
    combination changes the projection path and cannot be recovered by
    arithmetic afterwards.
  * **Recomputed live in the page** — the capital requirement stack and
    everything that follows from it: Pillar 2A, the buffers, the MDA test, the
    leverage requirement under either regime, MREL, and which constraint binds.
    That arithmetic is simple, and making it live is what turns a report into a
    simulator: move Pillar 2A and watch the ladder move under the ratio.

    python banksim/build_dashboard.py
"""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

from .bank import build_bank
from .capital import output_floor_rate
from .credit_risk import SAConfig
from .engine import compute_capital_position, run_simulation
from .scenario import standard_scenarios
from .units import Provenance

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "dashboard_template.html"
#: Standalone page — carries its own doctype and charset, opens from the
#: filesystem and deploys by copying one file.
OUT_HTML = HERE / "dashboard.html"
#: The same page as a bare fragment, for publishing as an Artifact: that
#: platform supplies its own document skeleton, so a second one would nest.
OUT_FRAGMENT = HERE / "dashboard_artifact.html"
OUT_JSON = HERE / "data" / "simulation.json"

STANDALONE_HEAD = (
    "<!doctype html>\n<html lang=\"en\">\n<head>\n"
    "<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,"
    "viewport-fit=cover\">\n</head>\n<body>\n"
)
STANDALONE_TAIL = "\n</body>\n</html>\n"

#: Dividend policies offered on the page. Payout is pre-computed rather than
#: applied live because retained earnings compound: a lower payout in year one
#: changes the capital base every year after it.
PAYOUT_STEPS = [0.00, 0.25, 0.40, 0.65, 1.00]

UNRATED_APPROACHES = ["risk_sensitive", "flat_100"]

START_YEAR = 2027
YEARS = 5

SCENARIO_BLURB = {
    "baseline": "Trend growth, Bank Rate easing towards neutral.",
    "upside": "Stronger growth, firmer asset prices, tighter spreads.",
    "stagflation": "Inflation persists: rates stay high, growth stalls.",
    "acs_severe": "Severe stress shaped like a Bank of England annual cyclical scenario.",
}


def _period_record(p) -> dict:
    """Flatten one simulated year into the numbers the page needs."""
    cap = p.capital
    rwa = cap.rwa
    inc = p.income
    return {
        "year": p.year,
        # --- P&L ---
        "nii": inc.net_interest_income,
        "markets": inc.markets_revenue,
        "fees": inc.fee_revenue,
        "other": inc.other_income,
        "revenue": inc.total_revenue,
        "costs": inc.operating_costs,
        "ppop": inc.pre_provision_operating_profit,
        "impairment": inc.impairment,
        "pbt": inc.profit_before_tax,
        "tax": inc.tax,
        "pat": inc.profit_after_tax,
        "cost_income": inc.cost_income_ratio,
        "rote": p.rote,
        "dividend": p.dividend,
        "revenue_detail": {k: round(v, 1) for k, v in inc.revenue_detail.items()},
        # --- capital ---
        "cet1": cap.own_funds.cet1,
        "at1": cap.own_funds.at1,
        "tier2": cap.own_funds.tier2(rwa.credit),
        "mrel_resources": cap.mrel_resources,
        # --- RWAs ---
        "rwa": {
            "credit": rwa.credit,
            "counterparty": rwa.counterparty_credit,
            "cva": rwa.cva,
            "market": rwa.market,
            "operational": rwa.operational,
        },
        "rwa_live": rwa.live_total,
        "rwa_sa": rwa.sa_total,
        "rwa_total": cap.total_rwa,
        "floor_rate": output_floor_rate(p.year),
        "floor_addon": cap.output_floor_impact,
        "floor_headroom": cap.output_floor_headroom,
        # --- leverage ---
        "exposure_measure": cap.exposure_measure.total,
        "exposure_detail": {
            "on_balance_sheet": cap.exposure_measure.on_balance_sheet,
            "derivatives": cap.exposure_measure.derivative_exposure,
            "sft": cap.exposure_measure.sft_exposure,
            "off_balance_sheet": cap.exposure_measure.off_balance_sheet,
            "central_bank_excluded": cap.exposure_measure.central_bank_claims_excluded,
        },
        # --- liquidity and credit quality ---
        "lcr": p.lcr_ratio,
        "nsfr": p.nsfr_ratio,
        "ecl": sum(p.stage_ecl.values()),
        "stage_balances": {str(k): v for k, v in sorted(p.stage_balances.items())},
        "stage_ecl": {str(k): v for k, v in sorted(p.stage_ecl.items())},
        # --- macro, so the page can show what drove the year ---
        "macro": {
            "gdp_growth": p.macro.gdp_growth,
            "unemployment": p.macro.unemployment,
            "bank_rate": p.macro.bank_rate,
            "hpi_growth": p.macro.hpi_growth,
            "equity_return": p.macro.equity_return,
            "volatility_index": p.macro.volatility_index,
            "activity_index": p.macro.activity_index,
        },
    }


def build_payload() -> dict:
    """Run the grid and collect everything the page needs."""
    template_bank = build_bank()
    scenarios = standard_scenarios(START_YEAR, YEARS)

    opening = compute_capital_position(build_bank(), START_YEAR)
    runs: dict[str, list[dict]] = {}

    for approach in UNRATED_APPROACHES:
        for payout in PAYOUT_STEPS:
            for name, scenario in scenarios.items():
                bank = copy.deepcopy(template_bank)
                bank.sa_cfg = SAConfig(unrated_corporate_approach=approach)
                bank.target_payout_ratio = payout
                result = run_simulation(
                    bank, scenario, scenarios,
                    start_year=START_YEAR, years=YEARS,
                )
                key = f"{name}|{approach}|{payout:.2f}"
                runs[key] = [_period_record(p) for p in result.periods]

    req = template_bank.requirements
    stylised = [a.name for a in template_bank.assumptions.by_provenance(Provenance.STYLISED)]

    return {
        "bank": template_bank.name,
        "generated": date.today().isoformat(),
        "start_year": START_YEAR,
        "years": YEARS,
        "payouts": PAYOUT_STEPS,
        "approaches": UNRATED_APPROACHES,
        "scenarios": {
            name: {"label": name.replace("_", " "), "blurb": SCENARIO_BLURB.get(name, "")}
            for name in scenarios
        },
        "opening": {
            "cet1": opening.own_funds.cet1,
            "rwa_total": opening.total_rwa,
            "cet1_ratio": opening.cet1_ratio,
            "leverage_ratio": opening.leverage_ratio,
            "exposure_measure": opening.exposure_measure.total,
        },
        "requirements": {
            "pillar2a_gross": req.pillar2a_gross,
            "sme_lending_adjustment": req.sme_lending_adjustment,
            "infrastructure_lending_adjustment": req.infrastructure_lending_adjustment,
            "ccyb": req.ccyb,
            "systemic_buffer": req.systemic_buffer,
            "pra_buffer": req.pra_buffer,
        },
        "provenance": {
            "registered": len(template_bank.assumptions),
            "stylised_share": template_bank.assumptions.stylised_share(),
            "stylised_names": stylised,
        },
        "runs": runs,
    }


def main() -> None:
    payload = build_payload()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, separators=(",", ":"), default=float))

    template = TEMPLATE.read_text()
    compact = json.dumps(payload, separators=(",", ":"), default=float)
    fragment = template.replace("/*__BANKSIM_DATA__*/null", compact)

    OUT_FRAGMENT.write_text(fragment, encoding="utf-8")
    OUT_HTML.write_text(STANDALONE_HEAD + fragment + STANDALONE_TAIL, encoding="utf-8")

    print(f"wrote {OUT_JSON} ({len(payload['runs'])} runs)")
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:,.0f} KB, standalone)")
    print(f"wrote {OUT_FRAGMENT} ({OUT_FRAGMENT.stat().st_size / 1024:,.0f} KB, artifact)")


if __name__ == "__main__":
    main()
