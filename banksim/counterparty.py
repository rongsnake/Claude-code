"""
Counterparty credit risk: SA-CCR exposure and the basic approach to CVA.

For a wholesale bank these two are a large share of RWAs, and they interact:
SA-CCR produces the EAD that feeds both the counterparty credit risk RWA
(EAD x the obligor's credit risk weight) and the CVA capital charge.

  * `sa_ccr_ead`   — EAD = 1.4 x (replacement cost + potential future exposure)
  * `ba_cva`       — the reduced form of the basic approach to CVA

Both are the Basel text. The supervisory factors and correlations below are
reproduced from the standard; they are not calibrated by us.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .exposures import CreditQuality, Derivative, NettingSet
from .units import norm_cdf, safe_div

# ---------------------------------------------------------------------------
# SA-CCR
# ---------------------------------------------------------------------------

#: The alpha factor grossing up EAD, carried over from the internal model method.
ALPHA = 1.4

#: PFE multiplier floor — recognises that over-collateralisation and negative
#: mark-to-market reduce, but never eliminate, potential future exposure.
MULTIPLIER_FLOOR = 0.05

#: Supervisory factors by asset class (decimals).
SF_INTEREST_RATE = 0.005
SF_FX = 0.04
SF_EQUITY_SINGLE = 0.32
SF_EQUITY_INDEX = 0.20
SF_COMMODITY = {"electricity": 0.40, "oil_gas": 0.18, "metals": 0.18,
                "agricultural": 0.18, "other": 0.18}

SF_CREDIT_SINGLE = {
    CreditQuality.AAA_AA: 0.0038,
    CreditQuality.A: 0.0042,
    CreditQuality.BBB: 0.0054,
    CreditQuality.BB: 0.0106,
    CreditQuality.B: 0.0160,
    CreditQuality.CCC: 0.0600,
    CreditQuality.UNRATED: 0.0106,
}
SF_CREDIT_INDEX_IG = 0.0038
SF_CREDIT_INDEX_SG = 0.0106

#: Correlation of each entity to the systematic factor, used to split the
#: credit and equity add-ons into systematic and idiosyncratic components.
RHO_SINGLE_NAME = 0.50
RHO_INDEX = 0.80

#: Correlations across the three interest-rate maturity buckets (<1y, 1-5y, >5y).
IR_BUCKET_CORR = ((1.0, 0.7, 0.3), (0.7, 1.0, 0.7), (0.3, 0.7, 1.0))


def supervisory_duration(start_years: float, end_years: float) -> float:
    """SD = (e^-0.05S - e^-0.05E)/0.05, floored at the 10-business-day minimum.

    Converts a notional into an interest-rate-equivalent notional. The floor
    stops very short trades from contributing nothing at all.
    """
    s = max(start_years, 0.0)
    e = max(end_years, s + 10.0 / 250.0)
    return (math.exp(-0.05 * s) - math.exp(-0.05 * e)) / 0.05


def supervisory_delta(t: Derivative) -> float:
    """Supervisory delta: +/-1 for linear trades, Black-Scholes-like for options."""
    if not t.is_option:
        return 1.0 if t.direction >= 0 else -1.0

    p = max(t.option_underlying, 1e-9)
    k = max(t.option_strike, 1e-9)
    tau = max(t.end_years, 1e-6)
    sigma = max(t.option_vol, 1e-6)
    d1 = (math.log(p / k) + 0.5 * sigma * sigma * tau) / (sigma * math.sqrt(tau))

    # Long call / short call / long put / short put. `direction` carries the
    # sign and `option_strike > underlying` does not determine call vs put, so
    # we encode puts as a negative strike convention on the caller side; here a
    # positive direction is a purchased option.
    if t.direction >= 0:
        return norm_cdf(d1)
    return -norm_cdf(d1)


def maturity_factor(t: Derivative, ns: NettingSet) -> float:
    """MF — scales the add-on for the risk horizon actually at risk."""
    if ns.margined:
        mpor_years = max(ns.mpor_days, 5) / 250.0
        return 1.5 * math.sqrt(mpor_years)
    return math.sqrt(min(max(t.end_years, 0.0), 1.0) / 1.0)


def _effective_notional(t: Derivative, ns: NettingSet) -> float:
    """Trade-level adjusted notional x supervisory delta x maturity factor."""
    d = t.notional
    if t.asset_class in ("IR", "CREDIT"):
        d *= supervisory_duration(t.start_years, t.end_years)
    return d * supervisory_delta(t) * maturity_factor(t, ns)


def _ir_addon(trades: list[Derivative], ns: NettingSet) -> float:
    """Interest rate add-on: bucket by maturity within each currency hedging set."""
    per_ccy: dict[str, list[float]] = {}
    for t in trades:
        buckets = per_ccy.setdefault(t.hedging_set, [0.0, 0.0, 0.0])
        idx = 0 if t.end_years < 1.0 else (1 if t.end_years <= 5.0 else 2)
        buckets[idx] += _effective_notional(t, ns)

    total = 0.0
    for buckets in per_ccy.values():
        acc = 0.0
        for i in range(3):
            for j in range(3):
                acc += IR_BUCKET_CORR[i][j] * buckets[i] * buckets[j]
        total += SF_INTEREST_RATE * math.sqrt(max(acc, 0.0))
    return total


def _fx_addon(trades: list[Derivative], ns: NettingSet) -> float:
    """FX add-on: full offset within a currency pair, none across pairs."""
    per_pair: dict[str, float] = {}
    for t in trades:
        per_pair[t.hedging_set] = per_pair.get(t.hedging_set, 0.0) + _effective_notional(t, ns)
    return sum(SF_FX * abs(v) for v in per_pair.values())


def _systematic_addon(entity_addons: dict[str, tuple[float, float]]) -> float:
    """Aggregate single-name/index add-ons into systematic + idiosyncratic parts.

    `entity_addons` maps entity -> (add-on, correlation). The Basel formula
    allows partial offset between long and short positions on different names
    through their common correlation to the systematic factor.
    """
    systematic = sum(rho * addon for addon, rho in entity_addons.values())
    idiosyncratic = sum((1.0 - rho * rho) * addon * addon for addon, rho in entity_addons.values())
    return math.sqrt(systematic * systematic + idiosyncratic)


def _credit_addon(trades: list[Derivative], ns: NettingSet, rating: CreditQuality) -> float:
    per_entity: dict[str, tuple[float, float]] = {}
    for t in trades:
        if t.subtype.startswith("index"):
            sf = SF_CREDIT_INDEX_IG if "ig" in t.subtype else SF_CREDIT_INDEX_SG
            rho = RHO_INDEX
        else:
            sf = SF_CREDIT_SINGLE.get(rating, SF_CREDIT_SINGLE[CreditQuality.UNRATED])
            rho = RHO_SINGLE_NAME
        prev_addon, _ = per_entity.get(t.hedging_set, (0.0, rho))
        per_entity[t.hedging_set] = (prev_addon + sf * _effective_notional(t, ns), rho)
    return _systematic_addon(per_entity)


def _equity_addon(trades: list[Derivative], ns: NettingSet) -> float:
    per_entity: dict[str, tuple[float, float]] = {}
    for t in trades:
        is_index = t.subtype.startswith("index")
        sf = SF_EQUITY_INDEX if is_index else SF_EQUITY_SINGLE
        rho = RHO_INDEX if is_index else RHO_SINGLE_NAME
        prev_addon, _ = per_entity.get(t.hedging_set, (0.0, rho))
        per_entity[t.hedging_set] = (prev_addon + sf * _effective_notional(t, ns), rho)
    return _systematic_addon(per_entity)


def _commodity_addon(trades: list[Derivative], ns: NettingSet) -> float:
    per_type: dict[str, float] = {}
    for t in trades:
        sf = SF_COMMODITY.get(t.subtype, SF_COMMODITY["other"])
        per_type[t.subtype] = per_type.get(t.subtype, 0.0) + sf * _effective_notional(t, ns)
    return sum(abs(v) for v in per_type.values())


@dataclass
class SACCRResult:
    replacement_cost: float = 0.0
    addon: float = 0.0
    multiplier: float = 1.0
    pfe: float = 0.0
    ead: float = 0.0


def sa_ccr_ead(ns: NettingSet) -> SACCRResult:
    """EAD for one netting set under SA-CCR."""
    v = ns.market_value
    c = ns.collateral_held

    if ns.margined:
        rc = max(v - c, ns.threshold + ns.mta - ns.nica, 0.0)
    else:
        rc = max(v - c, 0.0)

    by_class: dict[str, list[Derivative]] = {}
    for t in ns.trades:
        by_class.setdefault(t.asset_class, []).append(t)

    addon = 0.0
    addon += _ir_addon(by_class.get("IR", []), ns)
    addon += _fx_addon(by_class.get("FX", []), ns)
    addon += _credit_addon(by_class.get("CREDIT", []), ns, ns.rating)
    addon += _equity_addon(by_class.get("EQUITY", []), ns)
    addon += _commodity_addon(by_class.get("COMMODITY", []), ns)

    if addon <= 0:
        multiplier = 1.0
    else:
        exponent = (v - c) / (2.0 * (1.0 - MULTIPLIER_FLOOR) * addon)
        # Guard the exponential: deeply out-of-the-money sets would otherwise
        # overflow to inf on the way to a multiplier of 1.
        exponent = min(exponent, 50.0)
        multiplier = min(1.0, MULTIPLIER_FLOOR + (1.0 - MULTIPLIER_FLOOR) * math.exp(exponent))

    pfe = multiplier * addon
    return SACCRResult(
        replacement_cost=rc,
        addon=addon,
        multiplier=multiplier,
        pfe=pfe,
        ead=ALPHA * (rc + pfe),
    )


# ---------------------------------------------------------------------------
# BA-CVA (reduced version)
# ---------------------------------------------------------------------------

#: Supervisory CVA risk weights by counterparty sector and credit quality.
#: IG means BBB- or better.
CVA_RW = {
    "sovereign": (0.005, 0.030),
    "local_government": (0.010, 0.040),
    "financial": (0.050, 0.120),
    "basic_materials": (0.030, 0.070),
    "consumer": (0.030, 0.085),
    "technology": (0.020, 0.055),
    "healthcare_utilities": (0.015, 0.050),
    "other": (0.050, 0.120),
}

#: Single supervisory correlation across counterparties in the reduced version.
CVA_RHO = 0.50
#: The discount scalar the Basel framework applies to the basic approach.
CVA_DISCOUNT_SCALAR = 0.65

_IG_BANDS = (CreditQuality.AAA_AA, CreditQuality.A, CreditQuality.BBB)


def cva_risk_weight(sector: str, rating: CreditQuality) -> float:
    ig_rw, hy_rw = CVA_RW.get(sector, CVA_RW["other"])
    return ig_rw if rating in _IG_BANDS else hy_rw


def cva_discount_factor(maturity_years: float) -> float:
    """(1 - e^-0.05M)/(0.05M) — the non-IMM supervisory discount factor."""
    m = max(maturity_years, 1e-6)
    return (1.0 - math.exp(-0.05 * m)) / (0.05 * m)


def netting_set_maturity(ns: NettingSet) -> float:
    """Effective maturity of a netting set: notional-weighted, not the longest.

    Taking the longest trade would let a single 30-year swap set the maturity
    for a book of one-year FX forwards, which overstates CVA by a wide margin.
    """
    total_notional = sum(abs(t.notional) for t in ns.trades)
    if total_notional <= 0:
        return 1.0
    weighted = sum(abs(t.notional) * max(t.end_years, 0.0) for t in ns.trades)
    return max(weighted / total_notional, 1.0)


@dataclass
class CVAResult:
    capital: float = 0.0
    rwa: float = 0.0
    by_counterparty: dict[str, float] = field(default_factory=dict)
    exempt_counterparties: list[str] = field(default_factory=list)


def ba_cva(netting_sets: list[NettingSet], eads: dict[str, float] | None = None) -> CVAResult:
    """Reduced BA-CVA capital and RWA across all counterparties.

    `eads` optionally supplies pre-computed SA-CCR EADs keyed by counterparty;
    otherwise they are recomputed here.
    """
    scva_by_cpty: dict[str, float] = {}
    exempt: list[str] = []

    for ns in netting_sets:
        if ns.cva_exempt:
            exempt.append(ns.counterparty)
            continue
        ead = (eads or {}).get(ns.counterparty)
        if ead is None:
            ead = sa_ccr_ead(ns).ead
        m = netting_set_maturity(ns)
        rw = cva_risk_weight(ns.sector, ns.rating)
        scva = (1.0 / ALPHA) * rw * m * ead * cva_discount_factor(m)
        scva_by_cpty[ns.counterparty] = scva_by_cpty.get(ns.counterparty, 0.0) + scva

    values = list(scva_by_cpty.values())
    systematic = CVA_RHO * sum(values)
    idiosyncratic = (1.0 - CVA_RHO ** 2) * sum(v * v for v in values)
    k_reduced = math.sqrt(systematic * systematic + idiosyncratic)

    capital = CVA_DISCOUNT_SCALAR * k_reduced
    return CVAResult(capital=capital, rwa=capital * 12.5,
                     by_counterparty=scva_by_cpty, exempt_counterparties=exempt)


def counterparty_credit_rwa(
    netting_sets: list[NettingSet], risk_weight_by_counterparty: dict[str, float]
) -> tuple[float, dict[str, float]]:
    """CCR RWA = SA-CCR EAD x the counterparty's credit risk weight."""
    total = 0.0
    eads: dict[str, float] = {}
    for ns in netting_sets:
        ead = sa_ccr_ead(ns).ead
        eads[ns.counterparty] = eads.get(ns.counterparty, 0.0) + ead
        rw = risk_weight_by_counterparty.get(ns.counterparty, 1.00)
        total += ead * rw
    return total, eads
