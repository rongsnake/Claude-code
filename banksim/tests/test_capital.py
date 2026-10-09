"""Own funds, the output floor, buffers, the MDA and leverage."""

from __future__ import annotations

import unittest

from banksim.capital import (
    CCOB,
    P1_TOTAL,
    lending_adjustment,
    CapitalPosition,
    CapitalRequirements,
    ExposureMeasure,
    LeverageConfig,
    OwnFunds,
    RWABreakdown,
    mrel_requirement,
    output_floor_rate,
)


def own_funds(cet1_before=10_000.0, deductions=0.0, at1=1_500.0, t2=2_000.0) -> OwnFunds:
    return OwnFunds(ordinary_shares=cet1_before, other_cet1_deductions=deductions,
                    at1_instruments=at1, tier2_instruments=t2)


def position(cet1_before=10_000.0, live=60_000.0, sa=80_000.0, year=2027,
             exposure=200_000.0, **req_kw) -> CapitalPosition:
    return CapitalPosition(
        year=year,
        own_funds=own_funds(cet1_before),
        rwa=RWABreakdown(credit=live, credit_sa=sa),
        requirements=CapitalRequirements(**req_kw),
        exposure_measure=ExposureMeasure(on_balance_sheet=exposure),
    )


class TestOutputFloor(unittest.TestCase):
    def test_transitional_path(self):
        self.assertAlmostEqual(output_floor_rate(2026), 0.000)  # pre Basel 3.1
        self.assertAlmostEqual(output_floor_rate(2027), 0.600)
        self.assertAlmostEqual(output_floor_rate(2028), 0.650)
        self.assertAlmostEqual(output_floor_rate(2029), 0.700)
        self.assertAlmostEqual(output_floor_rate(2030), 0.725)
        self.assertAlmostEqual(output_floor_rate(2035), 0.725)

    def test_floor_binds_when_modelled_rwas_are_low_enough(self):
        # 60% of 80,000 = 48,000, below the live 60,000: not binding.
        p = position(live=60_000.0, sa=80_000.0, year=2027)
        self.assertFalse(p.output_floor_binding)
        self.assertAlmostEqual(p.total_rwa, 60_000.0)
        # Same book on a much better model: the floor takes over.
        p = position(live=40_000.0, sa=80_000.0, year=2027)
        self.assertTrue(p.output_floor_binding)
        self.assertAlmostEqual(p.total_rwa, 48_000.0)
        self.assertAlmostEqual(p.output_floor_impact, 8_000.0)

    def test_floor_headroom_sign(self):
        loose = position(live=60_000.0, sa=80_000.0, year=2027)
        tight = position(live=40_000.0, sa=80_000.0, year=2027)
        self.assertGreater(loose.output_floor_headroom, 0)
        self.assertLess(tight.output_floor_headroom, 0)

    def test_phase_in_can_turn_a_non_binding_floor_binding(self):
        args = dict(live=50_000.0, sa=80_000.0)
        self.assertFalse(position(year=2027, **args).output_floor_binding)  # 48,000
        self.assertTrue(position(year=2030, **args).output_floor_binding)   # 58,000


class TestOwnFunds(unittest.TestCase):
    def test_deductions_reduce_cet1_only(self):
        of = own_funds(cet1_before=10_000.0, deductions=1_000.0)
        self.assertAlmostEqual(of.cet1, 9_000.0)
        self.assertAlmostEqual(of.tier1, 10_500.0)
        self.assertAlmostEqual(of.total_capital(), 12_500.0)

    def test_excess_provisions_capped_at_sixty_bp_of_credit_rwa(self):
        of = own_funds(t2=0.0)
        of.excess_provisions = 1_000.0
        self.assertAlmostEqual(of.tier2(irb_credit_rwa=50_000.0), 300.0)
        self.assertAlmostEqual(of.tier2(irb_credit_rwa=200_000.0), 1_000.0)


