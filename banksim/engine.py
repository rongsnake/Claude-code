"""
The simulation engine: one year at a time, in the order a bank actually does it.

Each period:

  1. Read the macro state from the scenario.
  2. Re-stage the book and re-measure ECL, giving the impairment charge.
  3. Recompute RWAs across all five risk types, on both the live and the
     all-standardised basis, and apply the output floor.
  4. Build the leverage exposure measure.
  5. Run the P&L: NII, markets, fees, costs, impairment, tax.
  6. Move capital: retained earnings take the profit, less AT1 coupons and less
     the dividend — and the dividend is capped by the MDA if the bank has eaten
     into its combined buffer.
  7. Grow (or shrink) the balance sheet into the next year.

Step 6 is the feedback loop that makes this a simulation rather than a
spreadsheet: a bad year cuts capital, which cuts the buffer, which caps the
dividend, which partly protects capital for the following year.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .bank import Bank
from .capital import (
    CapitalPosition,
    ExposureMeasure,
    RWABreakdown,
    mrel_requirement,
)
from .counterparty import ba_cva, counterparty_credit_rwa, sa_ccr_ead
from .credit_risk import credit_rwa, sa_risk_weight
from .exposures import CreditQuality, ExposureClass, IFRS9Stage, IRBApproach
from .ifrs9 import SEGMENT_RHO, impairment_charge, portfolio_ecl
from .liquidity import lcr, nsfr
from .market_risk import market_risk_rwa
from .op_risk import IncomeStatementYear, operational_risk
from .pnl import (
    BalanceSheet,
    IncomeStatement,
    fee_revenue,
    markets_revenue,
    net_interest_income,
)
from .scenario import MacroState, Scenario, conditional_pd, systematic_factor
from .units import safe_div

#: SA risk weights applied to derivative counterparties for the CCR charge,
#: keyed by the netting set's rating.
CCR_COUNTERPARTY_RW = {
    CreditQuality.AAA_AA: 0.20,
    CreditQuality.A: 0.30,
    CreditQuality.BBB: 0.75,
    CreditQuality.BB: 1.00,
    CreditQuality.B: 1.50,
    CreditQuality.CCC: 1.50,
    CreditQuality.UNRATED: 1.00,
}

#: Minimum CCF applied to off-balance-sheet items in the leverage exposure
#: measure — the leverage ratio does not allow a 0% conversion.
LEVERAGE_MIN_CCF = 0.10

#: Add-on applied to securities financing transactions in the exposure measure,
#: standing in for the full counterparty-exposure calculation. SIMPLIFIED.
SFT_COUNTERPARTY_ADDON = 0.02


#: How much of the point-in-time move in default risk feeds through to the IRB
#: PD used for capital. A purely point-in-time model would be 1.0 and a purely
#: through-the-cycle model 0.0; UK IRB models are hybrids, and supervisors
#: expect some cyclicality but not the full amount. STYLISED.
PD_CYCLICALITY = 0.35

#: In a stress test the bank re-weights its IFRS 9 scenarios towards the stress
#: rather than keeping its planning weights. This is the weight given to the
#: scenario being run; the rest is shared across the others in proportion.
STRESS_SCENARIO_WEIGHT = 0.55


def migrate_regulatory_pds(bank: Bank, macro: MacroState) -> None:
    """Move each exposure's IRB PD with the cycle.

    Without this the model understates the capital impact of a downturn
    badly: losses hit CET1 while RWAs stay flat, when in reality RWAs inflate
    at the same time, squeezing the ratio from both ends.
    """
    for e in bank.exposures:
        if e.is_defaulted:
            continue
        rho = SEGMENT_RHO.get(e.segment, 0.15)
        z = systematic_factor(macro, e.segment)
        point_in_time = conditional_pd(e.pd, z, rho)
        ratio = safe_div(point_in_time, e.pd, default=1.0)
        e.pd_regulatory = e.pd * (1.0 + PD_CYCLICALITY * (ratio - 1.0))


#: Years over which a defaulted exposure is worked out and written off. Until
#: it is, it sits in the non-performing pool carrying a heavy provision — which
#: is why cumulative impairment in a stress does not simply reverse when the
#: macro recovers.
DEFAULT_WORKOUT_YEARS = 2.5


def migrate_defaults(bank: Bank, macro: MacroState) -> float:
    """Crystallise the year's defaults and write off resolved ones.

    Performing balances default at their point-in-time PD and move into the
    non-performing pool. A tranche of the existing non-performing stock is
    resolved: the recovered part leaves the balance sheet, the unrecovered part
    is written off against the provision.

    Returns the write-offs, which are part of the P&L impairment charge even
    though they do not change the closing provision.
    """
    npe = next((e for e in bank.exposures if e.stage is IFRS9Stage.STAGE_3), None)
    if npe is None:
        return 0.0

    newly_defaulted = 0.0
    for e in bank.exposures:
        if e is npe or e.is_defaulted or e.hqla_level is not None:
            continue
        if e.exposure_class in (ExposureClass.EQUITY, ExposureClass.OTHER_ASSET):
            continue
        rho = SEGMENT_RHO.get(e.segment, 0.15)
        pd_pit = conditional_pd(e.pd, systematic_factor(macro, e.segment), rho)
        defaulted = e.drawn * pd_pit
        e.drawn -= defaulted
        newly_defaulted += defaulted

    resolved = npe.drawn / DEFAULT_WORKOUT_YEARS
    write_offs = resolved * npe.lgd
    npe.drawn = max(0.0, npe.drawn - resolved) + newly_defaulted
    npe.provision = max(0.0, npe.provision - write_offs)
    return write_offs


def stress_weighted_scenarios(
    scenarios: dict[str, Scenario], running: Scenario
) -> dict[str, Scenario]:
    """Re-weight the IFRS 9 scenario set around the scenario being run."""
    others = {n: sc for n, sc in scenarios.items() if n != running.name}
    other_weight = sum(sc.weight for sc in others.values()) or 1.0
    out: dict[str, Scenario] = {running.name: _reweight(running, STRESS_SCENARIO_WEIGHT)}
    for name, sc in others.items():
        share = (1.0 - STRESS_SCENARIO_WEIGHT) * sc.weight / other_weight
        out[name] = _reweight(sc, share)
    return out


def _reweight(sc: Scenario, weight: float) -> Scenario:
    return Scenario(sc.name, sc.description, sc.path, weight, sc.provenance)


@dataclass
class PeriodResult:
    """One simulated year."""

    year: int
    macro: MacroState
    income: IncomeStatement
    capital: CapitalPosition
    balance_sheet: BalanceSheet
    lcr_ratio: float = 0.0
    nsfr_ratio: float = 0.0
    ecl_balance: float = 0.0
    ecl_coverage: float = 0.0
    stage2_balance: float = 0.0
    stage3_balance: float = 0.0
    #: Gross drawn balance and ECL by IFRS 9 stage, over the lending book only
    #: (the liquidity portfolio is excluded — reserves and gilts carry no
    #: meaningful ECL and including them makes the coverage ratio nonsense).
    #: Captured here rather than read back off the bank, which by the time a
    #: report runs has moved on several years.
    stage_balances: dict[int, float] = field(default_factory=dict)
    stage_ecl: dict[int, float] = field(default_factory=dict)
    dividend: float = 0.0
    rote: float = 0.0
    mda_constrained: bool = False
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        out = {
            "year": self.year,
            "total_revenue": self.income.total_revenue,
            "operating_costs": self.income.operating_costs,
            "impairment": self.income.impairment,
            "profit_before_tax": self.income.profit_before_tax,
            "profit_after_tax": self.income.profit_after_tax,
            "cost_income_ratio": self.income.cost_income_ratio,
            "rote": self.rote,
            "lcr": self.lcr_ratio,
            "nsfr": self.nsfr_ratio,
            "ecl_balance": self.ecl_balance,
            "dividend": self.dividend,
            "mda_constrained": self.mda_constrained,
        }
        out.update(self.capital.summary())
        return out


# ---------------------------------------------------------------------------
# Risk computation
# ---------------------------------------------------------------------------


def compute_rwa(bank: Bank) -> tuple[RWABreakdown, dict[str, float], float]:
    """All five risk types. Returns (breakdown, SA-CCR EADs, derivative exposure)."""
    credit = credit_rwa(bank.exposures, bank.sa_cfg)

    rw_by_counterparty = {
        ns.counterparty: CCR_COUNTERPARTY_RW.get(ns.rating, 1.00)
        for ns in bank.netting_sets
    }
    ccr, eads = counterparty_credit_rwa(bank.netting_sets, rw_by_counterparty)
    cva = ba_cva(bank.netting_sets, eads)
    market = market_risk_rwa(bank.trading_book)
    op = operational_risk(bank.op_risk_history, bank.op_risk_cfg)

    # The leverage exposure measure uses SA-CCR replacement cost plus potential
    # future exposure, grossed by alpha — the same EAD as the risk-based
    # calculation, so it is computed once here.
    derivative_exposure = sum(sa_ccr_ead(ns).ead for ns in bank.netting_sets)

    breakdown = RWABreakdown(
        credit=credit.live_rwa,
        counterparty_credit=ccr,
        cva=cva.rwa,
        market=market.rwa,
        operational=op.rwa,
        # The output floor comparator: credit on a standardised basis, with the
        # other risk types unchanged because the firm already uses the
        # standardised approach for each of them.
        credit_sa=credit.sa_rwa,
        counterparty_credit_sa=ccr,
        cva_sa=cva.rwa,
        market_sa=market.rwa,
        operational_sa=op.rwa,
    )
    return breakdown, eads, derivative_exposure


def compute_exposure_measure(bank: Bank, derivative_exposure: float) -> ExposureMeasure:
    """The leverage ratio denominator."""
    banking_book = sum(
        e.net_carrying for e in bank.exposures if e.hqla_level is None
    )
    liquidity_portfolio = sum(e.drawn for e in bank.exposures if e.hqla_level is not None)
    central_bank = sum(
        e.drawn for e in bank.exposures
        if e.exposure_class is ExposureClass.CENTRAL_BANK
    )
    reverse_repo = bank.lcr_inputs.reverse_repo_l1 + bank.lcr_inputs.reverse_repo_l2a \
        + bank.lcr_inputs.reverse_repo_other

    off_balance = sum(
        max(LEVERAGE_MIN_CCF, 0.40) * c.amount for c in bank.commitments
    )

    return ExposureMeasure(
        on_balance_sheet=(banking_book + liquidity_portfolio
                          + bank.trading_book.inventory + bank.fixed_assets),
        derivative_exposure=derivative_exposure,
        sft_exposure=reverse_repo * (1.0 + SFT_COUNTERPARTY_ADDON),
        off_balance_sheet=off_balance,
        central_bank_claims_excluded=central_bank,
    )


def compute_capital_position(bank: Bank, year: int) -> CapitalPosition:
    """Snapshot the capital position without running a P&L."""
    rwa, _eads, derivative_exposure = compute_rwa(bank)
    exposure = compute_exposure_measure(bank, derivative_exposure)

    position = CapitalPosition(
        year=year,
        own_funds=bank.own_funds,
        rwa=rwa,
        requirements=bank.requirements,
        exposure_measure=exposure,
        leverage_cfg=bank.leverage_cfg,
        mrel_resources=bank.mrel_resources,
    )
    position.mrel_requirement_rwa = mrel_requirement(
        bank.requirements,
        position.leverage_requirement,
        position.total_rwa,
        exposure.total,
    )
    return position


def _apply_irb_provision_adjustments(bank: Bank, expected_loss: float, ecl_balance: float) -> None:
    """Set the CET1 IRB shortfall deduction and the Tier 2 excess-provision
    add-back from the gap between regulatory EL and accounting provisions.

    This is the join between the IFRS 9 engine and the capital stack, and it is
    asymmetric by design: a shortfall is deducted from CET1 pound for pound,
    while an excess is added to Tier 2 only up to 0.6% of credit RWAs.
    """
    gap = expected_loss - ecl_balance
    bank.own_funds.irb_shortfall = max(0.0, gap)
    bank.own_funds.excess_provisions = max(0.0, -gap)


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------


@dataclass
class GrowthPolicy:
    """How the balance sheet responds to the macro environment.

    Deliberately simple and deliberately pro-cyclical: lending grows with GDP,
    trading inventory shrinks when volatility spikes (desks de-risk), and both
    are overridden downwards if the bank is in its buffer.
    """

    lending_gdp_beta: float = 2.0
    inventory_vol_beta: float = -0.35
    #: Balance-sheet reduction applied when the MDA constraint binds.
    deleveraging_on_mda: float = 0.08

    def lending_growth(self, macro: MacroState) -> float:
        return max(-0.12, min(0.12, self.lending_gdp_beta * macro.gdp_growth))

    def inventory_growth(self, macro: MacroState) -> float:
        return max(-0.35, self.inventory_vol_beta * (macro.volatility_index - 1.0))


def run_period(
    bank: Bank,
    scenario: Scenario,
    scenarios: dict[str, Scenario],
    year: int,
    year_index: int,
    opening_ecl: float,
    losses_brought_forward: float = 0.0,
    growth: GrowthPolicy | None = None,
) -> tuple[PeriodResult, float, float]:
    """Run one year. Returns (result, closing ECL, losses carried forward)."""
    growth = growth or GrowthPolicy()
    macro = scenario.state(year)

    # --- 1. Impairment ----------------------------------------------------
    # ECL stays probability-weighted across the scenario set, but the weights
    # move towards the scenario actually being run — a bank in a downturn does
    # not keep the planning weights it set in benign conditions.
    write_offs = migrate_defaults(bank, macro)
    weighted = stress_weighted_scenarios(scenarios, scenario)
    ecl = portfolio_ecl(bank.exposures, weighted, year, central=scenario.name)
    charge = impairment_charge(opening_ecl, ecl.total, write_offs)

    # IRB PDs migrate with the cycle before RWAs are struck.
    migrate_regulatory_pds(bank, macro)

    # --- 2. RWAs and the exposure measure ---------------------------------
    credit = credit_rwa(bank.exposures, bank.sa_cfg)
    _apply_irb_provision_adjustments(bank, credit.expected_loss, ecl.total)

    rwa, _eads, derivative_exposure = compute_rwa(bank)
    exposure = compute_exposure_measure(bank, derivative_exposure)

    # --- 3. P&L ------------------------------------------------------------
    nii = net_interest_income(bank.nii, bank.funding, macro, bank.hedge)
    mkt = markets_revenue(bank.desks, macro)
    fees, fee_detail = fee_revenue(bank.fee_businesses, macro)

    income = IncomeStatement(year=year)
    income.net_interest_income = nii.net_interest_income
    income.markets_revenue = mkt.total
    income.fee_revenue = fees
    income.other_income = 45.0
    income.revenue_detail = {**mkt.by_desk, **fee_detail,
                             "net_interest_income": nii.net_interest_income}

    costs, cost_detail = bank.costs.total(income.total_revenue, year_index)
    income.operating_costs = costs
    income.cost_detail = cost_detail
    income.impairment = charge

    # Bank levy base: total liabilities less Tier 1 capital, insured deposits
    # and repo secured on high-quality collateral.
    from .exposures import FundingType as _FT
    excluded = sum(
        f.amount for f in bank.funding
        if f.insured
        or (f.funding_type is _FT.SECURED_FUNDING and f.collateral_level == "L1")
        or f.funding_type in (_FT.AT1,)
    )
    chargeable_liabilities = max(
        0.0, sum(f.amount for f in bank.funding) - bank.own_funds.tier1 - excluded
    )
    tax, losses_carried = bank.tax.charge(
        income.profit_before_tax, chargeable_liabilities, losses_brought_forward
    )
    income.tax = tax

    # --- 4. Capital movement ----------------------------------------------
    # The MDA test is run on the position *before* the year's distribution,
    # which is what gates the dividend. `own_funds` is copied into each
    # position so that later mutation of the bank does not retrospectively
    # rewrite a reported year.
    def _position(own_funds) -> CapitalPosition:
        pos = CapitalPosition(
            year=year, own_funds=copy.deepcopy(own_funds), rwa=rwa,
            requirements=bank.requirements, exposure_measure=exposure,
            leverage_cfg=bank.leverage_cfg, mrel_resources=bank.mrel_resources,
        )
        pos.mrel_requirement_rwa = mrel_requirement(
            bank.requirements, pos.leverage_requirement,
            pos.total_rwa, exposure.total,
        )
        return pos

    opening_position = _position(bank.own_funds)

    attributable = income.profit_after_tax - bank.at1_coupons
    mda_share = opening_position.max_distributable_share
    intended_dividend = max(0.0, bank.target_payout_ratio * attributable)
    dividend = min(intended_dividend, max(0.0, mda_share * attributable))
    mda_constrained = (opening_position.in_buffer
                       and dividend < intended_dividend - 1e-9)

    notes: list[str] = []
    if opening_position.in_buffer:
        notes.append(
            f"CET1 available for buffers "
            f"{opening_position.cet1_available_for_buffers:.4%} is below the "
            f"combined buffer requirement {bank.requirements.combined_buffer:.2%}; "
            f"MDA payout capped at {mda_share:.0%}."
        )
    if opening_position.output_floor_binding:
        notes.append(
            f"Output floor binding: adds "
            f"£{opening_position.output_floor_impact:,.0f}m of RWAs "
            f"({opening_position.output_floor_impact / max(rwa.live_total, 1):.1%} "
            f"of unfloored RWAs)."
        )
    if opening_position.leverage_headroom_pct < 0:
        notes.append("Leverage ratio below requirement.")

    # AT1 coupons are payable out of distributable items and are themselves
    # subject to the MDA; a bank deep in its buffer cancels them.
    at1_paid = bank.at1_coupons if mda_share > 0 else 0.0
    retained = income.profit_after_tax - at1_paid - dividend
    bank.own_funds.retained_earnings += retained
    position = _position(bank.own_funds)

    # --- 5. Balance sheet --------------------------------------------------
    bs = _build_balance_sheet(bank, year, derivative_exposure)

    average_tangible_equity = max(
        bank.own_funds.cet1 - retained / 2.0, 1.0
    )
    rote = income.return_on_tangible_equity(average_tangible_equity, at1_paid)

    liq = lcr(bank.exposures, bank.funding, bank.commitments, bank.lcr_inputs)
    stable = nsfr(
        bank.exposures, bank.funding, bank.own_funds.cet1,
        trading_inventory=bank.trading_book.inventory,
        derivative_assets=bank.derivative_assets_net,
        derivative_liabilities=bank.derivative_liabilities,
        fixed_assets=bank.fixed_assets,
        reverse_repo_l1=bank.lcr_inputs.reverse_repo_l1,
        reverse_repo_other=(bank.lcr_inputs.reverse_repo_l2a
                            + bank.lcr_inputs.reverse_repo_other),
    )

    # Snapshot the staging over the lending book before the balance sheet moves.
    lending = [e for e in bank.exposures if e.hqla_level is None]
    stage_balances: dict[int, float] = {}
    stage_ecl: dict[int, float] = {}
    for e in lending:
        k = int(e.stage)
        stage_balances[k] = stage_balances.get(k, 0.0) + e.drawn
        stage_ecl[k] = stage_ecl.get(k, 0.0) + e.provision

    lending_ecl = sum(stage_ecl.values())
    lending_gross = sum(stage_balances.values())

    result = PeriodResult(
        year=year, macro=macro, income=income, capital=position,
        balance_sheet=bs, lcr_ratio=liq.ratio, nsfr_ratio=stable.ratio,
        ecl_balance=ecl.total, ecl_coverage=safe_div(lending_ecl, lending_gross),
        stage2_balance=stage_balances.get(2, 0.0),
        stage3_balance=stage_balances.get(3, 0.0),
        stage_balances=stage_balances, stage_ecl=stage_ecl,
        dividend=dividend, rote=rote, mda_constrained=mda_constrained, notes=notes,
    )

    # --- 6. Grow into next year -------------------------------------------
    _grow(bank, macro, growth, deleverage=mda_constrained)
    _roll_op_risk_history(bank, income, nii.interest_income, nii.interest_expense)

    return result, ecl.total, losses_carried


def _build_balance_sheet(bank: Bank, year: int, derivative_exposure: float) -> BalanceSheet:
    central_bank = sum(e.drawn for e in bank.exposures
                       if e.exposure_class is ExposureClass.CENTRAL_BANK)
    securities = sum(e.drawn for e in bank.exposures
                     if e.hqla_level is not None
                     and e.exposure_class is not ExposureClass.CENTRAL_BANK)
    loans = sum(e.net_carrying for e in bank.exposures
                if e.hqla_level is None
                and e.exposure_class not in (ExposureClass.OTHER_ASSET,
                                             ExposureClass.EQUITY))
    other = sum(e.drawn for e in bank.exposures
                if e.exposure_class in (ExposureClass.OTHER_ASSET, ExposureClass.EQUITY))
    reverse_repo = (bank.lcr_inputs.reverse_repo_l1 + bank.lcr_inputs.reverse_repo_l2a
                    + bank.lcr_inputs.reverse_repo_other)

    from .exposures import FundingType as FT
    deposits = sum(f.amount for f in bank.funding if f.funding_type in (
        FT.RETAIL_STABLE, FT.RETAIL_LESS_STABLE, FT.OPERATIONAL_DEPOSIT,
        FT.CORPORATE_NON_OPERATIONAL, FT.FINANCIAL_DEPOSIT))
    repo = sum(f.amount for f in bank.funding if f.funding_type is FT.SECURED_FUNDING)
    debt = sum(f.amount for f in bank.funding if f.funding_type in (
        FT.SENIOR_UNSECURED, FT.SENIOR_NON_PREFERRED, FT.COVERED_BOND_ISSUED))
    sub = sum(f.amount for f in bank.funding if f.funding_type in (FT.TIER2, FT.AT1))

    equity = bank.own_funds.cet1_before_deductions + bank.own_funds.at1_instruments

    bs = BalanceSheet(
        year=year,
        cash_and_central_bank=central_bank,
        loans_and_advances=loans,
        trading_assets=bank.trading_book.inventory,
        derivative_assets=bank.derivative_assets,
        reverse_repo=reverse_repo,
        investment_securities=securities,
        other_assets=other + bank.fixed_assets,
        deposits=deposits, repo=repo, debt_securities_issued=debt,
        derivative_liabilities=bank.derivative_liabilities,
        subordinated_liabilities=sub, equity=equity,
    )
    # Balance the sheet with a residual "other liabilities" line rather than
    # pretending it reconciles exactly; the residual is reported.
    bs.other_liabilities = max(
        0.0, bs.total_assets - bs.total_liabilities - bs.equity
    )
    return bs


def _grow(bank: Bank, macro: MacroState, policy: GrowthPolicy, deleverage: bool) -> None:
    """Roll the balance sheet forward."""
    lending_growth = policy.lending_growth(macro)
    inventory_growth = policy.inventory_growth(macro)
    if deleverage:
        lending_growth -= policy.deleveraging_on_mda
        inventory_growth -= policy.deleveraging_on_mda

    for e in bank.exposures:
        if e.hqla_level is not None:
            continue  # the liquidity portfolio is managed to the LCR, not grown
        e.drawn *= (1.0 + lending_growth)
        e.undrawn *= (1.0 + lending_growth)

    bank.trading_book.inventory *= (1.0 + inventory_growth)
    for desk in bank.desks:
        desk.inventory *= (1.0 + inventory_growth)

    bank.nii.interest_earning_assets *= (1.0 + 0.6 * lending_growth)


def _roll_op_risk_history(
    bank: Bank, income: IncomeStatement, interest_income: float, interest_expense: float
) -> None:
    """Append the year just run to the three-year Business Indicator window."""
    bank.op_risk_history.append(IncomeStatementYear(
        interest_income=interest_income,
        interest_expense=interest_expense,
        interest_earning_assets=bank.nii.interest_earning_assets,
        dividend_income=25.0,
        fee_income=income.fee_revenue, fee_expense=0.18 * income.fee_revenue,
        other_operating_income=income.other_income, other_operating_expense=95.0,
        trading_book_pnl=income.markets_revenue,
        banking_book_pnl=0.12 * income.net_interest_income,
    ))
    bank.op_risk_history = bank.op_risk_history[-3:]


# ---------------------------------------------------------------------------
# Multi-period run
# ---------------------------------------------------------------------------


@dataclass
class SimulationResult:
    bank_name: str
    scenario: str
    periods: list[PeriodResult] = field(default_factory=list)
    #: CET1 ratio before the first projected year. The drawdown is measured
    #: from here — a stress whose worst year is year one would otherwise show
    #: no drawdown at all.
    opening_cet1_ratio: float = 0.0

    @property
    def min_cet1_ratio(self) -> float:
        return min((p.capital.cet1_ratio for p in self.periods), default=0.0)

    @property
    def min_leverage_ratio(self) -> float:
        return min((p.capital.leverage_ratio for p in self.periods), default=0.0)

    @property
    def cumulative_impairment(self) -> float:
        return sum(p.income.impairment for p in self.periods)

    @property
    def cumulative_profit_after_tax(self) -> float:
        return sum(p.income.profit_after_tax for p in self.periods)

    def cet1_drawdown(self) -> float:
        """Peak-to-trough fall in the CET1 ratio, in percentage points — the
        headline number of any stress test."""
        if not self.periods:
            return 0.0
        ratios = [p.capital.cet1_ratio for p in self.periods]
        if self.opening_cet1_ratio:
            ratios = [self.opening_cet1_ratio] + ratios
        peak = ratios[0]
        worst = 0.0
        for r in ratios:
            peak = max(peak, r)
            worst = max(worst, peak - r)
        return worst


def run_simulation(
    bank: Bank,
    scenario: Scenario,
    scenarios: dict[str, Scenario],
    start_year: int = 2027,
    years: int = 5,
    growth: GrowthPolicy | None = None,
) -> SimulationResult:
    """Run `years` periods of `scenario` against `bank`, mutating the bank."""
    result = SimulationResult(
        bank_name=bank.name, scenario=scenario.name,
        opening_cet1_ratio=compute_capital_position(bank, start_year).cet1_ratio,
    )

    # Opening ECL, measured on the scenario set before any period is run.
    opening = portfolio_ecl(bank.exposures, scenarios, start_year, central="baseline")
    opening_ecl = opening.total
    losses = 0.0

    for i in range(years):
        year = start_year + i
        period, opening_ecl, losses = run_period(
            bank, scenario, scenarios, year, i, opening_ecl, losses, growth
        )
        result.periods.append(period)

    return result
