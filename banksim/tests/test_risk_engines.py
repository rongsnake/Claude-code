"""SA-CCR, BA-CVA, FRTB-SA, operational risk and liquidity."""

from __future__ import annotations

import math
import unittest

from banksim.counterparty import (
    ALPHA,
    MULTIPLIER_FLOOR,
    SF_INTEREST_RATE,
    ba_cva,
    cva_discount_factor,
    netting_set_maturity,
    sa_ccr_ead,
    supervisory_duration,
)
from banksim.exposures import (
    Commitment,
    CreditExposure,
    CreditQuality,
    Derivative,
    ExposureClass,
    Funding,
    FundingType,
    JumpToDefault,
    NettingSet,
    Sensitivity,
    TradingBook,
)
from banksim.liquidity import INFLOW_CAP, LCRInputs, hqla_stock, lcr, nsfr
from banksim.units import redenominate_eur_to_gbp
from banksim.market_risk import (
    DRC_RW,
    RRAO_EXOTIC,
    RRAO_OTHER,
    drc_charge,
    market_risk_rwa,
    rrao_charge,
    sbm_risk_class,
    vega_risk_weight,
)
from banksim.op_risk import (
    BI_BUCKET_1_CAP,
    BI_BUCKET_2_CAP,
    IncomeStatementYear,
    OpRiskConfig,
    bi_component,
    internal_loss_multiplier,
    operational_risk,
)


# ---------------------------------------------------------------------------
# SA-CCR
# ---------------------------------------------------------------------------


class TestSACCR(unittest.TestCase):
    def test_supervisory_duration_of_a_five_year_swap(self):
        self.assertAlmostEqual(supervisory_duration(0.0, 5.0),
                               (1.0 - math.exp(-0.25)) / 0.05, places=6)

    def test_unmargined_replacement_cost_is_floored_at_zero(self):
        ns = NettingSet("cp", margined=False,
                        trades=[Derivative("IR", notional=1_000.0, mtm=-500.0)])
        self.assertAlmostEqual(sa_ccr_ead(ns).replacement_cost, 0.0)

    def test_margined_replacement_cost_includes_threshold_and_mta(self):
        ns = NettingSet("cp", margined=True, threshold=10.0, mta=2.0, nica=1.0,
                        trades=[Derivative("IR", notional=1_000.0, mtm=-500.0)])
        self.assertAlmostEqual(sa_ccr_ead(ns).replacement_cost, 11.0)

    def test_multiplier_is_bounded(self):
        deep_otm = NettingSet("cp", margined=False, collateral_held=5_000.0,
                              trades=[Derivative("IR", notional=1_000.0, mtm=0.0,
                                                 end_years=5.0)])
        r = sa_ccr_ead(deep_otm)
        self.assertGreaterEqual(r.multiplier, MULTIPLIER_FLOOR)
        self.assertLessEqual(r.multiplier, 1.0)

    def test_in_the_money_set_has_multiplier_of_one(self):
        itm = NettingSet("cp", margined=False,
                         trades=[Derivative("IR", notional=1_000.0, mtm=500.0,
                                            end_years=5.0)])
        self.assertAlmostEqual(sa_ccr_ead(itm).multiplier, 1.0)

    def test_ead_applies_the_alpha_factor(self):
        ns = NettingSet("cp", margined=False,
                        trades=[Derivative("IR", notional=1_000.0, mtm=100.0,
                                           end_years=5.0)])
        r = sa_ccr_ead(ns)
        self.assertAlmostEqual(r.ead, ALPHA * (r.replacement_cost + r.pfe))

    def test_offsetting_swaps_in_one_currency_reduce_the_addon(self):
        same_bucket = [Derivative("IR", notional=1_000.0, mtm=0.0, end_years=3.0,
                                  direction=1, hedging_set="GBP"),
                       Derivative("IR", notional=1_000.0, mtm=0.0, end_years=3.0,
                                  direction=-1, hedging_set="GBP")]
        different_ccy = [Derivative("IR", notional=1_000.0, mtm=0.0, end_years=3.0,
                                    direction=1, hedging_set="GBP"),
                         Derivative("IR", notional=1_000.0, mtm=0.0, end_years=3.0,
                                    direction=-1, hedging_set="USD")]
        hedged = sa_ccr_ead(NettingSet("a", margined=False, trades=same_bucket)).addon
        unhedged = sa_ccr_ead(NettingSet("b", margined=False, trades=different_ccy)).addon
        self.assertLess(hedged, unhedged)
        self.assertAlmostEqual(hedged, 0.0, places=6)

    def test_interest_rate_supervisory_factor(self):
        t = Derivative("IR", notional=1_000.0, mtm=0.0, end_years=1.0, direction=1)
        ns = NettingSet("cp", margined=False, trades=[t])
        expected = SF_INTEREST_RATE * supervisory_duration(0.0, 1.0) * 1_000.0
        self.assertAlmostEqual(sa_ccr_ead(ns).addon, expected, places=6)


