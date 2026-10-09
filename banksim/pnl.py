"""
The income statement: where a wholesale bank's money actually comes from.

Four revenue engines, modelled separately because they respond to the macro
scenario in opposite directions — which is the whole point of a diversified
wholesale bank, and the thing a single-driver model cannot show:

  * **Net interest income** — lending and the structural hedge. Rises with
    Bank Rate, falls with deposit competition, lags the rate cycle because the
    hedge rolls slowly.
  * **Markets revenue** — client flow times bid-offer, plus the mark on
    inventory. Volatility *helps* (wider spreads, more hedging demand) until it
    doesn't: past a point clients stop trading and inventory marks against you.
  * **Fee and advisory income** — DCM, ECM and M&A. Strongly procyclical, and
    the first thing to disappear in a stress.
  * **Other/associates** — small, modelled as a constant.

Against those: operating costs (with a bonus pool that flexes with revenue),
impairment from the IFRS 9 engine, and tax — which in the UK means corporation
tax, the banking surcharge and the bank levy, all three.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exposures import Funding, FundingType
from .scenario import MacroState
from .units import clamp, safe_div

# ---------------------------------------------------------------------------
# Net interest income
# ---------------------------------------------------------------------------


@dataclass
class StructuralHedge:
    """A rolling portfolio of swaps/gilts investing equity and non-interest
    bearing balances.

    This is the mechanism that makes a bank's NII lag the rate cycle: only
    1/tenor of the hedge reprices each year, so a bank with a five-year hedge
    is still earning yesterday's rates well after the MPC has moved.
    """

    notional: float = 0.0            # £m
    tenor_years: int = 5
    #: The rates at which each vintage was invested, oldest first.
    vintages: list[float] = field(default_factory=list)

    def initialise(self, rate: float) -> None:
        self.vintages = [rate] * self.tenor_years

    def roll(self, new_rate: float) -> float:
        """Reinvest the maturing tranche and return the blended yield."""
        if not self.vintages:
            self.initialise(new_rate)
        self.vintages.pop(0)
        self.vintages.append(new_rate)
        return sum(self.vintages) / len(self.vintages)

    @property
    def yield_rate(self) -> float:
        return sum(self.vintages) / len(self.vintages) if self.vintages else 0.0

    def income(self) -> float:
        return self.notional * self.yield_rate


@dataclass
class NIIInputs:
    """Balances and margins for the net interest income calculation (£m)."""

    interest_earning_assets: float = 0.0
    #: Share of assets repricing with Bank Rate within the year.
    asset_rate_sensitivity: float = 0.75
    #: Spread over the reference rate earned on assets.
    asset_spread: float = 0.020
    #: Beta: how much of a Bank Rate move is passed through to depositors.
    #: The single most valuable number in a retail bank and the hardest to
    #: forecast; it ratchets up as customers move to savings accounts.
    deposit_beta: float = 0.55
    #: Spread paid over the reference rate on wholesale funding.
    wholesale_spread: float = 0.009


@dataclass
class NIIResult:
    interest_income: float = 0.0
    interest_expense: float = 0.0
    hedge_income: float = 0.0
    net_interest_income: float = 0.0
    net_interest_margin: float = 0.0


def net_interest_income(
    inputs: NIIInputs,
    funding: list[Funding],
    macro: MacroState,
    hedge: StructuralHedge | None = None,
) -> NIIResult:
    """One year of NII, given the rate environment."""
    asset_yield = (inputs.asset_spread
                   + inputs.asset_rate_sensitivity * macro.bank_rate
                   + (1.0 - inputs.asset_rate_sensitivity) * 0.02)
    interest_income = inputs.interest_earning_assets * asset_yield

    interest_expense = 0.0
    for f in funding:
        if f.funding_type in (
            FundingType.RETAIL_STABLE, FundingType.RETAIL_LESS_STABLE,
            FundingType.OPERATIONAL_DEPOSIT, FundingType.CORPORATE_NON_OPERATIONAL,
        ):
            rate = inputs.deposit_beta * macro.bank_rate
        elif f.funding_type is FundingType.SECURED_FUNDING:
            # Repo prices off the risk-free rate with a thin spread.
            rate = macro.bank_rate + 0.001
        else:
            # Term issuance reprices only as it matures; approximate by blending
            # the contractual coupon with the current market level.
            roll_share = clamp(1.0 / max(f.maturity_years, 1.0), 0.0, 1.0)
            market_rate = macro.bank_rate + inputs.wholesale_spread
            rate = (1.0 - roll_share) * f.rate + roll_share * market_rate
        interest_expense += f.amount * rate

    hedge_income = 0.0
    if hedge is not None and hedge.notional:
        hedge.roll(macro.gilt_5y)
        hedge_income = hedge.income()

    nii = interest_income + hedge_income - interest_expense
    return NIIResult(
        interest_income=interest_income,
        interest_expense=interest_expense,
        hedge_income=hedge_income,
        net_interest_income=nii,
        net_interest_margin=safe_div(nii, inputs.interest_earning_assets),
    )


# ---------------------------------------------------------------------------
# Markets revenue
# ---------------------------------------------------------------------------


@dataclass
class MarketsDesk:
    """One trading desk, described by what drives its revenue.

    `vol_beta` is the elasticity of revenue to the volatility index. Rates and
    FX desks have a positive beta — they make money when clients need to hedge.
    Equity derivatives and credit desks have a lower or negative one, because
    their inventory and their structured books lose money in a gap move.
    """

    name: str
    #: Normal-conditions revenue, £m per year.
    base_revenue: float
    vol_beta: float = 0.35
    activity_beta: float = 0.45
    #: Inventory carried, £m, marked against the relevant market.
    inventory: float = 0.0
    #: Sensitivity of the inventory mark to the equity/credit shock, decimal.
    inventory_beta: float = 0.0
    #: Revenue floor as a share of base — desks keep some franchise revenue
    #: even in a crisis, because clients must still transact.
    floor_share: float = 0.30


def desk_revenue(desk: MarketsDesk, macro: MacroState) -> float:
    """Revenue for one desk in one year."""
    vol_effect = 1.0 + desk.vol_beta * (macro.volatility_index - 1.0)
    # Past roughly twice normal volatility, client volume collapses faster than
    # spreads widen, so the relationship turns over.
    if macro.volatility_index > 2.0:
        vol_effect *= 1.0 - 0.30 * (macro.volatility_index - 2.0)
    activity_effect = 1.0 + desk.activity_beta * (macro.activity_index - 1.0)

    flow = desk.base_revenue * max(vol_effect * activity_effect, desk.floor_share)
    inventory_mark = desk.inventory * desk.inventory_beta * macro.equity_return
    return flow + inventory_mark


@dataclass
class MarketsResult:
    total: float = 0.0
    by_desk: dict[str, float] = field(default_factory=dict)


def markets_revenue(desks: list[MarketsDesk], macro: MacroState) -> MarketsResult:
    res = MarketsResult()
    for d in desks:
        r = desk_revenue(d, macro)
        res.by_desk[d.name] = r
        res.total += r
    return res


# ---------------------------------------------------------------------------
# Fee and advisory income
# ---------------------------------------------------------------------------


@dataclass
class FeeBusiness:
    """DCM, ECM or advisory. `activity_beta` above 1 means it amplifies the
    cycle — equity capital markets is the clearest example: issuance windows
    shut completely in a stress."""

    name: str
    base_revenue: float
    activity_beta: float = 1.0
    floor_share: float = 0.15


def fee_revenue(businesses: list[FeeBusiness], macro: MacroState) -> tuple[float, dict[str, float]]:
    out: dict[str, float] = {}
    total = 0.0
    for b in businesses:
        factor = max(macro.activity_index ** b.activity_beta, b.floor_share)
        r = b.base_revenue * factor
        out[b.name] = r
        total += r
    return total, out


# ---------------------------------------------------------------------------
# Costs and tax
# ---------------------------------------------------------------------------


@dataclass
class CostModel:
    """Fixed costs plus a bonus pool that flexes with revenue.

    The comp ratio is the lever management actually pulls in a bad year, and it
    has a floor: you cannot pay a markets franchise nothing and keep it.
    """

    fixed_staff_costs: float = 0.0        # £m
    non_staff_costs: float = 0.0          # £m
    variable_comp_ratio: float = 0.22     # share of total revenue
    minimum_variable_comp: float = 0.0    # £m
    #: Annual inflation applied to fixed costs.
    cost_inflation: float = 0.03
    #: Non-recurring items: restructuring, conduct redress, litigation.
    exceptional_costs: float = 0.0

    def total(self, revenue: float, year_index: int = 0) -> tuple[float, dict[str, float]]:
        inflator = (1.0 + self.cost_inflation) ** year_index
        fixed = self.fixed_staff_costs * inflator
        non_staff = self.non_staff_costs * inflator
        variable = max(self.variable_comp_ratio * max(revenue, 0.0),
                       self.minimum_variable_comp)
        detail = {
            "fixed_staff": fixed,
            "non_staff": non_staff,
            "variable_compensation": variable,
            "exceptional": self.exceptional_costs,
        }
        return sum(detail.values()), detail


@dataclass
class UKTaxModel:
    """UK corporation tax, the banking surcharge and the bank levy.

    Three separate charges with three different bases, which is why a UK bank's
    effective tax rate is well above the headline corporation tax rate.
    """

    corporation_tax_rate: float = 0.25
    #: Surcharge on banking profits above the allowance.
    surcharge_rate: float = 0.03
    surcharge_allowance: float = 100.0    # £m
    #: Bank levy on chargeable equity and liabilities. The base excludes Tier 1
    #: capital, insured deposits and repo secured on high-quality assets, so it
    #: is materially narrower than total liabilities — the caller computes it.
    levy_rate_short_term: float = 0.001
    #: Losses carried forward can shelter only part of a later year's profit.
    loss_relief_restriction: float = 0.50

    def charge(
        self, profit_before_tax: float, chargeable_liabilities: float,
        losses_brought_forward: float = 0.0,
    ) -> tuple[float, float]:
        """Return (tax charge, losses carried forward)."""
        levy = self.levy_rate_short_term * max(chargeable_liabilities, 0.0)

        if profit_before_tax <= 0:
            return levy, losses_brought_forward - profit_before_tax

        shelterable = min(losses_brought_forward,
                          self.loss_relief_restriction * profit_before_tax)
        taxable = profit_before_tax - shelterable
        tax = self.corporation_tax_rate * taxable
        surcharge_base = max(taxable - self.surcharge_allowance, 0.0)
        tax += self.surcharge_rate * surcharge_base
        return tax + levy, losses_brought_forward - shelterable


# ---------------------------------------------------------------------------
# Income statement
# ---------------------------------------------------------------------------


@dataclass
class IncomeStatement:
    """One year. All figures £m."""

    year: int
    net_interest_income: float = 0.0
    markets_revenue: float = 0.0
    fee_revenue: float = 0.0
    other_income: float = 0.0
    operating_costs: float = 0.0
    impairment: float = 0.0
    tax: float = 0.0
    cost_detail: dict[str, float] = field(default_factory=dict)
    revenue_detail: dict[str, float] = field(default_factory=dict)

    @property
    def total_revenue(self) -> float:
        return (self.net_interest_income + self.markets_revenue
                + self.fee_revenue + self.other_income)

    @property
    def pre_provision_operating_profit(self) -> float:
        """PPOP — the first line of defence against credit losses, and the one
        a stress test really tests."""
        return self.total_revenue - self.operating_costs

    @property
    def profit_before_tax(self) -> float:
        return self.pre_provision_operating_profit - self.impairment

    @property
    def profit_after_tax(self) -> float:
        return self.profit_before_tax - self.tax

    @property
    def cost_income_ratio(self) -> float:
        return safe_div(self.operating_costs, self.total_revenue)

    def return_on_tangible_equity(self, average_tangible_equity: float,
                                  at1_coupons: float = 0.0) -> float:
        """RoTE — profit attributable to ordinary shareholders over tangible
        equity. AT1 coupons are deducted: they are a distribution, not an
        expense, but they are not available to the ordinary shareholder."""
        return safe_div(self.profit_after_tax - at1_coupons, average_tangible_equity)


@dataclass
class BalanceSheet:
    """Summary balance sheet, £m. Assets and liabilities are reconciled by the
    engine each period, so `check` should be near zero."""

    year: int
    cash_and_central_bank: float = 0.0
    loans_and_advances: float = 0.0
    trading_assets: float = 0.0
    derivative_assets: float = 0.0
    reverse_repo: float = 0.0
    investment_securities: float = 0.0
    other_assets: float = 0.0

    deposits: float = 0.0
    repo: float = 0.0
    debt_securities_issued: float = 0.0
    derivative_liabilities: float = 0.0
    subordinated_liabilities: float = 0.0
    other_liabilities: float = 0.0
    equity: float = 0.0

    @property
    def total_assets(self) -> float:
        return (self.cash_and_central_bank + self.loans_and_advances
                + self.trading_assets + self.derivative_assets + self.reverse_repo
                + self.investment_securities + self.other_assets)

    @property
    def total_liabilities(self) -> float:
        return (self.deposits + self.repo + self.debt_securities_issued
                + self.derivative_liabilities + self.subordinated_liabilities
                + self.other_liabilities)

    @property
    def check(self) -> float:
        return self.total_assets - self.total_liabilities - self.equity
