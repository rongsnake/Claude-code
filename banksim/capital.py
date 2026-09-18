"""
Own funds, risk-weighted assets, the output floor, buffers, MDA and leverage.

This is where the separate risk engines meet. The order of operations matters
and is easy to get wrong, so it is spelled out:

  1. Each risk type produces RWAs on the firm's **live** approach (IRB where
     permitted, FRTB-SA, SA-CCR, BA-CVA, SA op risk) and, in parallel, on an
     **all-standardised** basis.
  2. Total RWAs = max(live total, floor% x all-SA total). This is the output
     floor: from 1 January 2027 it starts at 60% and steps up to 72.5% by
     1 January 2030.
  3. Own funds are built bottom-up: CET1 less deductions, then AT1, then Tier 2
     (including the IRB excess-provision add-back).
  4. Requirements are stacked: Pillar 1, then Pillar 2A, then the combined
     buffer requirement, then the PRA buffer.
  5. The distance into the combined buffer determines the maximum distributable
     amount, which is what actually constrains dividends and buybacks.
  6. Separately, the UK leverage ratio binds against a non-risk-based exposure
     measure, and MREL binds against both.

Which of (2), (5) and (6) is the binding constraint is the single most
interesting output of the whole model, and differs between a lender and a
markets-led bank.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .units import clamp, pct, safe_div

# ---------------------------------------------------------------------------
# Output floor
# ---------------------------------------------------------------------------

#: UK output floor transitional path, as finalised in PRA PS1/26 (20 Jan 2026).
#: Basel 3.1 applies in the UK from 1 January 2027; the floor starts at 60% and
#: reaches its fully-loaded 72.5% on 1 January 2030. (FRTB internal models are
#: deferred a further year, to 1 January 2028, but that affects which approach
#: a firm may use, not the floor itself.)
OUTPUT_FLOOR_PATH = {
    2027: 0.600,
    2028: 0.650,
    2029: 0.700,
    2030: 0.725,
}
OUTPUT_FLOOR_FULLY_LOADED = 0.725
BASEL_31_START_YEAR = 2027


def output_floor_rate(year: int) -> float:
    """The floor applying in a given calendar year. Zero before Basel 3.1."""
    if year < BASEL_31_START_YEAR:
        return 0.0
    if year >= max(OUTPUT_FLOOR_PATH):
        return OUTPUT_FLOOR_FULLY_LOADED
    return OUTPUT_FLOOR_PATH[year]


# ---------------------------------------------------------------------------
# RWAs
# ---------------------------------------------------------------------------


@dataclass
class RWABreakdown:
    """RWAs by risk type, on the live approach and on an all-SA basis."""

    credit: float = 0.0
    counterparty_credit: float = 0.0
    cva: float = 0.0
    market: float = 0.0
    operational: float = 0.0
    securitisation: float = 0.0
    other: float = 0.0

    # All-standardised comparators for the output floor.
    credit_sa: float = 0.0
    counterparty_credit_sa: float = 0.0
    cva_sa: float = 0.0
    market_sa: float = 0.0
    operational_sa: float = 0.0
    securitisation_sa: float = 0.0

    @property
    def live_total(self) -> float:
        return (self.credit + self.counterparty_credit + self.cva + self.market
                + self.operational + self.securitisation + self.other)

    @property
    def sa_total(self) -> float:
        return (self.credit_sa + self.counterparty_credit_sa + self.cva_sa
                + self.market_sa + self.operational_sa + self.securitisation_sa
                + self.other)

    def total(self, year: int) -> float:
        """RWAs after the output floor."""
        return max(self.live_total, output_floor_rate(year) * self.sa_total)

    def floor_bites_by(self, year: int) -> float:
        """How much extra RWA the floor adds. Zero when the floor is not binding."""
        return max(0.0, output_floor_rate(year) * self.sa_total - self.live_total)

    def as_dict(self) -> dict[str, float]:
        return {
            "credit": self.credit,
            "counterparty_credit": self.counterparty_credit,
            "cva": self.cva,
            "market": self.market,
            "operational": self.operational,
            "securitisation": self.securitisation,
            "other": self.other,
        }


# ---------------------------------------------------------------------------
# Own funds
# ---------------------------------------------------------------------------


@dataclass
class OwnFunds:
    """The capital stack, in £m, before and after regulatory deductions."""

    # CET1 items
    ordinary_shares: float = 0.0
    share_premium: float = 0.0
    retained_earnings: float = 0.0
    other_reserves: float = 0.0
    accumulated_oci: float = 0.0

    # CET1 deductions (entered as positive numbers, subtracted below)
    goodwill_intangibles: float = 0.0
    deferred_tax_future_profits: float = 0.0
    #: IRB expected loss in excess of accounting provisions.
    irb_shortfall: float = 0.0
    #: Additional valuation adjustment on fair-valued positions (prudent
    #: valuation). A material deduction for a markets-led bank.
    prudent_valuation_ava: float = 0.0
    defined_benefit_pension_asset: float = 0.0
    significant_investments: float = 0.0
    other_cet1_deductions: float = 0.0

    # AT1 and Tier 2
    at1_instruments: float = 0.0
    tier2_instruments: float = 0.0
    #: Accounting provisions in excess of IRB expected loss, addable to Tier 2
    #: up to 0.6% of IRB credit RWAs.
    excess_provisions: float = 0.0

    @property
    def cet1_before_deductions(self) -> float:
        return (self.ordinary_shares + self.share_premium + self.retained_earnings
                + self.other_reserves + self.accumulated_oci)

    @property
    def cet1_deductions(self) -> float:
        return (self.goodwill_intangibles + self.deferred_tax_future_profits
                + self.irb_shortfall + self.prudent_valuation_ava
                + self.defined_benefit_pension_asset + self.significant_investments
                + self.other_cet1_deductions)

    @property
    def cet1(self) -> float:
        return self.cet1_before_deductions - self.cet1_deductions

    @property
    def at1(self) -> float:
        return self.at1_instruments

    @property
    def tier1(self) -> float:
        return self.cet1 + self.at1

    def tier2(self, irb_credit_rwa: float = 0.0) -> float:
        cap = 0.006 * irb_credit_rwa
        return self.tier2_instruments + min(self.excess_provisions, cap)

    def total_capital(self, irb_credit_rwa: float = 0.0) -> float:
        return self.tier1 + self.tier2(irb_credit_rwa)


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

#: Pillar 1 minima as a share of RWAs.
P1_CET1 = 0.045
P1_TIER1 = 0.060
P1_TOTAL = 0.080

#: Pillar 2A must be met in the same proportions as Pillar 1: at least 56.25%
#: CET1 (4.5/8) and at least 75% Tier 1 (6/8).
P2A_CET1_SHARE = 0.5625
P2A_TIER1_SHARE = 0.75

#: Capital conservation buffer — CET1 only.
CCOB = 0.025

#: Maximum distributable amount: payout ratios by quartile of the combined
#: buffer requirement. Falling into the buffer is a distribution constraint,
#: not a breach of a minimum — a distinction worth preserving in the model.
MDA_QUARTILE_PAYOUT = (0.00, 0.20, 0.40, 0.60)


@dataclass
class CapitalRequirements:
    """Firm-specific requirements. P2A and the PRA buffer are supervisory."""

    #: Pillar 2A as a share of RWAs (total capital basis).
    pillar2a: float = 0.030
    #: Institution-specific countercyclical buffer. The FPC has held the UK
    #: rate at its 2% neutral setting through 2026; a firm's own rate is the
    #: exposure-weighted average across the jurisdictions it lends into.
    ccyb: float = 0.020
    #: The higher of the G-SII, O-SII and systemic risk buffer rates.
    systemic_buffer: float = 0.000
    #: PRA buffer (Pillar 2B). Confidential in practice; sits above the CBR
    #: and is not an MDA trigger, but using it invites supervisory action.
    pra_buffer: float = 0.010

    @property
    def combined_buffer(self) -> float:
        return CCOB + self.ccyb + self.systemic_buffer

    @property
    def cet1_minimum(self) -> float:
        """CET1 required by Pillar 1 and Pillar 2A, before buffers."""
        return P1_CET1 + P2A_CET1_SHARE * self.pillar2a

    @property
    def tier1_minimum(self) -> float:
        return P1_TIER1 + P2A_TIER1_SHARE * self.pillar2a

    @property
    def total_minimum(self) -> float:
        return P1_TOTAL + self.pillar2a

    @property
    def cet1_with_buffers(self) -> float:
        """The headline "CET1 requirement" a bank reports to investors."""
        return self.cet1_minimum + self.combined_buffer

    @property
    def cet1_with_pra_buffer(self) -> float:
        return self.cet1_with_buffers + self.pra_buffer


# ---------------------------------------------------------------------------
# Leverage
# ---------------------------------------------------------------------------


@dataclass
class LeverageConfig:
    """The UK leverage regime, in its current and its proposed form.

    The current UK minimum is 3.25% rather than Basel's 3% because the UK
    exposure measure excludes qualifying central bank claims — the higher rate
    offsets the smaller denominator.

    In 2026 the FPC set out a package it intends to consult on: cut the minimum
    to 3%, remove the countercyclical leverage buffer, recalibrate the additional
    leverage ratio buffer to 50% of the risk-weighted systemic buffer (the Basel
    calibration, up from 35%), and add a releasable 0.25% general leverage
    buffer. Set `regime="fpc_2026_proposal"` to model it.
    """

    regime: str = "current_uk"
    #: Whether the firm is in scope of the UK leverage ratio requirement at all.
    in_scope: bool = True

    @property
    def minimum(self) -> float:
        return 0.0325 if self.regime == "current_uk" else 0.030

    @property
    def alrb_share(self) -> float:
        """Additional leverage ratio buffer as a share of the systemic buffer."""
        return 0.35 if self.regime == "current_uk" else 0.50

    @property
    def cclb_share(self) -> float:
        """Countercyclical leverage buffer as a share of the CCyB. Removed
        under the FPC's proposal."""
        return 0.35 if self.regime == "current_uk" else 0.0

    @property
    def general_buffer(self) -> float:
        return 0.0 if self.regime == "current_uk" else 0.0025

    def requirement(self, req: CapitalRequirements) -> float:
        return (self.minimum
                + self.alrb_share * req.systemic_buffer
                + self.cclb_share * req.ccyb
                + self.general_buffer)