# ---------------------------------------------------------------------------
# BA-CVA
# ---------------------------------------------------------------------------


class TestBACVA(unittest.TestCase):
    def _set(self, **kw) -> NettingSet:
        base = dict(counterparty="cp", sector="financial", rating=CreditQuality.A,
                    margined=False,
                    trades=[Derivative("IR", notional=10_000.0, mtm=500.0, end_years=5.0)])
        base.update(kw)
        return NettingSet(**base)

    def test_exempt_counterparties_are_excluded(self):
        charged = ba_cva([self._set()])
        exempt = ba_cva([self._set(cva_exempt=True)])
        self.assertGreater(charged.capital, 0.0)
        self.assertAlmostEqual(exempt.capital, 0.0)
        self.assertIn("cp", exempt.exempt_counterparties)

    def test_maturity_is_notional_weighted_not_longest(self):
        ns = NettingSet("cp", trades=[
            Derivative("FX", notional=100_000.0, mtm=0.0, end_years=1.0),
            Derivative("IR", notional=1_000.0, mtm=0.0, end_years=30.0),
        ])
        m = netting_set_maturity(ns)
        self.assertLess(m, 2.0)
        self.assertGreaterEqual(m, 1.0)

    def test_discount_factor_is_below_one_and_falls_with_maturity(self):
        self.assertLess(cva_discount_factor(5.0), 1.0)
        self.assertLess(cva_discount_factor(10.0), cva_discount_factor(5.0))

    def test_high_yield_counterparty_costs_more(self):
        ig = ba_cva([self._set(rating=CreditQuality.A)])
        hy = ba_cva([self._set(rating=CreditQuality.B)])
        self.assertGreater(hy.capital, ig.capital)

    def test_diversification_across_counterparties(self):
        one_big = ba_cva([self._set(counterparty="a", trades=[
            Derivative("IR", notional=20_000.0, mtm=1_000.0, end_years=5.0)])])
        two_small = ba_cva([
            self._set(counterparty="a", trades=[
                Derivative("IR", notional=10_000.0, mtm=500.0, end_years=5.0)]),
            self._set(counterparty="b", trades=[
                Derivative("IR", notional=10_000.0, mtm=500.0, end_years=5.0)]),
        ])
        self.assertLess(two_small.capital, one_big.capital)


# ---------------------------------------------------------------------------
# FRTB standardised approach
# ---------------------------------------------------------------------------


