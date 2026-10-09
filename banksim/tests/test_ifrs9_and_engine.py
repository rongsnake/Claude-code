"""IFRS 9 staging and measurement, the scenario bridge, and the run loop."""

from __future__ import annotations

import copy
import unittest

from banksim.bank import build_bank
from banksim.engine import (
    PD_CYCLICALITY,
    STRESS_SCENARIO_WEIGHT,
    compute_capital_position,
    migrate_defaults,
    migrate_regulatory_pds,
    run_simulation,
    stress_weighted_scenarios,
)
from banksim.exposures import CreditExposure, ExposureClass, IFRS9Stage, IRBApproach
from banksim.ifrs9 import (
    assess_sicr,
    exposure_ecl,
    impairment_charge,
    portfolio_ecl,
)
from banksim.scenario import (
    MacroState,
    conditional_pd,
    standard_scenarios,
    systematic_factor,
)


def loan(**kw) -> CreditExposure:
    base = dict(name="loan", exposure_class=ExposureClass.CORPORATE, drawn=1_000.0,
                approach=IRBApproach.AIRB, pd=0.01, lgd=0.40,
                segment="corporate", behavioural_life_years=5.0, effective_rate=0.06)
    base.update(kw)
    return CreditExposure(**base)


class TestScenarioBridge(unittest.TestCase):
    def test_neutral_factor_reproduces_the_through_the_cycle_pd(self):
        """The bug this guards: the textbook Vasicek conditional PD evaluated
        at Z = 0 sits below the unconditional PD, which silently shrank every
        PD in a neutral scenario."""
        for pd in (0.0005, 0.002, 0.01, 0.05, 0.20):
            for rho in (0.04, 0.12, 0.25):
                self.assertAlmostEqual(conditional_pd(pd, 0.0, rho), pd, places=10)

    def test_adverse_factor_raises_pd_and_benign_lowers_it(self):
        self.assertGreater(conditional_pd(0.01, -2.0), 0.01)
        self.assertLess(conditional_pd(0.01, 2.0), 0.01)

    def test_higher_correlation_means_a_sharper_response(self):
        low = conditional_pd(0.01, -2.0, rho=0.04)
        high = conditional_pd(0.01, -2.0, rho=0.25)
        self.assertGreater(high, low)

    def test_systematic_factor_is_negative_in_the_severe_scenario(self):
        scenarios = standard_scenarios(2027, 5)
        severe = scenarios["acs_severe"].state(2028)
        base = scenarios["baseline"].state(2028)
        for segment in ("corporate", "mortgages", "cre", "leveraged_finance"):
            self.assertLess(systematic_factor(severe, segment),
                            systematic_factor(base, segment), msg=segment)
            self.assertLess(systematic_factor(severe, segment), 0.0, msg=segment)

    def test_segments_respond_to_different_variables(self):
        # Unemployment up, everything else at reference: mortgages suffer more
        # than leveraged finance, which loads on spreads instead.
        shock = MacroState(year=2027, unemployment=0.090)
        self.assertLess(systematic_factor(shock, "mortgages"),
                        systematic_factor(shock, "leveraged_finance"))


class TestIFRS9(unittest.TestCase):
    def setUp(self):
        self.scenarios = standard_scenarios(2027, 5)

    def test_lifetime_ecl_exceeds_twelve_month_ecl(self):
        stage1 = loan(stage=IFRS9Stage.STAGE_1)
        stage2 = loan(stage=IFRS9Stage.STAGE_2)
        sc = self.scenarios["baseline"]
        self.assertGreater(exposure_ecl(stage2, sc, 2027), exposure_ecl(stage1, sc, 2027))

    def test_stress_scenario_produces_a_larger_ecl(self):
        e = loan(stage=IFRS9Stage.STAGE_2)
        base = exposure_ecl(copy.deepcopy(e), self.scenarios["baseline"], 2027)
        severe = exposure_ecl(copy.deepcopy(e), self.scenarios["acs_severe"], 2027)
        self.assertGreater(severe, base)

    def test_stage_three_is_measured_on_the_defaulted_balance(self):
        e = loan(stage=IFRS9Stage.STAGE_3, lgd=0.50)
        ecl = exposure_ecl(e, self.scenarios["baseline"], 2027)
        self.assertGreater(ecl, 0.30 * e.drawn)
        self.assertLess(ecl, e.drawn)

    def test_sicr_needs_both_a_relative_and_an_absolute_increase(self):
        # Investment grade: a large relative rise is still a small absolute one.
        ig = loan(pd=0.0005)
        self.assertIs(assess_sicr(ig, self.scenarios["acs_severe"], 2028),
                      IFRS9Stage.STAGE_1)
        # Sub-investment grade: both limbs are met in the stress.
        hy = loan(pd=0.03, segment="leveraged_finance")
        self.assertIs(assess_sicr(hy, self.scenarios["acs_severe"], 2028),
                      IFRS9Stage.STAGE_2)

    def test_defaulted_exposures_stay_in_stage_three(self):
        e = loan(stage=IFRS9Stage.STAGE_3)
        self.assertIs(assess_sicr(e, self.scenarios["baseline"], 2027),
                      IFRS9Stage.STAGE_3)

    def test_probability_weighting_adds_to_the_central_path(self):
        """ECL is convex in the macro path, so the weighted average exceeds the
        ECL of the central scenario. That gap is the whole reason the standard
        requires multiple scenarios."""
        book = [loan(pd=0.02, segment="leveraged_finance", stage=IFRS9Stage.STAGE_2)]
        res = portfolio_ecl(book, self.scenarios, 2027, restage=False)
        self.assertGreater(res.total, res.central_only)
        self.assertGreater(res.scenario_convexity, 0.0)

    def test_provisions_are_allocated_to_sum_to_the_total(self):
        book = [loan(name=f"l{i}", pd=0.005 * (i + 1)) for i in range(4)]
        res = portfolio_ecl(book, self.scenarios, 2027)
        self.assertAlmostEqual(sum(e.provision for e in book), res.total, places=6)

    def test_impairment_charge_is_the_provision_movement_plus_write_offs(self):
        self.assertAlmostEqual(impairment_charge(100.0, 150.0, 20.0), 70.0)
        self.assertAlmostEqual(impairment_charge(150.0, 100.0), -50.0)


