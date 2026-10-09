"""
Market risk under the FRTB standardised approach.

Three components, added together and then multiplied by 12.5 to become RWAs:

  * **SBM** — the sensitivities-based method: weighted sensitivities aggregated
    within and across buckets under three correlation scenarios, of which the
    worst is taken.
  * **DRC** — default risk charge: jump-to-default exposures, netted within a
    bucket with a hedge-benefit haircut.
  * **RRAO** — residual risk add-on: a flat notional charge for exotic and
    other-residual instruments that the SBM cannot see.

Scope and honesty about it
--------------------------
This is a *reduced but structurally faithful* SBM. What is real: the
weighted-sensitivity construction, the within-bucket and across-bucket
aggregation formulae, the three correlation scenarios and the negative-root
fallback, the GIRR tenor correlation function, the DRC netting and hedge-benefit
ratio, and the RRAO. What is simplified and must be replaced before any number
here is used for anything but simulation:

  * vega and curvature are modelled per risk class but with a single
    prescribed shock rather than the full per-bucket vega risk-weight and
    curvature shock machinery;
  * the cross-bucket correlation matrices (gamma) are collapsed to the
    dominant Basel values rather than the full published matrices;
  * securitisation (CTP and non-CTP) CSR is not implemented.

Each such simplification is marked `SIMPLIFIED` in a comment so they can be
found and closed out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .exposures import CreditQuality, JumpToDefault, Sensitivity, TradingBook
from .units import safe_div

RWA_MULTIPLIER = 12.5

# ---------------------------------------------------------------------------
# Risk weights
# ---------------------------------------------------------------------------

#: GIRR delta risk weights by tenor (years), as a fraction per unit shift.
GIRR_RW = {
    0.25: 0.017, 0.5: 0.017, 1.0: 0.016, 2.0: 0.013, 3.0: 0.012,
    5.0: 0.011, 10.0: 0.011, 15.0: 0.011, 20.0: 0.011, 30.0: 0.011,
}
#: Inflation and cross-currency basis are single factors per currency.
GIRR_RW_INFLATION = 0.016
#: Currencies for which the rules permit the risk weights to be divided by
#: sqrt(2). A GBP-reporting wholesale bank gets most of its GIRR relief here.
GIRR_LIQUID_CCY = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "SEK"}
GIRR_THETA = 0.03           # tenor correlation decay
GIRR_TENOR_CORR_FLOOR = 0.40
GIRR_GAMMA = 0.50           # across currencies

#: CSR non-securitisation delta risk weights by bucket.
#: Bucket labels follow the Basel sector/credit-quality grid. SIMPLIFIED: the
#: covered-bond and index buckets are folded in at their headline weights.
CSR_RW = {
    "sovereign_ig": 0.005,
    "local_govt_ig": 0.010,
    "financial_ig": 0.050,
    "industrial_ig": 0.030,
    "consumer_ig": 0.030,
    "tech_telecom_ig": 0.020,
    "health_utilities_ig": 0.015,
    "covered_bond_ig": 0.010,
    "sovereign_hy": 0.020,
    "local_govt_hy": 0.040,
    "financial_hy": 0.120,
    "industrial_hy": 0.070,
    "consumer_hy": 0.085,
    "tech_telecom_hy": 0.055,
    "health_utilities_hy": 0.050,
    "other_sector": 0.120,
    "index_ig": 0.015,
    "index_hy": 0.050,
}
CSR_RHO_NAME_DIFFERENT = 0.35
CSR_RHO_TENOR_DIFFERENT = 0.65
CSR_RHO_BASIS_DIFFERENT = 0.999
#: SIMPLIFIED: flat cross-bucket correlation in place of the published matrix.
CSR_GAMMA = 0.50

#: Equity delta risk weights by bucket.
EQ_RW = {
    "em_large_consumer": 0.55, "em_large_industrial": 0.60, "em_large_financial": 0.45,
    "em_large_other": 0.55, "adv_large_consumer": 0.30, "adv_large_industrial": 0.35,
    "adv_large_financial": 0.40, "adv_large_other": 0.50, "em_small": 0.70,
    "adv_small": 0.50, "other_sector": 0.70, "index_large": 0.15, "index_other": 0.25,
}
EQ_RHO_SAME_BUCKET = 0.15
EQ_GAMMA = 0.15

#: FX delta risk weight — one weight for every currency pair, halved by the
#: sqrt(2) relief for the specified liquid pairs.
FX_RW = 0.15
FX_LIQUID_PAIRS = {"GBPUSD", "GBPEUR", "EURUSD", "USDJPY", "GBPJPY", "USDCHF", "AUDUSD"}
FX_GAMMA = 0.60

COMM_RW = {
    "energy_electricity": 0.60, "energy_oil": 0.35, "energy_gas": 0.45,
    "metals_precious": 0.20, "metals_base": 0.40, "agricultural": 0.35, "other": 0.50,
}
COMM_GAMMA = 0.20

#: DRC risk weights by rating, applied to jump-to-default exposures.
DRC_RW = {
    CreditQuality.AAA_AA: 0.02,
    CreditQuality.A: 0.03,
    CreditQuality.BBB: 0.06,
    CreditQuality.BB: 0.15,
    CreditQuality.B: 0.30,
    CreditQuality.CCC: 0.50,
    CreditQuality.UNRATED: 0.15,
}

#: Residual risk add-on: 1.0% of notional for instruments with an exotic
#: underlying, 0.1% for everything else carrying residual risk.
RRAO_EXOTIC = 0.010
RRAO_OTHER = 0.001

#: Vega risk weights. RW = min(0.55 x sqrt(LH/10), 100%), where LH is the
#: prescribed liquidity horizon for the risk class. Most classes cap at 100%,
#: which is why vega is expensive under the standardised approach.
VEGA_LIQUIDITY_HORIZON = {"GIRR": 60, "CSR": 120, "EQ": 20, "FX": 40, "COMM": 120}
VEGA_RW_SIGMA = 0.55


def vega_risk_weight(risk_class: str) -> float:
    lh = VEGA_LIQUIDITY_HORIZON.get(risk_class, 60)
    return min(VEGA_RW_SIGMA * math.sqrt(lh / 10.0), 1.0)


#: Curvature. SIMPLIFIED: rather than re-pricing the book under the prescribed
#: up and down shocks, the caller supplies the curvature loss (CVR) directly as
#: the sensitivity value, so the risk weight here is 1.0 and only the
#: aggregation machinery is applied.
CURVATURE_RW = 1.0

#: The three prescribed correlation scenarios. `medium` uses the correlations
#: as published; `high` scales them up (capped at 1); `low` scales them down.
CORRELATION_SCENARIOS = ("low", "medium", "high")


def _scenario_corr(rho: float, scenario: str) -> float:
    if scenario == "high":
        return min(1.0, rho * 1.25)
    if scenario == "low":
        return max(2.0 * rho - 1.0, 0.75 * rho)
    return rho


# ---------------------------------------------------------------------------
# Generic SBM aggregation
# ---------------------------------------------------------------------------


def _bucket_charge(
    weighted: list[tuple[str, float]],
    corr_fn,
    scenario: str,
) -> tuple[float, float]:
    """K_b and S_b for one bucket.

    `weighted` is a list of (factor label, weighted sensitivity). `corr_fn`
    returns the correlation between two factor labels before the scenario
    scaling is applied.
    """
    acc = 0.0
    for i, (fi, wi) in enumerate(weighted):
        acc += wi * wi
        for fj, wj in weighted[i + 1:]:
            rho = _scenario_corr(corr_fn(fi, fj), scenario)
            acc += 2.0 * rho * wi * wj
    k_b = math.sqrt(max(acc, 0.0))
    s_b = sum(w for _, w in weighted)
    return k_b, s_b


def _aggregate_buckets(
    buckets: dict[str, tuple[float, float]], gamma: float, scenario: str
) -> float:
    """Aggregate bucket-level (K_b, S_b) into a risk-class charge.

    Where the term under the square root goes negative — possible because the
    cross-bucket term is not a true covariance — the rules substitute
    S_b* = max(min(sum WS, K_b), -K_b) and recompute.
    """
    g = _scenario_corr(gamma, scenario)
    keys = list(buckets)

    def total(use_alternative: bool) -> float:
        acc = 0.0
        svals = {}
        for b in keys:
            k_b, s_b = buckets[b]
            svals[b] = max(min(s_b, k_b), -k_b) if use_alternative else s_b
            acc += k_b * k_b
        for i, b in enumerate(keys):
            for c in keys[i + 1:]:
                acc += 2.0 * g * svals[b] * svals[c]
        return acc

    acc = total(use_alternative=False)
    if acc < 0:
        acc = total(use_alternative=True)
    return math.sqrt(max(acc, 0.0))


# ---------------------------------------------------------------------------
# Per-risk-class weighting and correlations
# ---------------------------------------------------------------------------


def _tenor_or_none(label: str) -> float | None:
    try:
        return float(label)
    except ValueError:
        return None


def _girr_weight(s: Sensitivity) -> float:
    tenor = _tenor_or_none(s.factor)
    rw = GIRR_RW.get(tenor, 0.011) if tenor is not None else GIRR_RW_INFLATION
    if s.bucket in GIRR_LIQUID_CCY:
        rw /= math.sqrt(2.0)
    return rw * s.value


def _girr_corr(fa: str, fb: str) -> float:
    """rho = max(exp(-theta |Tk-Tl| / min(Tk,Tl)), 40%)."""
    if fa == fb:
        return 1.0
    ta, tb = _tenor_or_none(fa), _tenor_or_none(fb)
    # Inflation, cross-currency basis and the vega/curvature aggregates are not
    # points on a curve, so they take the floor correlation against everything.
    if ta is None or tb is None:
        return GIRR_TENOR_CORR_FLOOR
    lo = min(ta, tb)
    if lo <= 0:
        return GIRR_TENOR_CORR_FLOOR
    return max(math.exp(-GIRR_THETA * abs(ta - tb) / lo), GIRR_TENOR_CORR_FLOOR)


def _csr_corr(fa: str, fb: str) -> float:
    """Factor labels are "<name>|<tenor>"; same name and tenor correlate at 1."""
    if fa == fb:
        return 1.0
    na, _, ta = fa.partition("|")
    nb, _, tb = fb.partition("|")
    rho = 1.0
    if na != nb:
        rho *= CSR_RHO_NAME_DIFFERENT
    if ta != tb:
        rho *= CSR_RHO_TENOR_DIFFERENT
    return rho * CSR_RHO_BASIS_DIFFERENT


def _flat_corr(rho: float):
    def fn(fa: str, fb: str) -> float:
        return 1.0 if fa == fb else rho
    return fn


_RISK_CLASS_SPEC = {
    "GIRR": (_girr_weight, _girr_corr, GIRR_GAMMA),
    "CSR": (lambda s: CSR_RW.get(s.bucket, 0.05) * s.value, _csr_corr, CSR_GAMMA),
    "EQ": (lambda s: EQ_RW.get(s.bucket, 0.50) * s.value, _flat_corr(EQ_RHO_SAME_BUCKET), EQ_GAMMA),
    "FX": (
        lambda s: (FX_RW / math.sqrt(2.0) if s.bucket in FX_LIQUID_PAIRS else FX_RW) * s.value,
        _flat_corr(1.0),
        FX_GAMMA,
    ),
    "COMM": (lambda s: COMM_RW.get(s.bucket, 0.50) * s.value, _flat_corr(0.20), COMM_GAMMA),
}


def sbm_risk_class(sensitivities: list[Sensitivity], risk_class: str, kind: str = "delta") -> float:
    """SBM charge for one risk class and one sensitivity kind."""
    delta_weight_fn, corr_fn, gamma = _RISK_CLASS_SPEC[risk_class]
    relevant = [s for s in sensitivities if s.risk_class == risk_class and s.kind == kind]
    if not relevant:
        return 0.0

    if kind == "delta":
        weight_fn = delta_weight_fn
    elif kind == "vega":
        rw = vega_risk_weight(risk_class)
        weight_fn = lambda s: rw * s.value            # noqa: E731
    else:
        weight_fn = lambda s: CURVATURE_RW * s.value  # noqa: E731

    by_bucket: dict[str, list[tuple[str, float]]] = {}
    for s in relevant:
        by_bucket.setdefault(s.bucket, []).append((s.factor, weight_fn(s)))

    worst = 0.0
    for scenario in CORRELATION_SCENARIOS:
        buckets = {b: _bucket_charge(ws, corr_fn, scenario) for b, ws in by_bucket.items()}
        worst = max(worst, _aggregate_buckets(buckets, gamma, scenario))
    return worst


def sbm_charge(sensitivities: list[Sensitivity]) -> dict[str, float]:
    """SBM capital charge by risk class and kind, plus the total."""
    out: dict[str, float] = {}
    total = 0.0
    for rc in _RISK_CLASS_SPEC:
        for kind in ("delta", "vega", "curvature"):
            charge = sbm_risk_class(sensitivities, rc, kind)
            if charge:
                out[f"{rc}_{kind}"] = charge
                total += charge
    out["total"] = total
    return out


# ---------------------------------------------------------------------------
# Default risk charge
# ---------------------------------------------------------------------------


def drc_charge(jtds: list[JumpToDefault]) -> float:
    """Non-securitisation DRC: net within bucket, haircut the short hedges.

    The weighted-to-short ratio (WtS) recognises that short positions hedge
    long ones imperfectly — a fully hedged bucket still carries a charge.
    """
    by_bucket: dict[str, list[JumpToDefault]] = {}
    for j in jtds:
        by_bucket.setdefault(j.bucket, []).append(j)

    total = 0.0
    for positions in by_bucket.values():
        # Net JTD by issuer first: offsetting is permitted within an issuer.
        by_issuer: dict[str, tuple[float, CreditQuality]] = {}
        for p in positions:
            prev, _ = by_issuer.get(p.issuer, (0.0, p.rating))
            by_issuer[p.issuer] = (prev + p.jtd, p.rating)

        long_jtd = sum(v for v, _ in by_issuer.values() if v > 0)
        short_jtd = sum(-v for v, _ in by_issuer.values() if v < 0)
        wts = safe_div(long_jtd, long_jtd + short_jtd, default=0.0)

        weighted_long = sum(
            DRC_RW.get(r, 0.15) * v for v, r in by_issuer.values() if v > 0
        )
        weighted_short = sum(
            DRC_RW.get(r, 0.15) * (-v) for v, r in by_issuer.values() if v < 0
        )
        total += max(weighted_long - wts * weighted_short, 0.0)

    return total


def rrao_charge(book: TradingBook) -> float:
    return RRAO_EXOTIC * book.exotic_notional + RRAO_OTHER * book.other_residual_notional


# ---------------------------------------------------------------------------
# Total
# ---------------------------------------------------------------------------


@dataclass
class MarketRiskResult:
    sbm: float = 0.0
    drc: float = 0.0
    rrao: float = 0.0
    components: dict[str, float] = field(default_factory=dict)

    @property
    def capital(self) -> float:
        return self.sbm + self.drc + self.rrao

    @property
    def rwa(self) -> float:
        return self.capital * RWA_MULTIPLIER


def market_risk_rwa(book: TradingBook) -> MarketRiskResult:
    components = sbm_charge(book.sensitivities)
    return MarketRiskResult(
        sbm=components.pop("total", 0.0),
        drc=drc_charge(book.jtds),
        rrao=rrao_charge(book),
        components=components,
    )