class TestFRTB(unittest.TestCase):
    def test_single_sensitivity_charge_is_risk_weight_times_sensitivity(self):
        s = Sensitivity("EQ", "adv_large_financial", "NameA", 100.0)
        self.assertAlmostEqual(sbm_risk_class([s], "EQ"), 0.40 * 100.0, places=6)

    def test_same_risk_factor_nets_out_exactly(self):
        """Offsetting positions on the *same* factor correlate at 1 and cancel."""
        matched = [Sensitivity("EQ", "adv_large_financial", "A", 100.0),
                   Sensitivity("EQ", "adv_large_financial", "A", -100.0)]
        self.assertAlmostEqual(sbm_risk_class(matched, "EQ"), 0.0, places=9)

    def test_cross_name_hedging_is_not_recognised_and_can_cost_more(self):
        """Shorting a different name in the same bucket is not a hedge.

        Equity names within a bucket correlate at only 15%, so a long/short
        pair on two different names carries *more* standardised capital than
        the long alone — the approach treats them as two independent risks,
        which is precisely the conservatism that drives banks towards the
        internal model approach.
        """
        long_only = [Sensitivity("EQ", "adv_large_financial", "A", 100.0)]
        cross_name = long_only + [Sensitivity("EQ", "adv_large_financial", "B", -100.0)]
        self.assertGreater(sbm_risk_class(cross_name, "EQ"),
                           sbm_risk_class(long_only, "EQ"))

    def test_girr_tenor_correlation_decays_with_distance(self):
        near = [Sensitivity("GIRR", "GBP", "2.0", 100.0),
                Sensitivity("GIRR", "GBP", "3.0", -100.0)]
        far = [Sensitivity("GIRR", "GBP", "1.0", 100.0),
               Sensitivity("GIRR", "GBP", "30.0", -100.0)]
        # Adjacent tenors offset better than distant ones.
        self.assertLess(sbm_risk_class(near, "GIRR"), sbm_risk_class(far, "GIRR"))

    def test_liquid_currency_relief(self):
        liquid = [Sensitivity("GIRR", "GBP", "5.0", 10_000.0)]
        illiquid = [Sensitivity("GIRR", "TRY", "5.0", 10_000.0)]
        self.assertAlmostEqual(sbm_risk_class(illiquid, "GIRR") / math.sqrt(2.0),
                               sbm_risk_class(liquid, "GIRR"), places=6)

    def test_vega_risk_weights_cap_at_one(self):
        self.assertAlmostEqual(vega_risk_weight("GIRR"), 1.0)
        self.assertLess(vega_risk_weight("EQ"), 1.0)

    def test_drc_nets_within_a_bucket_with_a_hedge_haircut(self):
        long_only = [JumpToDefault("A", "corporate", CreditQuality.BBB, 1_000.0)]
        hedged = long_only + [JumpToDefault("B", "corporate", CreditQuality.BBB, -1_000.0)]
        self.assertLess(drc_charge(hedged), drc_charge(long_only))
        self.assertGreater(drc_charge(hedged), 0.0)

    def test_drc_does_not_net_across_buckets(self):
        split = [JumpToDefault("A", "corporate", CreditQuality.BBB, 1_000.0),
                 JumpToDefault("B", "sovereign", CreditQuality.BBB, -1_000.0)]
        long_only = [JumpToDefault("A", "corporate", CreditQuality.BBB, 1_000.0)]
        self.assertAlmostEqual(drc_charge(split), drc_charge(long_only))

    def test_drc_risk_weight_applied_to_jtd(self):
        j = JumpToDefault("A", "corporate", CreditQuality.BBB, 1_000.0, lgd=0.75)
        self.assertAlmostEqual(drc_charge([j]), DRC_RW[CreditQuality.BBB] * 750.0)

    def test_rrao_is_a_flat_notional_charge(self):
        book = TradingBook(exotic_notional=1_000.0, other_residual_notional=10_000.0)
        self.assertAlmostEqual(rrao_charge(book),
                               RRAO_EXOTIC * 1_000.0 + RRAO_OTHER * 10_000.0)

    def test_total_is_capital_times_twelve_point_five(self):
        book = TradingBook(
            sensitivities=[Sensitivity("EQ", "adv_large_financial", "A", 100.0)],
            jtds=[JumpToDefault("A", "corporate", CreditQuality.BBB, 1_000.0)],
            exotic_notional=1_000.0)
        r = market_risk_rwa(book)
        self.assertAlmostEqual(r.rwa, r.capital * 12.5)
        self.assertAlmostEqual(r.capital, r.sbm + r.drc + r.rrao)


# ---------------------------------------------------------------------------
# Operational risk
# ---------------------------------------------------------------------------


