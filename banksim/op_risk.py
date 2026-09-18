"""
Operational risk: the Basel 3.1 standardised approach.

One formula, three inputs:

    Business Indicator (BI)  ->  BI Component (BIC)  ->  x Internal Loss
                                                          Multiplier (ILM)

The BI is a proxy for the size of the business, built from three years of the
income statement. The BIC applies marginal coefficients across three size
buckets. The ILM scales the result by the firm's own ten-year loss history.

UK specifics
------------
The PRA's implementation sets **ILM = 1** for all firms rather than using
internal loss data, which removes the loss-history feedback loop that the Basel
text contains. `OpRiskConfig.use_ilm` defaults to False to match, but the ILM
is implemented so the effect of the UK choice can be measured — for a bank with
a large historical loss (conduct redress, say) the two diverge sharply.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .units import safe_div

RWA_MULTIPLIER = 12.5

#: Marginal BI buckets and coefficients. Basel states these in euro; the PRA
#: sets sterling equivalents. STYLISED conversion at a round rate — check the
#: actual thresholds in the PRA Rulebook Operational Risk part before use.
BI_BUCKET_1_CAP = 1_000.0      # £m
BI_BUCKET_2_CAP = 30_000.0     # £m
BI_COEFFICIENT_1 = 0.12
BI_COEFFICIENT_2 = 0.15
BI_COEFFICIENT_3 = 0.18

#: The cap on the interest component, as a share of interest-earning assets.
#: It stops a high-margin lender from being penalised purely for its margin.
ILDC_ASSET_CAP = 0.0225

#: Loss component multiplier: 15x the ten-year average annual loss.
LOSS_MULTIPLIER = 15.0


@dataclass
class IncomeStatementYear:
    """The income-statement lines the BI is built from, for one year (£m)."""

    interest_income: float = 0.0
    interest_expense: float = 0.0
    interest_earning_assets: float = 0.0
    dividend_income: float = 0.0
    fee_income: float = 0.0
    fee_expense: float = 0.0
    other_operating_income: float = 0.0
    other_operating_expense: float = 0.0
    trading_book_pnl: float = 0.0
    banking_book_pnl: float = 0.0

    def ildc(self) -> float:
        """Interest, leases and dividend component."""
        net_interest = abs(self.interest_income - self.interest_expense)
        capped = min(net_interest, ILDC_ASSET_CAP * self.interest_earning_assets)
        return capped + abs(self.dividend_income)

    def services(self) -> float:
        """Services component — the larger of income and expense on each leg,
        so that an outsourced, fee-paying business is not treated as smaller."""
        return (max(self.other_operating_income, self.other_operating_expense)
                + max(self.fee_income, self.fee_expense))

    def financial(self) -> float:
        """Financial component — absolute P&L, so losses increase the charge."""
        return abs(self.trading_book_pnl) + abs(self.banking_book_pnl)

    def business_indicator(self) -> float:
        return self.ildc() + self.services() + self.financial()


@dataclass
class OpRiskConfig:
    #: The PRA sets ILM = 1; set True to use the firm's loss history instead.
    use_ilm: bool = False
    #: Ten-year average annual operational risk losses, £m.
    average_annual_loss: float = 0.0


@dataclass
class OpRiskResult:
    business_indicator: float = 0.0
    bic: float = 0.0
    ilm: float = 1.0
    capital: float = 0.0
    rwa: float = 0.0
    detail: dict[str, float] = field(default_factory=dict)


def business_indicator(history: list[IncomeStatementYear]) -> float:
    """Three-year average BI. Shorter histories are averaged over what exists."""
    if not history:
        return 0.0
    window = history[-3:]
    return sum(y.business_indicator() for y in window) / len(window)


def bi_component(bi: float) -> float:
    """Marginal coefficients applied across the three size buckets."""
    b1 = min(bi, BI_BUCKET_1_CAP)
    b2 = max(0.0, min(bi, BI_BUCKET_2_CAP) - BI_BUCKET_1_CAP)
    b3 = max(0.0, bi - BI_BUCKET_2_CAP)
    return BI_COEFFICIENT_1 * b1 + BI_COEFFICIENT_2 * b2 + BI_COEFFICIENT_3 * b3


def internal_loss_multiplier(bic: float, average_annual_loss: float) -> float:
    """ILM = ln(e - 1 + (LC/BIC)^0.8). Equals 1 when LC == BIC."""
    if bic <= 0:
        return 1.0
    lc = LOSS_MULTIPLIER * average_annual_loss
    ratio = safe_div(lc, bic)
    return math.log(math.e - 1.0 + ratio ** 0.8)


def operational_risk(
    history: list[IncomeStatementYear], cfg: OpRiskConfig | None = None
) -> OpRiskResult:
    cfg = cfg or OpRiskConfig()
    bi = business_indicator(history)
    bic = bi_component(bi)
    ilm = internal_loss_multiplier(bic, cfg.average_annual_loss) if cfg.use_ilm else 1.0
    capital = bic * ilm

    window = history[-3:] if history else []
    detail = {
        "ildc": sum(y.ildc() for y in window) / len(window) if window else 0.0,
        "services": sum(y.services() for y in window) / len(window) if window else 0.0,
        "financial": sum(y.financial() for y in window) / len(window) if window else 0.0,
    }
    return OpRiskResult(
        business_indicator=bi, bic=bic, ilm=ilm,
        capital=capital, rwa=capital * RWA_MULTIPLIER, detail=detail,
    )
