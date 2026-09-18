"""Credit risk: standardised weights, the IRB formula, floors and the CCFs."""

from __future__ import annotations

import math
import unittest

from banksim.credit_risk import (
    CCF,
    PD_FLOOR,
    credit_rwa,
    irb_capital_requirement,
    irb_ead,
    irb_rwa,
    maturity_adjustment,
    sa_exposure_at_default,
    sa_risk_weight,
    standardised_rwa,
)
from banksim.exposures import (
    CreditExposure,
    CreditQuality,
    ExposureClass,
    Facility,
    IFRS9Stage,
    IRBApproach,
)


def corporate(**kw) -> CreditExposure:
    base = dict(
        name="test", exposure_class=ExposureClass.CORPORATE, drawn=1_000.0,
        rating=CreditQuality.BBB, approach=IRBApproach.AIRB,
        pd=0.01, lgd=0.45, maturity_years=2.5,
    )
    base.update(kw)
    return CreditExposure(**base)


class TestStandardisedWeights(unittest.TestCase):
    def test_sovereign_ladder(self):
        for rating, expected in ((CreditQuality.AAA_AA, 0.00),
                                 (CreditQuality.A, 0.20),
                                 (CreditQuality.BBB, 0.50),
                                 (CreditQuality.CCC, 1.50)):
            e = corporate(exposure_class=ExposureClass.SOVEREIGN, rating=rating)
            self.assertAlmostEqual(sa_risk_weight(e), expected)

    def test_corporate_ladder(self):
        self.assertAlmostEqual(sa_risk_weight(corporate(rating=CreditQuality.AAA_AA)), 0.20)
        self.assertAlmostEqual(sa_risk_weight(corporate(rating=CreditQuality.BBB)), 0.75)
        self.assertAlmostEqual(sa_risk_weight(corporate(rating=CreditQuality.B)), 1.50)

    def test_unrated_corporate_variants(self):
        unrated = corporate(rating=CreditQuality.UNRATED)
        self.assertAlmostEqual(sa_risk_weight(unrated), 1.00)
        self.assertAlmostEqual(sa_risk_weight(corporate(rating=CreditQuality.UNRATED, sme=True)), 0.85)
        ig = corporate(rating=CreditQuality.UNRATED, investment_grade=True)
        self.assertAlmostEqual(sa_risk_weight(ig), 0.65)

    def test_residential_ltv_bands(self):
        for ltv, expected in ((0.40, 0.20), (0.55, 0.25), (0.75, 0.35),
                              (0.95, 0.55), (1.20, 0.70)):
            e = corporate(exposure_class=ExposureClass.RRE, ltv=ltv)
            self.assertAlmostEqual(sa_risk_weight(e), expected, msg=f"ltv={ltv}")

    def test_unrated_bank_uses_scra(self):
        for grade, expected in (("A", 0.40), ("B", 0.75), ("C", 1.50)):
            e = corporate(exposure_class=ExposureClass.INSTITUTION,
                          rating=CreditQuality.UNRATED, scra_grade=grade)
            self.assertAlmostEqual(sa_risk_weight(e), expected)

    def test_defaulted_weight_depends_on_coverage(self):
        thin = corporate(stage=IFRS9Stage.STAGE_3, provision=50.0)      # 5% cover
        thick = corporate(stage=IFRS9Stage.STAGE_3, provision=300.0)    # 30% cover
        self.assertAlmostEqual(sa_risk_weight(thin), 1.50)
        self.assertAlmostEqual(sa_risk_weight(thick), 1.00)


class TestCreditConversionFactors(unittest.TestCase):
    def test_unconditionally_cancellable_is_ten_percent(self):
        # The change from 0% to 10% is one of Basel 3.1's larger effects on a
        # bank with a big undrawn revolver book.
        self.assertAlmostEqual(CCF[Facility.UNCONDITIONALLY_CANCELLABLE], 0.10)

    def test_ead_includes_converted_undrawn(self):
        e = corporate(drawn=100.0, undrawn=900.0, facility=Facility.COMMITMENT)
        self.assertAlmostEqual(sa_exposure_at_default(e), 100.0 + 0.40 * 900.0)

    def test_irb_ead_floor_is_half_the_sa_ccf(self):
        e = corporate(drawn=100.0, undrawn=900.0, facility=Facility.COMMITMENT)
        # Modelled EAD here equals the SA one, so the floor is not binding, but
        # it must never exceed the modelled figure.
        self.assertGreaterEqual(irb_ead(e), 100.0 + 0.5 * 0.40 * 900.0)


