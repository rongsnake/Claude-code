"""
Balance-sheet primitives: the things a bank owns, owes and has promised.

Everything the capital, liquidity and impairment engines consume is built from
these four objects:

  * `CreditExposure`  — a banking-book claim (loan, bond, commitment, reverse
                        repo). Carries both the standardised-approach fields
                        (exposure class, external rating, LTV) and the IRB
                        fields (PD, LGD, maturity), because Basel 3.1 makes
                        every IRB firm compute both — the output floor needs
                        the SA number for the same book.
  * `Derivative`      — an OTC trade in a netting set, for SA-CCR and CVA.
  * `TradingPosition` — a trading-book position expressed as sensitivities, for
                        the FRTB standardised approach.
  * `Funding`         — a liability, for LCR/NSFR and the cost of funds.

The split between "what the exposure is" and "how a given approach weights it"
is deliberate: the same `CreditExposure` is passed to the SA engine, the IRB
engine and the IFRS 9 engine, and each reads the fields it needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


class ExposureClass(str, Enum):
    """Standardised-approach exposure classes (UK CRR / Basel 3.1 credit risk)."""

    SOVEREIGN = "sovereign"
    CENTRAL_BANK = "central_bank"
    PSE = "public_sector_entity"
    MDB = "multilateral_development_bank"
    INSTITUTION = "institution"          # banks and investment firms
    COVERED_BOND = "covered_bond"
    CORPORATE = "corporate"
    CORPORATE_SME = "corporate_sme"
    SPECIALISED_LENDING = "specialised_lending"
    RETAIL = "retail"
    RETAIL_TRANSACTOR = "retail_transactor"
    RRE = "residential_real_estate"
    CRE = "commercial_real_estate"
    ADC = "land_acquisition_development_construction"
    EQUITY = "equity"
    SUBORDINATED = "subordinated_debt"
    DEFAULTED = "defaulted"
    OTHER_ASSET = "other_asset"


class CreditQuality(str, Enum):
    """Coarse rating bands. Mapped to credit quality steps by the SA engine."""

    AAA_AA = "AAA_to_AA-"
    A = "A+_to_A-"
    BBB = "BBB+_to_BBB-"
    BB = "BB+_to_BB-"
    B = "B+_to_B-"
    CCC = "CCC+_and_below"
    UNRATED = "unrated"


class IRBApproach(str, Enum):
    """Which approach the firm has permission to use for this book.

    Basel 3.1 removes A-IRB for exposures to banks, other financial institutions
    and large corporates (group revenue above the large-corporate threshold),
    and removes IRB entirely for equities. `SA_ONLY` and `FIRB` therefore appear
    on books that were A-IRB under the previous regime.
    """

    SA_ONLY = "standardised"
    FIRB = "foundation_irb"
    AIRB = "advanced_irb"


class IFRS9Stage(int, Enum):
    STAGE_1 = 1  # performing: 12-month ECL
    STAGE_2 = 2  # significant increase in credit risk: lifetime ECL
    STAGE_3 = 3  # credit-impaired: lifetime ECL on a defaulted asset


class Facility(str, Enum):
    """Drives the off-balance-sheet credit conversion factor."""

    DRAWN = "drawn"
    UNCONDITIONALLY_CANCELLABLE = "unconditionally_cancellable"
    COMMITMENT = "commitment"
    TRADE_CONTINGENT = "trade_related_contingent"
    TRANSACTION_CONTINGENT = "transaction_related_contingent"
    DIRECT_CREDIT_SUBSTITUTE = "direct_credit_substitute"
    NIF_RUF = "note_issuance_facility"


class Currency(str, Enum):
    GBP = "GBP"
    USD = "USD"
    EUR = "EUR"
    JPY = "JPY"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Banking book
# ---------------------------------------------------------------------------


@dataclass
class CreditExposure:
    """One banking-book credit exposure, or a homogeneous pool modelled as one.

    Amounts are £m. `drawn` is on-balance-sheet; `undrawn` is the committed but
    undrawn amount that attracts a CCF.
    """

    name: str
    exposure_class: ExposureClass
    drawn: float
    undrawn: float = 0.0
    facility: Facility = Facility.DRAWN

    # --- standardised approach inputs ---
    rating: CreditQuality = CreditQuality.UNRATED
    ltv: float | None = None               # RRE/CRE loan-to-value, decimal
    investment_grade: bool = False         # for the 65% IG corporate weight
    sme: bool = False
    #: Qualifying infrastructure lending. Like SME lending, it lost its Pillar 1
    #: supporting factor under Basel 3.1 and is compensated by a firm-specific
    #: Pillar 2A adjustment instead.
    infrastructure: bool = False
    #: SCRA grade for unrated bank exposures: "A", "B" or "C".
    scra_grade: str | None = None

    # --- IRB inputs ---
    approach: IRBApproach = IRBApproach.SA_ONLY
    pd: float = 0.01                       # 1-year through-the-cycle PD, decimal
    #: Point-in-time PD used for the IRB calculation, set each period by the
    #: engine. IRB PDs in practice are hybrid rather than purely through-the-
    #: cycle, so they migrate with the cycle and drag RWAs up in a downturn —
    #: the pro-cyclicality the countercyclical buffer exists to offset. Left
    #: as None, the IRB engine falls back to the TTC PD.
    pd_regulatory: float | None = None
    lgd: float = 0.45                      # loss given default, decimal
    maturity_years: float = 2.5            # effective maturity M
    turnover_gbp_m: float | None = None    # for the SME firm-size adjustment

    # --- credit risk mitigation ---
    financial_collateral: float = 0.0      # £m, post-haircut eligible collateral
    guarantee_amount: float = 0.0          # £m covered by an eligible guarantee
    guarantor_rating: CreditQuality | None = None

    # --- accounting / IFRS 9 ---
    stage: IFRS9Stage = IFRS9Stage.STAGE_1
    provision: float = 0.0                 # £m ECL already carried
    effective_rate: float = 0.05           # EIR used to discount ECL
    behavioural_life_years: float = 3.0    # lifetime-ECL horizon
    #: Dispersion of obligor PDs within this pool, as the standard deviation of
    #: log PD. Each `CreditExposure` stands for a pool rather than a single
    #: loan, and without dispersion the whole pool crosses the IFRS 9 stage
    #: transfer threshold at the same instant.
    pd_dispersion: float = 0.75

    # --- economics ---
    asset_yield: float = 0.06              # all-in contractual yield, decimal
    rate_sensitive_share: float = 1.0      # fraction repricing with Bank Rate
    segment: str = "corporate"             # links the exposure to a macro driver
    currency: Currency = Currency.GBP

    # --- liquidity ---
    hqla_level: str | None = None          # "L1", "L2A", "L2B" or None
    residual_maturity_years: float = 2.5   # for NSFR bucketing

    @property
    def total_commitment(self) -> float:
        return self.drawn + self.undrawn

    @property
    def net_carrying(self) -> float:
        """Drawn balance net of the ECL provision carried against it."""
        return self.drawn - self.provision

    @property
    def is_defaulted(self) -> bool:
        return self.stage is IFRS9Stage.STAGE_3 or self.exposure_class is ExposureClass.DEFAULTED


@dataclass
class NettingSet:
    """A close-out netting set of derivatives with one counterparty.

    SA-CCR is computed per netting set, so the counterparty's sector, rating and
    margin terms live here rather than on the individual trade.
    """

    counterparty: str
    sector: str = "financial"              # BA-CVA risk-weight sector
    rating: CreditQuality = CreditQuality.A
    margined: bool = True
    threshold: float = 0.0                 # TH, £m
    mta: float = 0.0                       # minimum transfer amount, £m
    nica: float = 0.0                      # net independent collateral amount, £m
    collateral_held: float = 0.0           # C, £m (variation margin held)
    mpor_days: int = 10                    # margin period of risk
    #: Out of scope of the CVA capital charge. UK CRR excludes transactions
    #: with a qualifying CCP, with certain sovereign and public bodies, and
    #: with non-financial counterparties below the EMIR clearing threshold —
    #: the last of these is a UK/EU divergence from the Basel text, and a
    #: material one for a bank whose client base is corporate hedgers.
    cva_exempt: bool = False
    trades: list["Derivative"] = field(default_factory=list)

    @property
    def market_value(self) -> float:
        """V — the net current mark-to-market of the set, £m."""
        return sum(t.mtm for t in self.trades)


@dataclass
class Derivative:
    """An OTC derivative trade, described in the terms SA-CCR needs."""

    asset_class: str                       # "IR", "FX", "CREDIT", "EQUITY", "COMMODITY"
    notional: float                        # £m, sign-free
    mtm: float                             # current value to us, £m (signed)
    start_years: float = 0.0               # S
    end_years: float = 5.0                 # E
    #: +1 long the risk factor, -1 short. For options, the supervisory delta is
    #: derived instead (see `supervisory_delta`).
    direction: int = 1
    is_option: bool = False
    option_strike: float = 0.0
    option_underlying: float = 0.0
    option_vol: float = 0.20
    #: Credit/equity sub-type: "single_name_ig", "single_name_hy", "index_ig",
    #: "index_hy", "single_name", "index".
    subtype: str = "single_name"
    #: Hedging-set key. For IR this is the currency; for FX the currency pair.
    hedging_set: str = "GBP"


# ---------------------------------------------------------------------------
# Trading book
# ---------------------------------------------------------------------------


@dataclass
class Sensitivity:
    """One FRTB standardised-approach risk factor sensitivity.

    `value` is the delta/vega sensitivity in £m per unit shift, expressed in the
    units the SBM expects: for GIRR, £m per 1bp is *not* what the rules use —
    they use the sensitivity to a 1 percentage point (100bp) shift, so callers
    must scale. Keeping that explicit here has caught more bugs than it caused.
    """

    risk_class: str        # "GIRR", "CSR", "EQ", "FX", "COMM"
    bucket: str            # bucket label within the risk class
    factor: str            # tenor, name or currency identifying the risk factor
    value: float           # £m per unit shift (1.0 = 100bp / 100% move)
    kind: str = "delta"    # "delta", "vega" or "curvature"
    #: Curvature only: P&L under the prescribed up and down shocks, £m.
    cvr_up: float = 0.0
    cvr_down: float = 0.0


@dataclass
class JumpToDefault:
    """A default-risk-charge position: the loss if the issuer defaults today."""

    issuer: str
    bucket: str                      # "corporate", "sovereign", "local_govt"
    rating: CreditQuality
    notional: float                  # £m, signed (+ long credit, - short)
    mtm: float = 0.0                 # £m, signed
    lgd: float = 0.75
    maturity_years: float = 1.0

    @property
    def jtd(self) -> float:
        """JTD = LGD x notional + P&L, floored at zero exposure for longs."""
        return self.lgd * self.notional + self.mtm


@dataclass
class TradingBook:
    """The trading book as FRTB-SA consumes it."""

    sensitivities: list[Sensitivity] = field(default_factory=list)
    jtds: list[JumpToDefault] = field(default_factory=list)
    #: Notional of exotic instruments attracting the 1.0% residual add-on.
    exotic_notional: float = 0.0
    #: Notional of other residual-risk instruments (0.1% add-on).
    other_residual_notional: float = 0.0
    #: Fair value of trading inventory carried on the balance sheet, £m.
    inventory: float = 0.0


# ---------------------------------------------------------------------------
# Funding
# ---------------------------------------------------------------------------


class FundingType(str, Enum):
    RETAIL_STABLE = "retail_stable"
    RETAIL_LESS_STABLE = "retail_less_stable"
    OPERATIONAL_DEPOSIT = "operational_deposit"
    CORPORATE_NON_OPERATIONAL = "corporate_non_operational"
    FINANCIAL_DEPOSIT = "financial_deposit"
    SECURED_FUNDING = "secured_funding"      # repo
    SENIOR_UNSECURED = "senior_unsecured"
    SENIOR_NON_PREFERRED = "senior_non_preferred"
    COVERED_BOND_ISSUED = "covered_bond_issued"
    TIER2 = "tier2"
    AT1 = "at1"
    CENTRAL_BANK_FACILITY = "central_bank_facility"


@dataclass
class Funding:
    """A liability line. `maturity_years` is residual contractual maturity."""

    name: str
    funding_type: FundingType
    amount: float                          # £m
    rate: float                            # cost, decimal
    maturity_years: float = 1.0
    currency: Currency = Currency.GBP
    #: Repo only: HQLA level of the collateral pledged, drives the LCR outflow.
    collateral_level: str | None = None
    #: Whether the instrument counts towards MREL (loss-absorbing at resolution).
    mrel_eligible: bool = False
    #: Deposits only: covered by FSCS, which lowers the LCR run-off rate.
    insured: bool = False


@dataclass
class Commitment:
    """An undrawn facility we have granted — an LCR outflow, not an asset."""

    name: str
    amount: float                          # £m undrawn
    counterparty: str                      # "retail", "corporate", "financial"
    kind: str = "credit"                   # "credit" or "liquidity"
