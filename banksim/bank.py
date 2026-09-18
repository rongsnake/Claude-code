"""
Kingsgate Bank plc — the hypothetical UK wholesale bank being simulated.

**Kingsgate is fictional.** It is not a pseudonym for any real firm, and none of
the figures below are taken from any firm's accounts. What is borrowed from
reality is the *shape*: the balance-sheet composition, revenue mix, cost ratio
and capital structure of a mid-sized UK-headquartered wholesale bank, of the
kind whose Pillar 3 report runs to a couple of hundred pages.

The profile:

  * PRA-authorised UK bank, not ring-fenced (its business is wholesale, so it
    falls outside the ring-fencing perimeter rather than inside it), with a
    bail-in resolution strategy and therefore an external MREL.
  * Roughly £180bn of total assets, around a third of which is cash, HQLA and
    reverse repo — a markets balance sheet, not a lending one.
  * IRB permission for its corporate and real-estate books; standardised for
    everything else. FRTB standardised approach for market risk. That makes it
    exactly the kind of firm the Basel 3.1 output floor was aimed at.
  * Four markets desks, three fee businesses, and a small lending book.

Why these choices matter for the simulation: a bank with this shape is
leverage-constrained and floor-constrained rather than CET1-constrained in
benign conditions, and its revenue is dominated by the two lines (markets and
fees) that move hardest in a stress.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .capital import (
    CapitalRequirements,
    ExposureMeasure,
    LeverageConfig,
    OwnFunds,
)
from .credit_risk import SAConfig
from .exposures import (
    Commitment,
    CreditExposure,
    CreditQuality,
    Currency,
    Derivative,
    ExposureClass,
    Facility,
    Funding,
    FundingType,
    IFRS9Stage,
    IRBApproach,
    JumpToDefault,
    NettingSet,
    Sensitivity,
    TradingBook,
)
from .liquidity import LCRInputs
from .op_risk import IncomeStatementYear, OpRiskConfig
from .pnl import CostModel, FeeBusiness, MarketsDesk, NIIInputs, StructuralHedge, UKTaxModel
from .units import Assumption, AssumptionSet, Provenance

BANK_NAME = "Kingsgate Bank plc"
BASE_YEAR = 2026


# ---------------------------------------------------------------------------
# The bank
# ---------------------------------------------------------------------------


@dataclass
class Bank:
    """Everything the engines need, in one object."""

    name: str
    exposures: list[CreditExposure] = field(default_factory=list)
    netting_sets: list[NettingSet] = field(default_factory=list)
    trading_book: TradingBook = field(default_factory=TradingBook)
    funding: list[Funding] = field(default_factory=list)
    commitments: list[Commitment] = field(default_factory=list)

    desks: list[MarketsDesk] = field(default_factory=list)
    fee_businesses: list[FeeBusiness] = field(default_factory=list)
    costs: CostModel = field(default_factory=CostModel)
    tax: UKTaxModel = field(default_factory=UKTaxModel)
    nii: NIIInputs = field(default_factory=NIIInputs)
    hedge: StructuralHedge = field(default_factory=StructuralHedge)

    own_funds: OwnFunds = field(default_factory=OwnFunds)
    requirements: CapitalRequirements = field(default_factory=CapitalRequirements)
    leverage_cfg: LeverageConfig = field(default_factory=LeverageConfig)
    exposure_measure: ExposureMeasure = field(default_factory=ExposureMeasure)
    sa_cfg: SAConfig = field(default_factory=SAConfig)
    op_risk_cfg: OpRiskConfig = field(default_factory=OpRiskConfig)
    op_risk_history: list[IncomeStatementYear] = field(default_factory=list)
    lcr_inputs: LCRInputs = field(default_factory=LCRInputs)

    #: Non-credit balance-sheet items needed by NSFR and the exposure measure.
    fixed_assets: float = 0.0
    derivative_assets: float = 0.0
    derivative_liabilities: float = 0.0
    #: Dividend policy: share of attributable profit paid out, before the MDA.
    target_payout_ratio: float = 0.40
    #: AT1 coupons payable, £m per year.
    at1_coupons: float = 0.0

    assumptions: AssumptionSet = field(default_factory=AssumptionSet)

    @property
    def total_deposits(self) -> float:
        return sum(f.amount for f in self.funding
                   if f.funding_type in (
                       FundingType.RETAIL_STABLE, FundingType.RETAIL_LESS_STABLE,
                       FundingType.OPERATIONAL_DEPOSIT,
                       FundingType.CORPORATE_NON_OPERATIONAL,
                       FundingType.FINANCIAL_DEPOSIT))

    @property
    def mrel_resources(self) -> float:
        """Own funds plus eligible liabilities — the bail-in stack."""
        eligible = sum(f.amount for f in self.funding if f.mrel_eligible)
        return self.own_funds.total_capital() + eligible


# ---------------------------------------------------------------------------
# Book construction
# ---------------------------------------------------------------------------


def _banking_book(a: AssumptionSet) -> list[CreditExposure]:
    """The lending and liquidity book. Sized to a markets-led balance sheet:
    a modest loan book sitting under a large pool of HQLA and reverse repo."""

    a.add(Assumption("loan_book_gbp_m", 36_500, Provenance.STYLISED,
                     "Total drawn customer and bank lending"))
    a.add(Assumption("hqla_pool_gbp_m", 44_000, Provenance.STYLISED,
                     "Cash, central bank reserves and liquid securities"))

    return [
        # --- Liquidity portfolio -----------------------------------------
        CreditExposure(
            "Bank of England reserves", ExposureClass.CENTRAL_BANK, drawn=28_000,
            rating=CreditQuality.AAA_AA, hqla_level="L1", asset_yield=0.0375,
            segment="sovereign", residual_maturity_years=0.02,
            approach=IRBApproach.SA_ONLY, pd=0.0001, lgd=0.0,
        ),
        CreditExposure(
            "UK gilts", ExposureClass.SOVEREIGN, drawn=11_000,
            rating=CreditQuality.AAA_AA, hqla_level="L1", asset_yield=0.041,
            segment="sovereign", residual_maturity_years=6.0,
            approach=IRBApproach.SA_ONLY, pd=0.0002, lgd=0.45,
        ),
        CreditExposure(
            "Other sovereign and supranational HQLA", ExposureClass.SOVEREIGN,
            drawn=3_500, rating=CreditQuality.AAA_AA, hqla_level="L1",
            asset_yield=0.039, segment="sovereign", residual_maturity_years=4.0,
            approach=IRBApproach.SA_ONLY, pd=0.0004, lgd=0.45,
        ),
        CreditExposure(
            "Covered bonds and agency paper", ExposureClass.COVERED_BOND,
            drawn=1_500, rating=CreditQuality.AAA_AA, hqla_level="L2A",
            asset_yield=0.043, segment="financial", residual_maturity_years=4.0,
            approach=IRBApproach.SA_ONLY, pd=0.0010, lgd=0.25,
        ),

        # --- Corporate lending -------------------------------------------
        CreditExposure(
            "Investment grade corporate revolvers", ExposureClass.CORPORATE,
            drawn=5_200, undrawn=14_000, facility=Facility.COMMITMENT,
            rating=CreditQuality.BBB, investment_grade=True,
            approach=IRBApproach.AIRB, pd=0.0022, lgd=0.32, maturity_years=3.2,
            asset_yield=0.058, segment="corporate", residual_maturity_years=3.2,
            effective_rate=0.058, behavioural_life_years=3.2,
        ),
        CreditExposure(
            "Investment grade corporate term loans", ExposureClass.CORPORATE,
            drawn=5_400, rating=CreditQuality.BBB, investment_grade=True,
            approach=IRBApproach.AIRB, pd=0.0030, lgd=0.33, maturity_years=4.0,
            asset_yield=0.062, segment="corporate", residual_maturity_years=4.0,
            effective_rate=0.062, behavioural_life_years=4.0,
        ),
        CreditExposure(
            "Sub-investment grade corporate loans", ExposureClass.CORPORATE,
            drawn=2_100, undrawn=1_100, facility=Facility.COMMITMENT,
            rating=CreditQuality.BB,
            approach=IRBApproach.AIRB, pd=0.0140, lgd=0.38, maturity_years=3.6,
            asset_yield=0.085, segment="corporate", residual_maturity_years=3.6,
            effective_rate=0.085, behavioural_life_years=3.6,
        ),
        CreditExposure(
            "Leveraged finance", ExposureClass.CORPORATE, drawn=2_300,
            undrawn=500, facility=Facility.COMMITMENT, rating=CreditQuality.B,
            approach=IRBApproach.AIRB, pd=0.0320, lgd=0.42, maturity_years=4.5,
            asset_yield=0.105, segment="leveraged_finance",
            residual_maturity_years=4.5, effective_rate=0.105,
            behavioural_life_years=4.5,
        ),
        CreditExposure(
            "Mid-market and SME lending", ExposureClass.CORPORATE_SME, drawn=1_900,
            undrawn=550, facility=Facility.COMMITMENT, sme=True,
            turnover_gbp_m=28.0, rating=CreditQuality.UNRATED,
            approach=IRBApproach.AIRB, pd=0.0165, lgd=0.40, maturity_years=3.0,
            asset_yield=0.078, segment="corporate", residual_maturity_years=3.0,
            effective_rate=0.078, behavioural_life_years=3.0,
        ),

        # --- Real estate ---------------------------------------------------
        CreditExposure(
            "Commercial real estate lending", ExposureClass.CRE, drawn=4_200,
            undrawn=450, facility=Facility.COMMITMENT, ltv=0.62,
            rating=CreditQuality.BB,
            approach=IRBApproach.AIRB, pd=0.0145, lgd=0.24, maturity_years=3.4,
            asset_yield=0.072, segment="cre", residual_maturity_years=3.4,
            effective_rate=0.072, behavioural_life_years=3.4,
        ),
        CreditExposure(
            "Residential mortgages (legacy book)", ExposureClass.RRE, drawn=3_900,
            ltv=0.58, approach=IRBApproach.AIRB, pd=0.0075, lgd=0.14,
            maturity_years=12.0, asset_yield=0.047, segment="mortgages",
            residual_maturity_years=12.0, rate_sensitive_share=0.45,
            effective_rate=0.047, behavioural_life_years=8.0,
        ),

        # --- Financial institutions ---------------------------------------
        CreditExposure(
            "Loans and advances to banks", ExposureClass.INSTITUTION, drawn=3_200,
            rating=CreditQuality.A, approach=IRBApproach.FIRB, pd=0.0022,
            lgd=0.40, maturity_years=0.4, asset_yield=0.044, segment="financial",
            residual_maturity_years=0.4, effective_rate=0.044,
            behavioural_life_years=1.0,
        ),
        CreditExposure(
            "Prime brokerage margin lending", ExposureClass.INSTITUTION,
            drawn=8_400, rating=CreditQuality.UNRATED, scra_grade="B",
            financial_collateral=7_600,
            approach=IRBApproach.SA_ONLY, pd=0.0090, lgd=0.20, maturity_years=0.3,
            asset_yield=0.051, segment="prime_brokerage",
            residual_maturity_years=0.3, effective_rate=0.051,
            behavioural_life_years=1.0,
        ),
        CreditExposure(
            "Non-performing exposures", ExposureClass.CORPORATE, drawn=560,
            rating=CreditQuality.CCC, stage=IFRS9Stage.STAGE_3,
            approach=IRBApproach.AIRB, pd=1.0, lgd=0.55, maturity_years=1.0,
            asset_yield=0.0, segment="corporate", provision=225.0,
            residual_maturity_years=1.0, effective_rate=0.07,
        ),

        # --- Other assets ---------------------------------------------------
        CreditExposure(
            "Equity investments and seed capital", ExposureClass.EQUITY, drawn=420,
            approach=IRBApproach.SA_ONLY, segment="financial",
            residual_maturity_years=5.0, asset_yield=0.0,
        ),
        CreditExposure(
            "Other assets", ExposureClass.OTHER_ASSET, drawn=2_600,
            approach=IRBApproach.SA_ONLY, segment="corporate",
            residual_maturity_years=1.0, asset_yield=0.01,
        ),
    ]


def _netting_sets(a: AssumptionSet) -> list[NettingSet]:
    """Derivative counterparties, grouped the way SA-CCR wants them.

    The split matters: cleared and heavily-margined bank counterparties produce
    small EADs and small CVA; corporate hedging counterparties are unmargined,
    long-dated and unrated, and produce most of the CVA charge despite a
    fraction of the notional.
    """
    a.add(Assumption("derivative_notional_gbp_m", 713_000, Provenance.STYLISED,
                     "Gross OTC derivative notional across all netting sets"))

    return [
        NettingSet(
            counterparty="Cleared - LCH rates", sector="financial",
            rating=CreditQuality.AAA_AA, margined=True, mpor_days=5,
            collateral_held=950, nica=390,
            # Cleared through a qualifying CCP, so outside the CVA charge.
            cva_exempt=True,
            trades=[
                Derivative("IR", notional=280_000, mtm=1_100, end_years=7.0,
                           direction=1, hedging_set="GBP"),
                Derivative("IR", notional=185_000, mtm=-870, end_years=4.0,
                           direction=-1, hedging_set="USD"),
                Derivative("IR", notional=80_000, mtm=270, end_years=12.0,
                           direction=1, hedging_set="EUR"),
            ],
        ),
        NettingSet(
            counterparty="Dealer bank netting sets", sector="financial",
            rating=CreditQuality.A, margined=True, mpor_days=10,
            collateral_held=1_700, threshold=50, mta=5, nica=600,
            trades=[
                Derivative("IR", notional=48_000, mtm=550, end_years=6.0,
                           direction=1, hedging_set="GBP"),
                Derivative("FX", notional=32_000, mtm=-350, end_years=1.2,
                           direction=-1, hedging_set="GBPUSD"),
                Derivative("CREDIT", notional=14_000, mtm=210, end_years=5.0,
                           direction=1, subtype="index_ig", hedging_set="CDX_IG"),
                Derivative("EQUITY", notional=9_500, mtm=440, end_years=2.0,
                           direction=1, subtype="index", hedging_set="FTSE"),
            ],
        ),
        NettingSet(
            counterparty="Hedge fund and prime clients", sector="financial",
            rating=CreditQuality.BB, margined=True, mpor_days=10,
            collateral_held=1_400, threshold=0, mta=1, nica=870,
            trades=[
                Derivative("EQUITY", notional=15_000, mtm=700, end_years=1.5,
                           direction=1, subtype="single_name", hedging_set="EQ_SN"),
                Derivative("IR", notional=11_000, mtm=-145, end_years=3.0,
                           direction=-1, hedging_set="USD"),
                Derivative("CREDIT", notional=4_800, mtm=130, end_years=4.0,
                           direction=1, subtype="single_name", hedging_set="CDS_SN"),
            ],
        ),
        NettingSet(
            counterparty="Corporate hedging clients", sector="basic_materials",
            rating=CreditQuality.BBB, margined=False,
            trades=[
                Derivative("IR", notional=9_000, mtm=950, end_years=9.0,
                           direction=1, hedging_set="GBP"),
                Derivative("FX", notional=6_000, mtm=370, end_years=2.5,
                           direction=1, hedging_set="GBPEUR"),
                Derivative("COMMODITY", notional=2_000, mtm=105, end_years=2.0,
                           direction=1, subtype="oil_gas", hedging_set="OIL"),
            ],
        ),
        NettingSet(
            counterparty="Sovereign and supranational", sector="sovereign",
            rating=CreditQuality.AAA_AA, margined=False,
            # Sovereign and public-sector counterparties are outside the UK
            # CVA charge. The corporate hedging set above would also be exempt
            # if those clients sat below the EMIR clearing threshold; it is
            # left in scope here so the charge is visible.
            cva_exempt=True,
            trades=[
                Derivative("IR", notional=13_000, mtm=620, end_years=11.0,
                           direction=1, hedging_set="GBP"),
                Derivative("FX", notional=4_000, mtm=-90, end_years=3.0,
                           direction=-1, hedging_set="GBPUSD"),
            ],
        ),
    ]


def _trading_book(a: AssumptionSet) -> TradingBook:
    """Trading-book sensitivities for the FRTB standardised approach.

    GIRR sensitivities are stated the way the rules require: the P&L change for
    a **one unit** (100bp) shift, so a desk running £0.6m of PV01 per basis
    point at the 5-year point appears here as 6,000.
    """
    a.add(Assumption("girr_pv01_gbp_m_per_bp", 1.62, Provenance.STYLISED,
                     "Net interest rate PV01 across all currencies and tenors"))

    sens: list[Sensitivity] = []

    # --- GIRR: net PV01 by currency and tenor, scaled to a 100bp shift ------
    girr_pv01 = {   # £m per basis point, signed
        "GBP": {1.0: 0.18, 2.0: -0.42, 5.0: 0.61, 10.0: -0.35, 30.0: 0.14},
        "USD": {1.0: -0.26, 2.0: 0.33, 5.0: -0.48, 10.0: 0.29, 30.0: -0.09},
        "EUR": {1.0: 0.11, 2.0: -0.19, 5.0: 0.27, 10.0: -0.16},
        "JPY": {2.0: 0.07, 5.0: -0.12, 10.0: 0.05},
    }
    for ccy, curve in girr_pv01.items():
        for tenor, pv01 in curve.items():
            sens.append(Sensitivity("GIRR", ccy, str(tenor), pv01 * 10_000.0))
        sens.append(Sensitivity("GIRR", ccy, "inflation", 0.08 * 10_000.0))

    # --- CSR: credit spread sensitivity by bucket, per 100bp ----------------
    csr = {
        "financial_ig": [("BankA|5", 1_450), ("BankB|5", -980), ("BankC|10", 620)],
        "industrial_ig": [("IndustrialA|5", 1_180), ("IndustrialB|3", -540)],
        "consumer_ig": [("ConsumerA|5", 860), ("ConsumerB|7", -410)],
        "sovereign_ig": [("UKGovt|10", 2_300), ("USGovt|5", -1_600)],
        "industrial_hy": [("HYIssuerA|3", 540), ("HYIssuerB|5", 380)],
        "index_ig": [("iTraxxMain|5", -1_900)],
        "index_hy": [("iTraxxXover|5", -640)],
    }
    for bucket, items in csr.items():
        for factor, value in items:
            sens.append(Sensitivity("CSR", bucket, factor, float(value)))

    # --- Equity delta: per 100% move ----------------------------------------
    eq = {
        "adv_large_financial": [("EuropeanBanks", 240)],
        "adv_large_consumer": [("UKConsumer", 200), ("USConsumer", -140)],
        "adv_large_industrial": [("UKIndustrials", 160)],
        "index_large": [("FTSE100", -380), ("SX5E", -220)],
        "adv_small": [("UKSmallCap", 70)],
    }
    for bucket, items in eq.items():
        for factor, value in items:
            sens.append(Sensitivity("EQ", bucket, factor, float(value)))

    # --- FX delta: net open position per currency pair, per 100% move -------
    for pair, value in (("GBPUSD", 410), ("GBPEUR", -260), ("GBPJPY", 140),
                        ("GBPCHF", 75), ("GBPNOK", -48)):
        sens.append(Sensitivity("FX", pair, pair, float(value)))

    # --- Commodity ----------------------------------------------------------
    for bucket, value in (("energy_oil", 120), ("metals_precious", -70)):
        sens.append(Sensitivity("COMM", bucket, bucket, float(value)))

    # --- Vega: simplified, one aggregate per risk class ---------------------
    for rc, bucket, value in (("GIRR", "GBP", 290), ("EQ", "index_large", 170),
                              ("CSR", "financial_ig", 110), ("FX", "GBPUSD", 80)):
        sens.append(Sensitivity(rc, bucket, f"{rc}_vega", float(value), kind="vega"))

    # --- Curvature: simplified, one aggregate per risk class ----------------
    for rc, bucket, value in (("GIRR", "GBP", 130), ("EQ", "index_large", 105)):
        sens.append(Sensitivity(rc, bucket, f"{rc}_curv", float(value), kind="curvature"))

    # --- Default risk: corporate and sovereign inventory --------------------
    jtds = [
        JumpToDefault("IG corporate inventory", "corporate", CreditQuality.BBB,
                      notional=7_400, mtm=-90, lgd=0.75),
        JumpToDefault("HY corporate inventory", "corporate", CreditQuality.BB,
                      notional=2_100, mtm=-140, lgd=0.75),
        JumpToDefault("Index protection bought", "corporate", CreditQuality.BBB,
                      notional=-5_800, mtm=60, lgd=0.75),
        JumpToDefault("Financial issuer inventory", "corporate", CreditQuality.A,
                      notional=3_600, mtm=-40, lgd=0.75),
        JumpToDefault("Sovereign inventory", "sovereign", CreditQuality.AAA_AA,
                      notional=9_200, mtm=-210, lgd=0.75),
        JumpToDefault("Sovereign hedges", "sovereign", CreditQuality.AAA_AA,
                      notional=-4_100, mtm=85, lgd=0.75),
    ]

    return TradingBook(
        sensitivities=sens,
        jtds=jtds,
        exotic_notional=4_200,
        other_residual_notional=38_000,
        inventory=31_500,
    )


def _funding(a: AssumptionSet) -> list[Funding]:
    """The liability stack, including the MREL-eligible layers.

    A wholesale bank's funding is short and secured — repo dominates — which is
    why NSFR rather than LCR is usually its binding liquidity constraint.
    """
    return [
        Funding("Corporate operational deposits", FundingType.OPERATIONAL_DEPOSIT,
                amount=17_500, rate=0.021, maturity_years=0.1),
        Funding("Corporate non-operational deposits",
                FundingType.CORPORATE_NON_OPERATIONAL,
                amount=15_800, rate=0.030, maturity_years=0.2),
        Funding("Financial institution deposits", FundingType.FINANCIAL_DEPOSIT,
                amount=9_400, rate=0.034, maturity_years=0.1),
        Funding("Private bank deposits", FundingType.RETAIL_LESS_STABLE,
                amount=5_600, rate=0.026, maturity_years=0.3, insured=True),
        Funding("Repo - gilt collateral", FundingType.SECURED_FUNDING,
                amount=44_000, rate=0.037, maturity_years=0.05,
                collateral_level="L1"),
        Funding("Repo - corporate and equity collateral", FundingType.SECURED_FUNDING,
                amount=26_000, rate=0.040, maturity_years=0.08,
                collateral_level=None),
        Funding("Senior unsecured (OpCo)", FundingType.SENIOR_UNSECURED,
                amount=13_000, rate=0.048, maturity_years=3.0),
        Funding("Senior non-preferred (HoldCo)", FundingType.SENIOR_NON_PREFERRED,
                amount=9_000, rate=0.056, maturity_years=4.5, mrel_eligible=True),
        Funding("Covered bonds", FundingType.COVERED_BOND_ISSUED,
                amount=5_800, rate=0.042, maturity_years=5.0),
        Funding("Tier 2 subordinated notes", FundingType.TIER2,
                amount=2_600, rate=0.072, maturity_years=7.0),
        Funding("AT1 contingent convertibles", FundingType.AT1,
                amount=1_650, rate=0.088, maturity_years=6.0),
        Funding("Other liabilities", FundingType.CORPORATE_NON_OPERATIONAL,
                amount=4_900, rate=0.010, maturity_years=1.0),
    ]


def _commitments() -> list[Commitment]:
    return [
        Commitment("Corporate revolving credit facilities", 14_000, "corporate", "credit"),
        Commitment("Corporate backstop liquidity lines", 2_400, "corporate", "liquidity"),
        Commitment("Financial institution facilities", 1_300, "financial", "credit"),
        Commitment("Committed liquidity to funds", 650, "financial", "liquidity"),
    ]


def _desks() -> list[MarketsDesk]:
    """Four desks with deliberately different macro betas.

    Rates and FX are the counter-cyclical franchises: clients hedge more when
    the world is frightening. Credit and equity derivatives are pro-cyclical —
    they carry inventory and short-volatility structured books.
    """
    return [
        MarketsDesk("Rates", base_revenue=760, vol_beta=0.55, activity_beta=0.25,
                    inventory=9_000, inventory_beta=0.02, floor_share=0.55),
        MarketsDesk("FX", base_revenue=470, vol_beta=0.60, activity_beta=0.30,
                    inventory=1_800, inventory_beta=0.01, floor_share=0.60),
        MarketsDesk("Credit", base_revenue=510, vol_beta=-0.15, activity_beta=0.70,
                    inventory=12_500, inventory_beta=0.10, floor_share=0.20),
        MarketsDesk("Equities and prime", base_revenue=880, vol_beta=0.10,
                    activity_beta=0.65, inventory=8_200, inventory_beta=0.14,
                    floor_share=0.25),
    ]


def _fee_businesses() -> list[FeeBusiness]:
    return [
        FeeBusiness("Debt capital markets", base_revenue=380, activity_beta=0.9,
                    floor_share=0.35),
        FeeBusiness("Equity capital markets", base_revenue=215, activity_beta=1.8,
                    floor_share=0.10),
        FeeBusiness("Advisory and M&A", base_revenue=340, activity_beta=1.4,
                    floor_share=0.20),
    ]


def _op_risk_history() -> list[IncomeStatementYear]:
    """Three years of income statement for the Business Indicator.

    Note the financial component uses *absolute* trading P&L, so a bank whose
    trading revenue swings around carries a higher operational risk charge than
    one with the same average and less variance.
    """
    return [
        IncomeStatementYear(
            interest_income=5_900, interest_expense=4_950,
            interest_earning_assets=118_000, dividend_income=25,
            fee_income=1_010, fee_expense=180,
            other_operating_income=120, other_operating_expense=90,
            trading_book_pnl=2_480, banking_book_pnl=140),
        IncomeStatementYear(
            interest_income=6_350, interest_expense=5_380,
            interest_earning_assets=121_000, dividend_income=30,
            fee_income=880, fee_expense=165,
            other_operating_income=105, other_operating_expense=95,
            trading_book_pnl=2_610, banking_book_pnl=95),
        IncomeStatementYear(
            interest_income=6_100, interest_expense=5_120,
            interest_earning_assets=124_000, dividend_income=28,
            fee_income=935, fee_expense=172,
            other_operating_income=130, other_operating_expense=100,
            trading_book_pnl=2_545, banking_book_pnl=120),
    ]


def build_bank() -> Bank:
    """Assemble Kingsgate Bank plc."""
    a = AssumptionSet()

    a.add(Assumption("cet1_opening_gbp_m", 9_620, Provenance.STYLISED,
                     "Opening CET1 capital"))
    a.add(Assumption("pillar2a", 0.032, Provenance.SUPERVISORY,
                     "Pillar 2A as a share of RWAs; real firms disclose theirs"))
    a.add(Assumption("ccyb", 0.020, Provenance.REGULATORY,
                     "UK countercyclical capital buffer, held at the FPC's 2% "
                     "neutral setting through 2026",
                     source="Bank of England FPC, July 2026"))
    a.add(Assumption("output_floor_2027", 0.60, Provenance.REGULATORY,
                     "Output floor on first application of Basel 3.1 in the UK",
                     source="PRA PS1/26, 20 January 2026"))
    a.add(Assumption("leverage_minimum", 0.0325, Provenance.REGULATORY,
                     "UK leverage ratio minimum; the exposure measure excludes "
                     "qualifying central bank claims"))

    bank = Bank(
        name=BANK_NAME,
        exposures=_banking_book(a),
        netting_sets=_netting_sets(a),
        trading_book=_trading_book(a),
        funding=_funding(a),
        commitments=_commitments(),
        desks=_desks(),
        fee_businesses=_fee_businesses(),
        assumptions=a,
    )

    bank.costs = CostModel(
        fixed_staff_costs=1_340, non_staff_costs=960,
        variable_comp_ratio=0.155, minimum_variable_comp=240,
        cost_inflation=0.030, exceptional_costs=0.0,
    )
    bank.tax = UKTaxModel()
    # The earning-asset base is the whole interest-bearing balance sheet:
    # reserves, the liquidity portfolio, reverse repo and the loan book. The
    # spread is thin because most of it is collateralised or risk-free — a
    # wholesale bank earns its margin on a small slice of a large balance sheet.
    bank.nii = NIIInputs(
        interest_earning_assets=145_000, asset_rate_sensitivity=0.80,
        asset_spread=0.0080, deposit_beta=0.58, wholesale_spread=0.0105,
    )
    bank.hedge = StructuralHedge(notional=16_000, tenor_years=5)
    bank.hedge.initialise(0.032)

    bank.own_funds = OwnFunds(
        ordinary_shares=2_400, share_premium=3_100, retained_earnings=5_200,
        other_reserves=310, accumulated_oci=-180,
        goodwill_intangibles=560, deferred_tax_future_profits=185,
        prudent_valuation_ava=240, defined_benefit_pension_asset=95,
        significant_investments=130,
        at1_instruments=1_650, tier2_instruments=2_600,
    )
    bank.requirements = CapitalRequirements(
        pillar2a=0.032, ccyb=0.020, systemic_buffer=0.000, pra_buffer=0.010,
    )
    bank.leverage_cfg = LeverageConfig(regime="current_uk", in_scope=True)
    bank.op_risk_history = _op_risk_history()
    bank.op_risk_cfg = OpRiskConfig(use_ilm=False, average_annual_loss=95.0)

    bank.lcr_inputs = LCRInputs(
        derivative_outflows=2_900, derivative_inflows=2_400,
        downgrade_trigger_collateral=1_150, market_valuation_outflow=780,
        inflow_retail=140, inflow_corporate=2_600, inflow_financial=3_900,
        reverse_repo_l1=32_000, reverse_repo_l2a=9_000, reverse_repo_other=13_000,
    )

    bank.derivative_assets = 24_000
    bank.derivative_liabilities = 22_000
    bank.fixed_assets = 1_900
    bank.at1_coupons = 145
    bank.target_payout_ratio = 0.65

    return bank