class TestIRBFormula(unittest.TestCase):
    def test_against_hand_computed_risk_weight(self):
        """A corporate at PD 1%, LGD 45%, M 2.5 gives a risk weight of ~92.3%.

        Worked through by hand: R = 0.1928, b = 0.1375, maturity adjustment
        1.2598, conditional PD 0.1403, K = 0.0738.
        """
        e = corporate(pd=0.01, lgd=0.45, maturity_years=2.5, drawn=1_000.0)
        k = irb_capital_requirement(e)
        self.assertAlmostEqual(k, 0.073849, places=5)
        self.assertAlmostEqual(irb_rwa(e) / 1_000.0, 0.923, places=3)

    def test_risk_weight_rises_with_pd(self):
        weights = [irb_rwa(corporate(pd=p)) for p in (0.001, 0.005, 0.02, 0.10)]
        self.assertEqual(weights, sorted(weights))

    def test_maturity_adjustment_is_one_at_two_point_five_years(self):
        # The adjustment is normalised so M = 2.5 leaves K unchanged by the
        # (1 + (M-2.5)b) term; only the 1/(1-1.5b) scaling remains.
        b = (0.11852 - 0.05478 * math.log(0.01)) ** 2
        self.assertAlmostEqual(maturity_adjustment(0.01, 2.5), 1.0 / (1.0 - 1.5 * b))

    def test_retail_has_no_maturity_adjustment(self):
        short = corporate(exposure_class=ExposureClass.RETAIL, maturity_years=1.0)
        long = corporate(exposure_class=ExposureClass.RETAIL, maturity_years=5.0)
        self.assertAlmostEqual(irb_rwa(short), irb_rwa(long))

    def test_pd_floor_applies(self):
        tiny = corporate(pd=1e-9)
        floored = corporate(pd=PD_FLOOR)
        self.assertAlmostEqual(irb_rwa(tiny), irb_rwa(floored))

    def test_lgd_floor_applies_to_unsecured_corporate(self):
        optimistic = corporate(lgd=0.05)
        at_floor = corporate(lgd=0.25)
        self.assertAlmostEqual(irb_rwa(optimistic), irb_rwa(at_floor))

    def test_firb_uses_supervisory_lgd(self):
        e = corporate(approach=IRBApproach.FIRB, lgd=0.99)
        supervisory = corporate(approach=IRBApproach.AIRB, lgd=0.40,
                                maturity_years=2.5)
        # F-IRB ignores the firm's own LGD and uses 40% senior unsecured.
        self.assertAlmostEqual(irb_rwa(e), irb_rwa(supervisory), places=4)

    def test_institution_correlation_carries_the_avc_multiplier(self):
        bank_exp = corporate(exposure_class=ExposureClass.INSTITUTION,
                             approach=IRBApproach.FIRB)
        corp_exp = corporate(approach=IRBApproach.FIRB)
        self.assertGreater(irb_rwa(bank_exp), irb_rwa(corp_exp))

    def test_defaulted_exposure_capital_is_lgd_less_provisions(self):
        e = corporate(stage=IFRS9Stage.STAGE_3, pd=1.0, lgd=0.60, provision=200.0)
        # LGD 60% floored at 25% stays 60%; best-estimate EL is 200/1000 = 20%.
        self.assertAlmostEqual(irb_capital_requirement(e), 0.40, places=6)

    def test_fully_provided_default_carries_no_capital(self):
        e = corporate(stage=IFRS9Stage.STAGE_3, pd=1.0, lgd=0.40, provision=900.0)
        self.assertAlmostEqual(irb_capital_requirement(e), 0.0)


class TestPortfolioAggregation(unittest.TestCase):
    def test_both_bases_are_produced(self):
        book = [corporate(), corporate(approach=IRBApproach.SA_ONLY)]
        res = credit_rwa(book)
        self.assertGreater(res.live_rwa, 0)
        self.assertGreater(res.sa_rwa, 0)
        self.assertGreater(res.expected_loss, 0)

    def test_sa_only_exposures_are_identical_on_both_bases(self):
        e = corporate(approach=IRBApproach.SA_ONLY)
        res = credit_rwa([e])
        self.assertAlmostEqual(res.live_rwa, res.sa_rwa)
        self.assertAlmostEqual(res.live_rwa, standardised_rwa(e))


if __name__ == "__main__":
    unittest.main()