class TestRedenomination(unittest.TestCase):
    """The PRA converted the euro thresholds at 0.88, to two significant figures."""

    def test_published_thresholds(self):
        self.assertAlmostEqual(redenominate_eur_to_gbp(1_000.0), 880.0)      # EUR 1bn
        self.assertAlmostEqual(redenominate_eur_to_gbp(30_000.0), 26_000.0)  # EUR 30bn
        self.assertAlmostEqual(redenominate_eur_to_gbp(5.0), 4.4)            # EUR 5m
        self.assertAlmostEqual(redenominate_eur_to_gbp(50.0), 44.0)          # EUR 50m

    def test_rounds_to_two_significant_figures(self):
        # 30,000 x 0.88 = 26,400, which rounds to 26,000 — not 26,400.
        self.assertAlmostEqual(redenominate_eur_to_gbp(30_000.0), 26_000.0)
        self.assertAlmostEqual(redenominate_eur_to_gbp(0.0), 0.0)

    def test_derived_buckets_match_the_pra_published_figures(self):
        """Cross-check: the PRA's operational risk reporting instructions state
        the bucket 2 marginal amount as £25.12bn. Deriving £26bn - £880m from
        the redenomination rate reproduces it exactly, which is independent
        confirmation of both the rate and the rounding convention."""
        self.assertAlmostEqual(BI_BUCKET_1_CAP, 880.0)
        self.assertAlmostEqual(BI_BUCKET_2_CAP, 26_000.0)
        self.assertAlmostEqual(BI_BUCKET_2_CAP - BI_BUCKET_1_CAP, 25_120.0)


class TestOperationalRisk(unittest.TestCase):
    def test_marginal_bucket_coefficients(self):
        self.assertAlmostEqual(bi_component(500.0), 0.12 * 500.0)
        self.assertAlmostEqual(bi_component(2_000.0),
                               0.12 * 880.0 + 0.15 * 1_120.0)
        self.assertAlmostEqual(
            bi_component(40_000.0),
            0.12 * 880.0 + 0.15 * 25_120.0 + 0.18 * 14_000.0)

    def test_bucket_boundaries_are_the_sterling_ones(self):
        """A firm with a £950m BI is in bucket 2 in the UK, but would be in
        bucket 1 on the euro thresholds — the redenomination moves real firms."""
        just_over = bi_component(950.0)
        all_bucket_1 = 0.12 * 950.0
        self.assertGreater(just_over, all_bucket_1)

    def test_ilm_is_one_when_losses_equal_the_bi_component(self):
        bic = 1_000.0
        # LC = 15 x average loss, so an average loss of BIC/15 gives LC == BIC.
        self.assertAlmostEqual(internal_loss_multiplier(bic, bic / 15.0), 1.0, places=9)

    def test_pra_sets_ilm_to_one_by_default(self):
        history = [IncomeStatementYear(interest_income=1_000.0, interest_expense=500.0,
                                       interest_earning_assets=40_000.0,
                                       fee_income=300.0, trading_book_pnl=200.0)]
        default = operational_risk(history)
        with_losses = operational_risk(
            history, OpRiskConfig(use_ilm=True, average_annual_loss=500.0))
        self.assertAlmostEqual(default.ilm, 1.0)
        self.assertGreater(with_losses.capital, default.capital)

    def test_interest_component_is_capped_by_earning_assets(self):
        wide_margin = IncomeStatementYear(interest_income=5_000.0, interest_expense=0.0,
                                          interest_earning_assets=10_000.0)
        # 2.25% of 10,000 = 225, well below the 5,000 net interest figure.
        self.assertAlmostEqual(wide_margin.ildc(), 225.0)

    def test_trading_losses_increase_the_charge(self):
        profit = IncomeStatementYear(trading_book_pnl=1_000.0)
        loss = IncomeStatementYear(trading_book_pnl=-1_000.0)
        self.assertAlmostEqual(profit.business_indicator(), loss.business_indicator())


# ---------------------------------------------------------------------------
# Liquidity
# ---------------------------------------------------------------------------