@dataclass
class ExposureMeasure:
    """The leverage ratio denominator, £m."""

    on_balance_sheet: float = 0.0          # excluding derivatives and SFTs
    derivative_exposure: float = 0.0       # SA-CCR based
    sft_exposure: float = 0.0
    off_balance_sheet: float = 0.0         # after CCFs, minimum 10%
    #: The UK regime permits exclusion of claims on central banks where matched
    #: by deposits of the same currency and equal or longer maturity.
    central_bank_claims_excluded: float = 0.0

    @property
    def total(self) -> float:
        return max(
            0.0,
            self.on_balance_sheet + self.derivative_exposure + self.sft_exposure
            + self.off_balance_sheet - self.central_bank_claims_excluded,
        )


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


@dataclass
class CapitalPosition:
    """Everything a Pillar 3 key-metrics table (UK KM1) needs, computed once."""

    year: int
    own_funds: OwnFunds
    rwa: RWABreakdown
    requirements: CapitalRequirements
    exposure_measure: ExposureMeasure
    leverage_cfg: LeverageConfig = field(default_factory=LeverageConfig)
    #: MREL requirement as a share of RWAs, set by the resolution authority.
    mrel_requirement_rwa: float = 0.0
    mrel_resources: float = 0.0

    # -- RWAs -------------------------------------------------------------
    @property
    def total_rwa(self) -> float:
        return self.rwa.total(self.year)

    @property
    def output_floor_impact(self) -> float:
        return self.rwa.floor_bites_by(self.year)

    @property
    def output_floor_binding(self) -> bool:
        return self.output_floor_impact > 0.0

    @property
    def output_floor_headroom(self) -> float:
        """RWAs by which the live calculation could still fall before the floor
        starts to bind, in £m. Negative means the floor is already binding.

        This is the number that tells an IRB firm whether new model approvals
        are worth pursuing: below the floor, a better model buys nothing.
        """
        return self.rwa.live_total - output_floor_rate(self.year) * self.rwa.sa_total

    # -- Ratios -----------------------------------------------------------
    @property
    def cet1_ratio(self) -> float:
        return safe_div(self.own_funds.cet1, self.total_rwa)

    @property
    def tier1_ratio(self) -> float:
        return safe_div(self.own_funds.tier1, self.total_rwa)

    @property
    def total_capital_ratio(self) -> float:
        return safe_div(self.own_funds.total_capital(self.rwa.credit), self.total_rwa)

    @property
    def leverage_ratio(self) -> float:
        return safe_div(self.own_funds.tier1, self.exposure_measure.total)

    @property
    def leverage_requirement(self) -> float:
        return self.leverage_cfg.requirement(self.requirements)

    @property
    def mrel_ratio(self) -> float:
        return safe_div(self.mrel_resources, self.total_rwa)

    # -- Headroom ---------------------------------------------------------
    @property
    def cet1_headroom_pct(self) -> float:
        """CET1 ratio less the requirement including buffers, in decimals."""
        return self.cet1_ratio - self.requirements.cet1_with_buffers

    @property
    def cet1_headroom_gbp_m(self) -> float:
        return self.cet1_headroom_pct * self.total_rwa

    @property
    def leverage_headroom_pct(self) -> float:
        if not self.leverage_cfg.in_scope:
            return float("inf")
        return self.leverage_ratio - self.leverage_requirement

    @property
    def mrel_headroom_pct(self) -> float:
        if self.mrel_requirement_rwa <= 0:
            return float("inf")
        return self.mrel_ratio - self.mrel_requirement_rwa

    @property
    def headroom_gbp_m(self) -> dict[str, float]:
        """Headroom against each requirement, in pounds.

        The three requirements have different denominators, so comparing their
        percentage headrooms directly is meaningless — 1pp of leverage headroom
        and 1pp of CET1 headroom are different amounts of money. Converting
        each to cash is the only honest comparison.
        """
        out = {"risk_weighted_cet1": self.cet1_headroom_pct * self.total_rwa}
        if self.leverage_cfg.in_scope:
            out["leverage"] = self.leverage_headroom_pct * self.exposure_measure.total
        if self.mrel_requirement_rwa > 0:
            out["mrel"] = self.mrel_headroom_pct * self.total_rwa
        return out

    @property
    def binding_constraint(self) -> str:
        """Which requirement the firm is closest to breaching, in cash terms."""
        candidates = self.headroom_gbp_m
        return min(candidates, key=candidates.get)

    # -- Distribution constraint -----------------------------------------
    @property
    def cet1_available_for_buffers(self) -> float:
        """CET1 ratio left after meeting Pillar 1 and Pillar 2A.

        CET1 used to plug an AT1 or Tier 2 shortfall is not available to meet
        the buffers — the reason a bank with a thin AT1 layer can be in its
        buffer at a CET1 ratio that looks comfortable.
        """
        rwa = self.total_rwa
        cet1 = safe_div(self.own_funds.cet1, rwa)
        at1 = safe_div(self.own_funds.at1, rwa)
        t2 = safe_div(self.own_funds.tier2(self.rwa.credit), rwa)

        at1_shortfall = max(0.0, (P1_TIER1 - P1_CET1
                                  + (P2A_TIER1_SHARE - P2A_CET1_SHARE) * self.requirements.pillar2a)
                            - at1)
        t2_shortfall = max(0.0, (P1_TOTAL - P1_TIER1
                                 + (1.0 - P2A_TIER1_SHARE) * self.requirements.pillar2a)
                           - t2)
        return cet1 - self.requirements.cet1_minimum - at1_shortfall - t2_shortfall

    @property
    def buffer_usage(self) -> float:
        """Fraction of the combined buffer requirement consumed, 0.0 to 1.0+."""
        cbr = self.requirements.combined_buffer
        if cbr <= 0:
            return 0.0
        available = self.cet1_available_for_buffers
        return clamp(1.0 - safe_div(available, cbr), 0.0, 2.0)

    @property
    def in_buffer(self) -> bool:
        return self.cet1_available_for_buffers < self.requirements.combined_buffer

    @property
    def max_distributable_share(self) -> float:
        """The MDA payout ratio: the share of distributable profit payable out."""
        if not self.in_buffer:
            return 1.0
        cbr = self.requirements.combined_buffer
        available = max(self.cet1_available_for_buffers, 0.0)
        if available <= 0:
            return 0.0
        quartile = min(int(safe_div(available, cbr) * 4.0), 3)
        return MDA_QUARTILE_PAYOUT[quartile]

    def summary(self) -> dict[str, float | str | bool]:
        return {
            "year": self.year,
            "cet1_ratio": self.cet1_ratio,
            "tier1_ratio": self.tier1_ratio,
            "total_capital_ratio": self.total_capital_ratio,
            "leverage_ratio": self.leverage_ratio,
            "leverage_requirement": self.leverage_requirement,
            "total_rwa": self.total_rwa,
            "live_rwa": self.rwa.live_total,
            "sa_rwa": self.rwa.sa_total,
            "output_floor_rate": output_floor_rate(self.year),
            "output_floor_impact": self.output_floor_impact,
            "output_floor_binding": self.output_floor_binding,
            "cet1_requirement": self.requirements.cet1_with_buffers,
            "cet1_headroom_pct": self.cet1_headroom_pct,
            "cet1_headroom_gbp_m": self.cet1_headroom_gbp_m,
            "in_buffer": self.in_buffer,
            "mda_payout_share": self.max_distributable_share,
            "binding_constraint": self.binding_constraint,
            "mrel_ratio": self.mrel_ratio,
        }


# ---------------------------------------------------------------------------
# MREL
# ---------------------------------------------------------------------------


def mrel_requirement(
    req: CapitalRequirements,
    leverage_requirement: float,
    total_rwa: float,
    exposure_measure: float,
    bail_in_strategy: bool = True,
) -> float:
    """MREL as a share of RWAs, for a firm with a bail-in resolution strategy.

    The Bank of England sets MREL for a bail-in firm at the higher of twice the
    risk-weighted minimum (Pillar 1 + Pillar 2A) and twice the leverage
    requirement, with the combined buffer required to be met *above* it. Firms
    below the resolution-strategy threshold have MREL set at their minimum
    capital requirement only; the Bank raised that indicative threshold to
    total assets of £25-40bn, reviewed every three years from 2028.
    """
    risk_weighted = 2.0 * req.total_minimum
    if not bail_in_strategy:
        return req.total_minimum
    leverage_based = safe_div(
        2.0 * leverage_requirement * exposure_measure, total_rwa, default=0.0
    )
    return max(risk_weighted, leverage_based)