class TestEngineMechanics(unittest.TestCase):
    def setUp(self):
        self.bank = build_bank()
        self.scenarios = standard_scenarios(2027, 5)

    def test_stress_reweighting_sums_to_one(self):
        out = stress_weighted_scenarios(self.scenarios, self.scenarios["acs_severe"])
        self.assertAlmostEqual(sum(s.weight for s in out.values()), 1.0, places=9)
        self.assertAlmostEqual(out["acs_severe"].weight, STRESS_SCENARIO_WEIGHT)

    def test_pd_migration_is_dampened(self):
        """IRB PDs are hybrids, so they move by less than the full
        point-in-time swing."""
        e = self.bank.exposures[4]
        ttc = e.pd
        severe = self.scenarios["acs_severe"].state(2028)
        migrate_regulatory_pds(self.bank, severe)
        point_in_time = conditional_pd(ttc, systematic_factor(severe, e.segment), 0.12)
        self.assertGreater(e.pd_regulatory, ttc)
        self.assertLess(e.pd_regulatory, point_in_time)
        self.assertLess(PD_CYCLICALITY, 1.0)

    def test_defaults_move_balances_into_the_non_performing_pool(self):
        npe = next(e for e in self.bank.exposures if e.stage is IFRS9Stage.STAGE_3)
        performing_before = sum(e.drawn for e in self.bank.exposures if e is not npe)
        severe = self.scenarios["acs_severe"].state(2027)
        write_offs = migrate_defaults(self.bank, severe)
        performing_after = sum(e.drawn for e in self.bank.exposures if e is not npe)
        self.assertLess(performing_after, performing_before)
        self.assertGreater(write_offs, 0.0)

    def test_capital_positions_do_not_alias_the_banks_own_funds(self):
        """Each reported year must be a snapshot. Before this was fixed, later
        retained earnings retrospectively rewrote earlier years' ratios."""
        result = run_simulation(self.bank, self.scenarios["baseline"],
                                self.scenarios, start_year=2027, years=3)
        first = result.periods[0]
        recorded = first.capital.cet1_ratio
        self.bank.own_funds.retained_earnings += 5_000.0
        self.assertAlmostEqual(first.capital.cet1_ratio, recorded)


class TestSimulation(unittest.TestCase):
    def setUp(self):
        self.scenarios = standard_scenarios(2027, 5)

    def _run(self, name: str):
        return run_simulation(build_bank(), self.scenarios[name], self.scenarios,
                              start_year=2027, years=5)

    def test_severe_stress_is_worse_on_every_measure(self):
        base = self._run("baseline")
        severe = self._run("acs_severe")
        self.assertLess(severe.min_cet1_ratio, base.min_cet1_ratio)
        self.assertLess(severe.min_leverage_ratio, base.min_leverage_ratio)
        self.assertGreater(severe.cumulative_impairment, base.cumulative_impairment)
        self.assertLess(severe.cumulative_profit_after_tax,
                        base.cumulative_profit_after_tax)

    def test_stress_produces_a_capital_drawdown(self):
        severe = self._run("acs_severe")
        self.assertGreater(severe.cet1_drawdown(), 0.01)  # more than 1pp

    def test_rwas_inflate_in_the_stress(self):
        severe = self._run("acs_severe")
        opening = compute_capital_position(build_bank(), 2027).total_rwa
        self.assertGreater(severe.periods[0].capital.total_rwa, opening)

    def test_the_bank_stays_above_its_pillar_one_minimum(self):
        for name in self.scenarios:
            result = self._run(name)
            self.assertGreater(result.min_cet1_ratio, 0.045, msg=name)

    def test_mda_binds_in_the_severe_scenario(self):
        severe = self._run("acs_severe")
        self.assertTrue(any(p.capital.in_buffer for p in severe.periods))

    def test_liquidity_ratios_are_reported_and_plausible(self):
        base = self._run("baseline")
        for p in base.periods:
            self.assertGreater(p.lcr_ratio, 0.5)
            self.assertGreater(p.nsfr_ratio, 0.5)

    def test_every_period_is_reported(self):
        base = self._run("baseline")
        self.assertEqual([p.year for p in base.periods], list(range(2027, 2032)))
        self.assertTrue(all("cet1_ratio" in p.summary() for p in base.periods))


if __name__ == "__main__":
    unittest.main()