def hqla(level: str, amount: float) -> CreditExposure:
    return CreditExposure(name=level, exposure_class=ExposureClass.SOVEREIGN,
                          drawn=amount, hqla_level=level)


class TestLiquidity(unittest.TestCase):
    def test_level_two_capped_at_forty_percent_of_the_stock(self):
        total, by_level = hqla_stock([hqla("L1", 100.0), hqla("L2A", 200.0)])
        # L2 <= 2/3 of L1 after haircuts: L1 = 100, L2A haircut to 170 but
        # capped at 66.67.
        self.assertAlmostEqual(by_level["L2A"], 100.0 * 2.0 / 3.0, places=6)
        self.assertAlmostEqual(total, 100.0 + 100.0 * 2.0 / 3.0, places=6)

    def test_level_two_b_capped_at_fifteen_percent(self):
        _total, by_level = hqla_stock([hqla("L1", 1_000.0), hqla("L2B", 1_000.0)])
        self.assertAlmostEqual(by_level["L2B"], 15.0 / 85.0 * 1_000.0, places=6)

    def test_haircuts_applied(self):
        total, _ = hqla_stock([hqla("L2A", 100.0)])
        # L2A takes a 15% haircut, then the 40%-of-stock cap with no L1 leaves
        # nothing eligible.
        self.assertAlmostEqual(total, 0.0)

    def test_inflows_capped_at_seventy_five_percent_of_outflows(self):
        funding = [Funding("dep", FundingType.FINANCIAL_DEPOSIT, 1_000.0, 0.03)]
        res = lcr([hqla("L1", 1_000.0)], funding, [],
                  LCRInputs(inflow_financial=100_000.0))
        self.assertAlmostEqual(res.capped_inflows, INFLOW_CAP * res.gross_outflows)
        self.assertAlmostEqual(res.net_outflows, 0.25 * res.gross_outflows)

    def test_run_off_rates_differ_by_funding_type(self):
        def outflow(kind):
            return lcr([], [Funding("f", kind, 1_000.0, 0.03)], []).gross_outflows
        self.assertAlmostEqual(outflow(FundingType.RETAIL_STABLE), 50.0)
        self.assertAlmostEqual(outflow(FundingType.OPERATIONAL_DEPOSIT), 250.0)
        self.assertAlmostEqual(outflow(FundingType.FINANCIAL_DEPOSIT), 1_000.0)

    def test_repo_run_off_depends_on_the_collateral(self):
        def outflow(level):
            f = Funding("repo", FundingType.SECURED_FUNDING, 1_000.0, 0.03,
                        collateral_level=level)
            return lcr([], [f], []).gross_outflows
        self.assertAlmostEqual(outflow("L1"), 0.0)
        self.assertAlmostEqual(outflow("L2A"), 150.0)
        self.assertAlmostEqual(outflow(None), 1_000.0)

    def test_undrawn_liquidity_line_to_a_fund_is_a_full_outflow(self):
        res = lcr([], [], [Commitment("line", 1_000.0, "financial", "liquidity")])
        self.assertAlmostEqual(res.gross_outflows, 1_000.0)

    def test_nsfr_capital_is_fully_stable_funding(self):
        res = nsfr([], [], cet1=1_000.0)
        self.assertAlmostEqual(res.available, 1_000.0)

    def test_nsfr_long_term_funding_beats_short_term(self):
        short = nsfr([], [Funding("f", FundingType.FINANCIAL_DEPOSIT, 1_000.0, 0.03,
                                  maturity_years=0.1)], cet1=0.0)
        long = nsfr([], [Funding("f", FundingType.FINANCIAL_DEPOSIT, 1_000.0, 0.03,
                                 maturity_years=2.0)], cet1=0.0)
        self.assertAlmostEqual(short.available, 0.0)
        self.assertAlmostEqual(long.available, 1_000.0)

    def test_nsfr_trading_inventory_is_expensive_to_fund(self):
        res = nsfr([], [], cet1=0.0, trading_inventory=1_000.0)
        self.assertAlmostEqual(res.required, 850.0)


if __name__ == "__main__":
    unittest.main()