class TestRequirements(unittest.TestCase):
    def test_pillar2a_is_split_in_pillar1_proportions(self):
        req = CapitalRequirements(pillar2a_gross=0.04, ccyb=0.0, systemic_buffer=0.0)
        self.assertAlmostEqual(req.cet1_minimum, 0.045 + 0.5625 * 0.04)
        self.assertAlmostEqual(req.tier1_minimum, 0.060 + 0.75 * 0.04)
        self.assertAlmostEqual(req.total_minimum, 0.080 + 0.04)

    def test_combined_buffer_sums_the_three_buffers(self):
        req = CapitalRequirements(ccyb=0.02, systemic_buffer=0.015)
        self.assertAlmostEqual(req.combined_buffer, CCOB + 0.02 + 0.015)

    def test_lending_adjustments_reduce_pillar2a(self):
        req = CapitalRequirements(pillar2a_gross=0.032,
                                  sme_lending_adjustment=0.0008,
                                  infrastructure_lending_adjustment=0.0010)
        self.assertAlmostEqual(req.pillar2a, 0.032 - 0.0008 - 0.0010)

    def test_pillar2a_cannot_go_negative(self):
        req = CapitalRequirements(pillar2a_gross=0.001,
                                  sme_lending_adjustment=0.05)
        self.assertAlmostEqual(req.pillar2a, 0.0)

    def test_lending_adjustment_holds_the_total_requirement_constant(self):
        """The PRA calibrates these so removing the Pillar 1 supporting factor
        does not raise overall capital requirements for the affected lending."""
        gross, rwa, relief = 0.030, 100_000.0, 4_000.0
        adj = lending_adjustment(gross, relief, rwa)
        before = (P1_TOTAL + gross) * (rwa - relief)   # factor still in place
        after = (P1_TOTAL + gross - adj) * rwa         # factor removed, P2A cut
        self.assertAlmostEqual(before, after, places=6)

    def test_no_adjustment_without_affected_lending(self):
        self.assertAlmostEqual(lending_adjustment(0.03, 0.0, 100_000.0), 0.0)

    def test_pra_buffer_sits_above_the_combined_buffer(self):
        req = CapitalRequirements(pra_buffer=0.01)
        self.assertAlmostEqual(req.cet1_with_pra_buffer,
                               req.cet1_with_buffers + 0.01)


class TestMDA(unittest.TestCase):
    def _at_buffer_usage(self, available_share: float) -> CapitalPosition:
        """Build a position whose CET1 available for buffers is a given share
        of the combined buffer requirement."""
        req = CapitalRequirements(pillar2a_gross=0.0, ccyb=0.015, systemic_buffer=0.0)
        cbr = req.combined_buffer
        rwa = 100_000.0
        # CET1 ratio = P1 CET1 + the share of the buffer we want available.
        cet1_ratio = 0.045 + available_share * cbr
        p = CapitalPosition(
            year=2027,
            own_funds=OwnFunds(ordinary_shares=cet1_ratio * rwa,
                               at1_instruments=0.015 * rwa,
                               tier2_instruments=0.020 * rwa),
            rwa=RWABreakdown(credit=rwa, credit_sa=rwa),
            requirements=req,
            exposure_measure=ExposureMeasure(on_balance_sheet=rwa * 3),
        )
        return p

    def test_no_restriction_above_the_buffer(self):
        p = self._at_buffer_usage(1.2)
        self.assertFalse(p.in_buffer)
        self.assertAlmostEqual(p.max_distributable_share, 1.0)

    def test_quartile_payouts(self):
        for share, expected in ((0.10, 0.00), (0.35, 0.20),
                                (0.60, 0.40), (0.85, 0.60)):
            p = self._at_buffer_usage(share)
            self.assertTrue(p.in_buffer, msg=f"share={share}")
            self.assertAlmostEqual(p.max_distributable_share, expected,
                                   msg=f"share={share}")

    def test_at1_shortfall_consumes_buffer_capacity(self):
        """CET1 plugging an AT1 hole is not available to meet the buffers."""
        req = CapitalRequirements(pillar2a_gross=0.0, ccyb=0.0, systemic_buffer=0.0)
        rwa = 100_000.0
        with_at1 = CapitalPosition(
            year=2027,
            own_funds=OwnFunds(ordinary_shares=0.09 * rwa, at1_instruments=0.015 * rwa,
                               tier2_instruments=0.02 * rwa),
            rwa=RWABreakdown(credit=rwa, credit_sa=rwa), requirements=req,
            exposure_measure=ExposureMeasure(on_balance_sheet=rwa * 3))
        without_at1 = CapitalPosition(
            year=2027,
            own_funds=OwnFunds(ordinary_shares=0.09 * rwa, at1_instruments=0.0,
                               tier2_instruments=0.02 * rwa),
            rwa=RWABreakdown(credit=rwa, credit_sa=rwa), requirements=req,
            exposure_measure=ExposureMeasure(on_balance_sheet=rwa * 3))
        self.assertGreater(with_at1.cet1_available_for_buffers,
                           without_at1.cet1_available_for_buffers)


