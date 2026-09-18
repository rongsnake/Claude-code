"""
Liquidity: the liquidity coverage ratio and the net stable funding ratio.

LCR asks whether the bank survives a 30-day stress; NSFR asks whether its
funding is structurally matched to the life of its assets. A wholesale bank
usually finds LCR easy and NSFR hard, because trading inventory and
prime-brokerage assets carry heavy required stable funding while repo funding
provides almost none.

    LCR  = stock of HQLA / net cash outflows over 30 calendar days
    NSFR = available stable funding / required stable funding

Both must be at least 100%.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exposures import Commitment, CreditExposure, Funding, FundingType
from .units import safe_div

# ---------------------------------------------------------------------------
# LCR
# ---------------------------------------------------------------------------

#: Haircuts applied to the HQLA stock by level.
HQLA_HAIRCUT = {"L1": 0.00, "L1_COVERED": 0.07, "L2A": 0.15, "L2B": 0.50}

#: Level 2 assets may not exceed 40% of the HQLA stock, and Level 2B may not
#: exceed 15%. Expressed as caps relative to the lower levels, which is how the
#: adjusted-stock calculation actually works.
L2_CAP_OF_L1 = 2.0 / 3.0           # L2 total <= 40% of HQLA  <=>  <= 2/3 of L1
L2B_CAP_OF_L1_L2A = 15.0 / 85.0    # L2B <= 15% of HQLA

#: 30-day run-off rates by funding type.
OUTFLOW_RATE = {
    FundingType.RETAIL_STABLE: 0.05,
    FundingType.RETAIL_LESS_STABLE: 0.10,
    FundingType.OPERATIONAL_DEPOSIT: 0.25,
    FundingType.CORPORATE_NON_OPERATIONAL: 0.40,
    FundingType.FINANCIAL_DEPOSIT: 1.00,
    FundingType.SENIOR_UNSECURED: 1.00,
    FundingType.SENIOR_NON_PREFERRED: 1.00,
    FundingType.COVERED_BOND_ISSUED: 1.00,
    FundingType.TIER2: 1.00,
    FundingType.AT1: 1.00,
    FundingType.CENTRAL_BANK_FACILITY: 0.00,
}

#: Secured funding run-off depends on the collateral pledged: repo against
#: gilts rolls, repo against equities does not.
SECURED_OUTFLOW_BY_COLLATERAL = {"L1": 0.00, "L2A": 0.15, "L2B": 0.50, None: 1.00}

#: Undrawn facilities we have granted. The liquidity-line rates are the ones
#: that hurt: a committed liquidity line to a financial institution is a 100%
#: outflow even though nothing has been drawn.
COMMITMENT_OUTFLOW = {
    ("retail", "credit"): 0.05,
    ("retail", "liquidity"): 0.05,
    ("corporate", "credit"): 0.10,
    ("corporate", "liquidity"): 0.30,
    ("financial", "credit"): 0.40,
    ("financial", "liquidity"): 1.00,
}

#: Inflows are capped at 75% of outflows, so a bank cannot rely wholly on
#: money coming in to meet money going out.
INFLOW_CAP = 0.75

#: Floor on net outflows as a share of gross outflows.
NET_OUTFLOW_FLOOR = 0.25


@dataclass
class LCRInputs:
    """Everything outside the balance-sheet objects that the LCR needs (£m)."""

    #: Contractual derivative cash outflows and inflows over 30 days.
    derivative_outflows: float = 0.0
    derivative_inflows: float = 0.0
    #: Collateral callable on a three-notch downgrade of the firm.
    downgrade_trigger_collateral: float = 0.0
    #: Look-back outflow for market valuation changes on posted collateral.
    market_valuation_outflow: float = 0.0
    #: Contractual inflows from performing loans maturing within 30 days,
    #: split by counterparty type.
    inflow_retail: float = 0.0
    inflow_corporate: float = 0.0
    inflow_financial: float = 0.0
    #: Reverse repo maturing within 30 days, by collateral level.
    reverse_repo_l1: float = 0.0
    reverse_repo_l2a: float = 0.0
    reverse_repo_other: float = 0.0


@dataclass
class LCRResult:
    hqla: float = 0.0
    hqla_by_level: dict[str, float] = field(default_factory=dict)
    gross_outflows: float = 0.0
    capped_inflows: float = 0.0
    net_outflows: float = 0.0
    ratio: float = 0.0
    outflow_detail: dict[str, float] = field(default_factory=dict)


def hqla_stock(assets: list[CreditExposure]) -> tuple[float, dict[str, float]]:
    """Apply haircuts, then the Level 2 and Level 2B caps."""
    raw = {"L1": 0.0, "L2A": 0.0, "L2B": 0.0}
    for a in assets:
        if a.hqla_level in raw:
            raw[a.hqla_level] += a.drawn * (1.0 - HQLA_HAIRCUT[a.hqla_level])

    l1 = raw["L1"]
    l2a = raw["L2A"]
    l2b_allowed = min(raw["L2B"], L2B_CAP_OF_L1_L2A * (l1 + l2a))
    l2_allowed = min(l2a + l2b_allowed, L2_CAP_OF_L1 * l1)
    # If the 40% cap binds, cut Level 2B first — it is the lower-quality tier.
    if l2_allowed < l2a + l2b_allowed:
        l2b_allowed = max(0.0, l2_allowed - l2a)
        l2a = min(l2a, l2_allowed)

    total = l1 + l2a + l2b_allowed
    return total, {"L1": l1, "L2A": l2a, "L2B": l2b_allowed}


def lcr(
    assets: list[CreditExposure],
    funding: list[Funding],
    commitments: list[Commitment],
    inputs: LCRInputs | None = None,
) -> LCRResult:
    inputs = inputs or LCRInputs()
    stock, by_level = hqla_stock(assets)

    detail: dict[str, float] = {}
    outflows = 0.0
    for f in funding:
        if f.maturity_years > 30.0 / 365.0 and f.funding_type in (
            FundingType.SENIOR_UNSECURED, FundingType.SENIOR_NON_PREFERRED,
            FundingType.COVERED_BOND_ISSUED, FundingType.TIER2, FundingType.AT1,
        ):
            continue  # term funding outside the 30-day window does not run
        if f.funding_type is FundingType.SECURED_FUNDING:
            rate = SECURED_OUTFLOW_BY_COLLATERAL.get(f.collateral_level, 1.00)
        else:
            rate = OUTFLOW_RATE.get(f.funding_type, 1.00)
            # Fully insured deposits run more slowly.
            if f.insured and f.funding_type is FundingType.CORPORATE_NON_OPERATIONAL:
                rate = 0.20
        amount = f.amount * rate
        outflows += amount
        detail[f.funding_type.value] = detail.get(f.funding_type.value, 0.0) + amount

    for c in commitments:
        rate = COMMITMENT_OUTFLOW.get((c.counterparty, c.kind), 0.40)
        amount = c.amount * rate
        outflows += amount
        detail["undrawn_commitments"] = detail.get("undrawn_commitments", 0.0) + amount

    derivative_outflow = (inputs.derivative_outflows
                          + inputs.downgrade_trigger_collateral
                          + inputs.market_valuation_outflow)
    outflows += derivative_outflow
    detail["derivatives"] = derivative_outflow

    inflows = (
        0.50 * inputs.inflow_retail
        + 0.50 * inputs.inflow_corporate
        + 1.00 * inputs.inflow_financial
        + 0.00 * inputs.reverse_repo_l1
        + 0.15 * inputs.reverse_repo_l2a
        + 1.00 * inputs.reverse_repo_other
        + inputs.derivative_inflows
    )
    capped = min(inflows, INFLOW_CAP * outflows)
    net = max(outflows - capped, NET_OUTFLOW_FLOOR * outflows)

    return LCRResult(
        hqla=stock, hqla_by_level=by_level, gross_outflows=outflows,
        capped_inflows=capped, net_outflows=net,
        ratio=safe_div(stock, net), outflow_detail=detail,
    )


# ---------------------------------------------------------------------------
# NSFR
# ---------------------------------------------------------------------------

#: Available stable funding factors, for funding with under a year to run.
#: Anything with a year or more, and all regulatory capital, is 100%.
ASF_FACTOR = {
    FundingType.RETAIL_STABLE: 0.95,
    FundingType.RETAIL_LESS_STABLE: 0.90,
    FundingType.OPERATIONAL_DEPOSIT: 0.50,
    FundingType.CORPORATE_NON_OPERATIONAL: 0.50,
    FundingType.FINANCIAL_DEPOSIT: 0.00,
    FundingType.SECURED_FUNDING: 0.00,
    FundingType.SENIOR_UNSECURED: 0.50,
    FundingType.SENIOR_NON_PREFERRED: 0.50,
    FundingType.COVERED_BOND_ISSUED: 0.50,
    FundingType.TIER2: 1.00,
    FundingType.AT1: 1.00,
    FundingType.CENTRAL_BANK_FACILITY: 0.00,
}

#: Required stable funding factors for HQLA held.
RSF_HQLA = {"L1": 0.05, "L2A": 0.15, "L2B": 0.50}


@dataclass
class NSFRResult:
    available: float = 0.0
    required: float = 0.0
    ratio: float = 0.0
    asf_detail: dict[str, float] = field(default_factory=dict)
    rsf_detail: dict[str, float] = field(default_factory=dict)


def available_stable_funding(
    funding: list[Funding], cet1: float
) -> tuple[float, dict[str, float]]:
    detail = {"capital": cet1}
    total = cet1
    for f in funding:
        factor = 1.00 if f.maturity_years >= 1.0 else ASF_FACTOR.get(f.funding_type, 0.0)
        # Funding from financial institutions with six months to a year gets
        # 50%, not zero — the one intermediate band in the ASF table.
        if (f.funding_type in (FundingType.FINANCIAL_DEPOSIT, FundingType.SECURED_FUNDING)
                and 0.5 <= f.maturity_years < 1.0):
            factor = 0.50
        amount = f.amount * factor
        total += amount
        detail[f.funding_type.value] = detail.get(f.funding_type.value, 0.0) + amount
    return total, detail


def required_stable_funding(
    assets: list[CreditExposure],
    trading_inventory: float = 0.0,
    derivative_assets: float = 0.0,
    derivative_liabilities: float = 0.0,
    fixed_assets: float = 0.0,
) -> tuple[float, dict[str, float]]:
    detail: dict[str, float] = {}
    total = 0.0

    for a in assets:
        if a.hqla_level in RSF_HQLA:
            factor = RSF_HQLA[a.hqla_level]
            key = f"hqla_{a.hqla_level}"
        elif a.is_defaulted:
            factor, key = 1.00, "non_performing"
        elif a.residual_maturity_years < 0.5:
            # Short-dated interbank lending is the cheapest asset to fund.
            factor = 0.10 if a.segment == "financial" else 0.50
            key = "short_dated"
        elif a.residual_maturity_years < 1.0:
            factor, key = 0.50, "under_one_year"
        elif a.exposure_class.value == "residential_real_estate":
            factor, key = 0.65, "residential_mortgages"
        else:
            factor, key = 0.85, "other_performing_loans"

        amount = a.drawn * factor
        total += amount
        detail[key] = detail.get(key, 0.0) + amount
        # Undrawn committed facilities require 5% stable funding.
        if a.undrawn:
            total += 0.05 * a.undrawn
            detail["undrawn"] = detail.get("undrawn", 0.0) + 0.05 * a.undrawn

    for label, amount, factor in (
        ("trading_inventory", trading_inventory, 0.85),
        ("derivative_assets", derivative_assets, 1.00),
        ("derivative_liabilities_addon", derivative_liabilities, 0.05),
        ("fixed_assets", fixed_assets, 1.00),
    ):
        if amount:
            detail[label] = amount * factor
            total += amount * factor

    return total, detail


def nsfr(
    assets: list[CreditExposure],
    funding: list[Funding],
    cet1: float,
    trading_inventory: float = 0.0,
    derivative_assets: float = 0.0,
    derivative_liabilities: float = 0.0,
    fixed_assets: float = 0.0,
) -> NSFRResult:
    asf, asf_detail = available_stable_funding(funding, cet1)
    rsf, rsf_detail = required_stable_funding(
        assets, trading_inventory, derivative_assets, derivative_liabilities, fixed_assets
    )
    return NSFRResult(
        available=asf, required=rsf, ratio=safe_div(asf, rsf),
        asf_detail=asf_detail, rsf_detail=rsf_detail,
    )
