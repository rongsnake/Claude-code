"""
IFRS 9 expected credit losses: the three stages, and the macro conditioning.

The accounting charge, not the regulatory one. The two differ deliberately:
regulatory expected loss is a through-the-cycle 12-month number used to test the
adequacy of provisions, while IFRS 9 ECL is a point-in-time, probability-weighted
estimate over 12 months or the asset's life depending on stage.

    Stage 1  performing                      -> 12-month ECL
    Stage 2  significant increase in risk    -> lifetime ECL
    Stage 3  credit-impaired                 -> lifetime ECL on a defaulted asset

Two features of the standard drive most of the volatility in a bank's reported
impairment charge, and both are modelled here:

  * **Multiple economic scenarios.** ECL is the probability-weighted average
    across scenarios, and because ECL is convex in the macro path, that average
    is higher than the ECL of the average path. The gap is real money.
  * **Stage transfer.** An asset moving from stage 1 to stage 2 has its
    provision jump from twelve months of loss to a lifetime of it, with no
    default having occurred. In a downturn this cliff, not the defaults
    themselves, is what hits the first-year P&L.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .exposures import CreditExposure, ExposureClass, IFRS9Stage
from .scenario import Scenario, conditional_pd, systematic_factor
from .units import clamp, norm_cdf, safe_div

#: Asset correlation used for the macro conditioning, by segment. Higher rho
#: means the segment's defaults are more driven by the common factor and less
#: by idiosyncratic risk, so the PD responds more violently to the scenario.
SEGMENT_RHO = {
    "mortgages": 0.15,
    "corporate": 0.12,
    "leveraged_finance": 0.18,
    "financial": 0.20,
    "sovereign": 0.25,
    "cre": 0.18,
    "prime_brokerage": 0.20,
}
DEFAULT_RHO = 0.15

#: SICR test. An exposure moves to stage 2 when its PD has risen by more than
#: a multiple of its origination PD *and* by at least an absolute threshold.
#: Both limbs are needed: the relative test alone moves everything with a tiny
#: origination PD, the absolute test alone moves nothing investment grade.
SICR_ABSOLUTE_INCREASE = 0.005

#: The relative threshold is graduated by origination PD, as UK banks' disclosed
#: methodologies are. A low-PD name doubling its PD is noise; a sub-investment
#: grade name doubling its PD is not. A flat doubling threshold migrates almost
#: the entire book in a severe stress, which is not what banks report.
SICR_MULTIPLE_LOW_PD = 4.0      # applied at or below SICR_PD_LOW
SICR_MULTIPLE_HIGH_PD = 2.0     # applied at or above SICR_PD_HIGH
SICR_PD_LOW = 0.001
SICR_PD_HIGH = 0.010

#: IFRS 9 5.5.10 permits an entity to assume no significant increase in credit
#: risk where the instrument has low credit risk at the reporting date. Banks
#: apply it at roughly the investment-grade boundary. Without it, the first
#: year of a stress migrates the whole performing book.
LOW_CREDIT_RISK_PD = 0.010

#: Loss given default is itself macro-sensitive: collateral is worth less in
#: the stress that caused the default. This is the elasticity of LGD to a one
#: standard deviation move in the systematic factor. STYLISED.
LGD_DOWNTURN_ELASTICITY = 0.06


@dataclass
class ECLResult:
    total: float = 0.0
    by_stage: dict[int, float] = field(default_factory=dict)
    by_segment: dict[str, float] = field(default_factory=dict)
    by_scenario: dict[str, float] = field(default_factory=dict)
    #: ECL on the central path alone, for comparison with the weighted number.
    central_only: float = 0.0
    stage2_balance: float = 0.0
    stage3_balance: float = 0.0
    coverage_ratio: float = 0.0

    @property
    def scenario_convexity(self) -> float:
        """How much the probability weighting adds over the central path."""
        return self.total - self.central_only


def _rho(segment: str) -> float:
    return SEGMENT_RHO.get(segment, DEFAULT_RHO)


def sicr_relative_multiple(origination_pd: float) -> float:
    """The relative SICR threshold for an exposure of this origination PD."""
    if origination_pd <= SICR_PD_LOW:
        return SICR_MULTIPLE_LOW_PD
    if origination_pd >= SICR_PD_HIGH:
        return SICR_MULTIPLE_HIGH_PD
    span = math.log(SICR_PD_HIGH) - math.log(SICR_PD_LOW)
    w = (math.log(origination_pd) - math.log(SICR_PD_LOW)) / span
    return SICR_MULTIPLE_LOW_PD - (SICR_MULTIPLE_LOW_PD - SICR_MULTIPLE_HIGH_PD) * w


def _downturn_lgd(lgd: float, z: float) -> float:
    """Raise LGD as the systematic factor deteriorates."""
    return clamp(lgd - LGD_DOWNTURN_ELASTICITY * z, 0.01, 1.0)


def _amortised_ead(e: CreditExposure, t: int) -> float:
    """Exposure at default in year t, on straight-line amortisation to maturity.

    Revolving facilities do not amortise; term loans do. Undrawn amounts are
    brought in at a behavioural drawdown assumption rather than the regulatory
    CCF, which is what IFRS 9 requires.
    """
    life = max(e.behavioural_life_years, 1.0)
    if e.exposure_class in (ExposureClass.RETAIL_TRANSACTOR,):
        drawn = e.drawn
    else:
        drawn = e.drawn * max(0.0, 1.0 - (t - 1) / life)
    expected_drawdown = 0.50 * e.undrawn
    return drawn + expected_drawdown


def exposure_ecl(
    e: CreditExposure, scenario: Scenario, start_year: int, horizon_years: int | None = None
) -> float:
    """ECL for one exposure under one scenario path."""
    if e.stage is IFRS9Stage.STAGE_3:
        # Credit-impaired: the loss is the unrecovered balance, discounted over
        # the workout period rather than the contractual life.
        z = systematic_factor(scenario.state(start_year), e.segment)
        lgd = _downturn_lgd(e.lgd, z)
        workout_years = 2.0
        return e.drawn * lgd / (1.0 + e.effective_rate) ** workout_years

    if horizon_years is None:
        horizon_years = 1 if e.stage is IFRS9Stage.STAGE_1 else max(
            1, int(round(e.behavioural_life_years))
        )

    rho = _rho(e.segment)
    survival = 1.0
    ecl = 0.0
    for t in range(1, horizon_years + 1):
        state = scenario.state(start_year + t - 1)
        z = systematic_factor(state, e.segment)
        pd_t = conditional_pd(e.pd, z, rho)
        marginal_pd = survival * pd_t
        lgd = _downturn_lgd(e.lgd, z)
        ead = _amortised_ead(e, t)
        discount = (1.0 + e.effective_rate) ** t
        ecl += marginal_pd * lgd * ead / discount
        survival *= (1.0 - pd_t)
    return ecl


def assess_sicr(
    e: CreditExposure, scenario: Scenario, start_year: int, origination_pd: float | None = None
) -> IFRS9Stage:
    """Decide the stage for one exposure under the current macro state."""
    if e.stage is IFRS9Stage.STAGE_3 or e.is_defaulted:
        return IFRS9Stage.STAGE_3

    origination_pd = origination_pd if origination_pd is not None else e.pd
    z = systematic_factor(scenario.state(start_year), e.segment)
    current_pd = conditional_pd(e.pd, z, _rho(e.segment))

    # Low credit risk exemption: still investment grade, so no stage transfer.
    if current_pd < LOW_CREDIT_RISK_PD:
        return IFRS9Stage.STAGE_1

    relative = current_pd > sicr_relative_multiple(origination_pd) * origination_pd
    absolute = (current_pd - origination_pd) > SICR_ABSOLUTE_INCREASE
    if relative and absolute:
        return IFRS9Stage.STAGE_2
    return IFRS9Stage.STAGE_1


def sicr_threshold_pd(origination_pd: float) -> float:
    """The PD above which an obligor fails the SICR test."""
    return max(
        LOW_CREDIT_RISK_PD,
        sicr_relative_multiple(origination_pd) * origination_pd,
        origination_pd + SICR_ABSOLUTE_INCREASE,
    )


def stage2_share(
    e: CreditExposure, scenario: Scenario, start_year: int,
    origination_pd: float | None = None,
) -> float:
    """Fraction of a pool that has suffered a significant increase in credit risk.

    Treating each pool as one homogeneous exposure makes stage transfer
    all-or-nothing — the entire book moves to stage 2 on the same day, which is
    not what any bank reports. Real portfolios migrate gradually because obligor
    PDs are dispersed around the pool mean.

    Assuming log PD is normally distributed within the pool with standard
    deviation `pd_dispersion`, and calibrating the median so the pool mean
    matches the conditioned PD, the stage 2 share is the probability that an
    obligor's PD exceeds the SICR threshold.
    """
    if e.stage is IFRS9Stage.STAGE_3 or e.is_defaulted:
        return 0.0

    origination_pd = origination_pd if origination_pd is not None else e.pd
    z = systematic_factor(scenario.state(start_year), e.segment)
    mean_pd = conditional_pd(e.pd, z, _rho(e.segment))
    threshold = sicr_threshold_pd(origination_pd)

    sigma = max(e.pd_dispersion, 1e-6)
    mu = math.log(max(mean_pd, 1e-12)) - 0.5 * sigma * sigma
    return clamp(1.0 - norm_cdf((math.log(threshold) - mu) / sigma), 0.0, 1.0)


def portfolio_ecl(
    exposures: list[CreditExposure],
    scenarios: dict[str, Scenario],
    start_year: int,
    central: str = "baseline",
    restage: bool = True,
) -> ECLResult:
    """Probability-weighted ECL across the scenario set.

    `restage` re-runs the SICR test under the central scenario before measuring,
    which is what produces the stage 1 -> stage 2 migration that dominates the
    first year of a downturn.
    """
    res = ECLResult()
    total_weight = sum(s.weight for s in scenarios.values()) or 1.0
    central_sc = scenarios.get(central) or next(iter(scenarios.values()))

    # The share of each pool in stage 2 is set under the central scenario, then
    # held while ECL is measured across the scenario set — a bank re-stages on
    # its central view, not separately in each scenario.
    shares: dict[int, float] = {}
    if restage:
        for e in exposures:
            share = stage2_share(e, central_sc, start_year)
            shares[id(e)] = share
            if e.stage is not IFRS9Stage.STAGE_3:
                e.stage = IFRS9Stage.STAGE_2 if share >= 0.5 else IFRS9Stage.STAGE_1
    else:
        for e in exposures:
            shares[id(e)] = 1.0 if e.stage is IFRS9Stage.STAGE_2 else 0.0

    def blended(e: CreditExposure, sc: Scenario) -> float:
        """ECL for a pool that is part 12-month and part lifetime."""
        if e.stage is IFRS9Stage.STAGE_3 or e.is_defaulted:
            return exposure_ecl(e, sc, start_year)
        share = shares.get(id(e), 0.0)
        lifetime_horizon = max(1, int(round(e.behavioural_life_years)))
        twelve_month = exposure_ecl(e, sc, start_year, horizon_years=1)
        if share <= 0.0:
            return twelve_month
        lifetime = exposure_ecl(e, sc, start_year, horizon_years=lifetime_horizon)
        return share * lifetime + (1.0 - share) * twelve_month

    per_scenario: dict[str, float] = {}
    for name, sc in scenarios.items():
        per_scenario[name] = sum(blended(e, sc) for e in exposures)

    res.by_scenario = per_scenario
    res.total = sum(per_scenario[n] * scenarios[n].weight for n in scenarios) / total_weight
    res.central_only = per_scenario.get(central, res.total)

    # Attribute the weighted total back to stages and segments in proportion to
    # each exposure's central-scenario ECL, so the splits sum to the total.
    per_exposure = [(e, blended(e, central_sc)) for e in exposures]
    central_total = sum(v for _, v in per_exposure) or 1.0
    scale = res.total / central_total

    for e, v in per_exposure:
        allocated = v * scale
        e.provision = allocated
        res.by_stage[int(e.stage)] = res.by_stage.get(int(e.stage), 0.0) + allocated
        res.by_segment[e.segment] = res.by_segment.get(e.segment, 0.0) + allocated
        if e.stage is IFRS9Stage.STAGE_3:
            res.stage3_balance += e.drawn
        else:
            res.stage2_balance += shares.get(id(e), 0.0) * e.drawn

    gross = sum(e.drawn for e in exposures)
    res.coverage_ratio = safe_div(res.total, gross)
    return res


def impairment_charge(opening_ecl: float, closing_ecl: float, write_offs: float = 0.0) -> float:
    """The P&L charge: the movement in the balance-sheet provision, plus
    write-offs taken directly. A release shows as a negative charge."""
    return (closing_ecl - opening_ecl) + write_offs