class TestLeverage(unittest.TestCase):
    def test_current_uk_regime(self):
        cfg = LeverageConfig(regime="current_uk")
        req = CapitalRequirements(ccyb=0.02, systemic_buffer=0.01)
        self.assertAlmostEqual(cfg.minimum, 0.0325)
        self.assertAlmostEqual(cfg.requirement(req),
                               0.0325 + 0.35 * 0.01 + 0.35 * 0.02)

    def test_fpc_proposal_lowers_the_minimum_and_drops_the_cclb(self):
        cfg = LeverageConfig(regime="fpc_2026_proposal")
        req = CapitalRequirements(ccyb=0.02, systemic_buffer=0.01)
        self.assertAlmostEqual(cfg.minimum, 0.030)
        self.assertAlmostEqual(cfg.cclb_share, 0.0)
        self.assertAlmostEqual(cfg.requirement(req),
                               0.030 + 0.50 * 0.01 + 0.0025)

    def test_exposure_measure_excludes_matched_central_bank_claims(self):
        em = ExposureMeasure(on_balance_sheet=100_000.0, derivative_exposure=20_000.0,
                             sft_exposure=30_000.0, off_balance_sheet=10_000.0,
                             central_bank_claims_excluded=25_000.0)
        self.assertAlmostEqual(em.total, 135_000.0)


class TestBindingConstraint(unittest.TestCase):
    def test_compared_in_cash_not_percentage_points(self):
        """A percentage point of leverage headroom and a percentage point of
        CET1 headroom are different amounts of money."""
        p = position(cet1_before=10_000.0, live=60_000.0, sa=60_000.0,
                     exposure=300_000.0, pillar2a_gross=0.0, ccyb=0.0)
        headroom = p.headroom_gbp_m
        self.assertAlmostEqual(headroom["risk_weighted_cet1"],
                               p.cet1_headroom_pct * p.total_rwa)
        self.assertAlmostEqual(headroom["leverage"],
                               p.leverage_headroom_pct * p.exposure_measure.total)
        self.assertIn(p.binding_constraint, headroom)


class TestMREL(unittest.TestCase):
    def test_bail_in_firm_takes_twice_the_risk_weighted_minimum(self):
        req = CapitalRequirements(pillar2a_gross=0.03)
        value = mrel_requirement(req, leverage_requirement=0.0325,
                                 total_rwa=60_000.0, exposure_measure=100_000.0)
        self.assertAlmostEqual(value, 2.0 * 0.11)

    def test_leverage_limb_can_bind_for_a_low_density_balance_sheet(self):
        req = CapitalRequirements(pillar2a_gross=0.01)
        value = mrel_requirement(req, leverage_requirement=0.0325,
                                 total_rwa=30_000.0, exposure_measure=400_000.0)
        self.assertAlmostEqual(value, 2.0 * 0.0325 * 400_000.0 / 30_000.0)

    def test_firm_without_a_bail_in_strategy_takes_its_minimum(self):
        req = CapitalRequirements(pillar2a_gross=0.02)
        value = mrel_requirement(req, 0.0325, 10_000.0, 30_000.0,
                                 bail_in_strategy=False)
        self.assertAlmostEqual(value, req.total_minimum)


if __name__ == "__main__":
    unittest.main()
