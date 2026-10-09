"""
Macroeconomic scenarios and the systematic factor that drives credit losses.

A scenario is a path of macro variables. Everything downstream — impairment,
trading revenue, fee income, funding costs, the value of the mortgage book —
reads from that path rather than being set by hand, so a single scenario change
propagates consistently through the whole model.

The bridge between macro and credit is a **single systematic factor Z** per
portfolio segment, in the Vasicek sense: Z > 0 is a good state of the world,
Z < 0 a bad one, and a conditional PD is recovered as

    PD(Z) = N( ( G(PD_TTC) - sqrt(rho) Z ) / sqrt(1 - rho) )

Z is built as a weighted sum of standardised deviations of macro variables from
their through-the-cycle reference levels, with the weights differing by segment
(a mortgage book cares about unemployment and house prices; a leveraged finance
book cares about GDP and high-yield spreads).

The scenario paths themselves are STYLISED. `acs_severe` is shaped like the
Bank of England's published annual cyclical scenario — a sharp GDP contraction,
unemployment roughly doubling, a deep house-price and CRE fall, an equity crash
and a spread blowout — but the numbers are ours, not the Bank's. Anyone wanting
the real thing should substitute the published ACS variable paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .units import Provenance, norm_cdf, norm_ppf

# ---------------------------------------------------------------------------
# Macro state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MacroState:
    """One year of the macroeconomy. Rates and growth rates are decimals."""

    year: int
    gdp_growth: float = 0.015
    unemployment: float = 0.044
    bank_rate: float = 0.035
    gilt_5y: float = 0.038
    #: Annual growth in the house price and commercial property indices.
    hpi_growth: float = 0.030
    cre_growth: float = 0.020
    equity_return: float = 0.060
    gbp_usd: float = 1.27
    ig_spread: float = 0.012
    hy_spread: float = 0.040
    #: An implied-volatility index, 1.0 = long-run normal. Drives trading revenue.
    volatility_index: float = 1.00
    #: Primary issuance and M&A activity, 1.0 = long-run normal. Drives fees.
    activity_index: float = 1.00


#: Through-the-cycle reference levels and the standard deviations used to
#: normalise deviations from them. STYLISED, but of the right order for the UK.
TTC_REFERENCE = MacroState(year=0)
MACRO_SIGMA = {
    "gdp_growth": 0.020,
    "unemployment": 0.015,
    "bank_rate": 0.020,
    "hpi_growth": 0.070,
    "cre_growth": 0.100,
    "equity_return": 0.200,
    "ig_spread": 0.008,
    "hy_spread": 0.030,
}

#: Segment loadings on each macro variable. Positive means "a rise in this
#: variable is good for this segment"; the sign convention is applied once,
#: here, so that Z comes out with high = benign everywhere.
SEGMENT_LOADINGS: dict[str, dict[str, float]] = {
    "mortgages": {"unemployment": -0.55, "hpi_growth": 0.35, "bank_rate": -0.10},
    "corporate": {"gdp_growth": 0.45, "unemployment": -0.20, "hy_spread": -0.35},
    "leveraged_finance": {"gdp_growth": 0.35, "hy_spread": -0.50, "equity_return": 0.15},
    "financial": {"equity_return": 0.25, "ig_spread": -0.50, "gdp_growth": 0.25},
    "sovereign": {"gdp_growth": 0.60, "ig_spread": -0.40},
    "cre": {"cre_growth": 0.55, "gdp_growth": 0.20, "bank_rate": -0.25},
    "prime_brokerage": {"equity_return": 0.40, "ig_spread": -0.30, "gdp_growth": 0.30},
}
DEFAULT_SEGMENT = "corporate"

#: Scales the weighted deviation into a standard-normal-like factor. Calibrated
#: so the severe scenario's trough lands near Z = -1.65, which lifts a 0.2%
#: corporate PD to roughly 1.4%, a six-fold increase of the order UK stress
#: tests imply. This is the single most powerful dial in the model: it drives
#: impairment, IRB PD migration and the IFRS 9 stage 2 share together, so
#: recalibrating it moves every stress result. STYLISED.
Z_SCALE = 0.90


def systematic_factor(state: MacroState, segment: str = DEFAULT_SEGMENT) -> float:
    """Z for one segment in one year. Positive is benign."""
    loadings = SEGMENT_LOADINGS.get(segment, SEGMENT_LOADINGS[DEFAULT_SEGMENT])
    z = 0.0
    for var, weight in loadings.items():
        sigma = MACRO_SIGMA.get(var, 1.0)
        deviation = (getattr(state, var) - getattr(TTC_REFERENCE, var)) / sigma
        z += weight * deviation
    return Z_SCALE * z


def conditional_pd(pd_ttc: float, z: float, rho: float = 0.15) -> float:
    """Point-in-time PD given the systematic factor. rho is the asset correlation.

    Note the form. The textbook Vasicek conditional PD is

        N( ( G(PD) - sqrt(rho) Z ) / sqrt(1 - rho) )

    and that is what the Basel capital formula uses, at Z = G(0.999). But its
    value at Z = 0 is N(G(PD)/sqrt(1-rho)), which is *below* PD — the
    unconditional PD is the mean over Z, not the value at the median. Using
    that form for scenario conditioning silently shrinks every PD in a neutral
    scenario; for a 0.22% corporate PD at rho = 0.12 it returns 0.12%.

    So the shock is applied without rescaling the level:

        N( G(PD) - sqrt( rho / (1 - rho) ) Z )

    which reproduces PD exactly at Z = 0 and gives a comparable response in the
    tail. The Basel risk-weight function in `credit_risk` is untouched and
    still uses the regulatory form.
    """
    pd_ttc = min(max(pd_ttc, 1e-6), 0.9999)
    shock = (rho / (1.0 - rho)) ** 0.5 * z
    return norm_cdf(norm_ppf(pd_ttc) - shock)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    """A named macro path, with the weight it carries in an IFRS 9 ECL average."""

    name: str
    description: str
    path: list[MacroState]
    weight: float = 1.0
    provenance: Provenance = Provenance.STYLISED

    def state(self, year: int) -> MacroState:
        """The state for a calendar year, holding the last value flat beyond
        the end of the published path."""
        for s in self.path:
            if s.year == year:
                return s
        if year < self.path[0].year:
            return self.path[0]
        return self.path[-1]

    @property
    def years(self) -> list[int]:
        return [s.year for s in self.path]


def _baseline(start_year: int = 2027, n: int = 5) -> list[MacroState]:
    """A steady UK expansion: growth near trend, unemployment flat, Bank Rate
    drifting down towards a neutral setting."""
    out = []
    for i in range(n):
        out.append(MacroState(
            year=start_year + i,
            gdp_growth=0.013 + 0.002 * min(i, 2),
            unemployment=0.045 - 0.001 * min(i, 2),
            bank_rate=0.0375 - 0.0025 * min(i, 3),
            gilt_5y=0.040 - 0.002 * min(i, 3),
            hpi_growth=0.025 + 0.002 * min(i, 2),
            cre_growth=0.015 + 0.003 * min(i, 2),
            equity_return=0.065,
            gbp_usd=1.27 + 0.005 * i,
            ig_spread=0.012,
            hy_spread=0.038,
            volatility_index=1.00,
            activity_index=1.00,
        ))
    return out


def _acs_severe(start_year: int = 2027, n: int = 5) -> list[MacroState]:
    """Shaped like a Bank of England annual cyclical scenario: a sharp
    contraction in year 1, a trough in year 2, then a slow recovery.

    Note the rate path — a stress in which Bank Rate *rises* before it falls,
    because the scenario assumes a supply shock the MPC must lean against. That
    combination (falling asset prices with rising funding costs) is what makes
    the ACS bite for a bank with a large fixed-rate book.
    """
    shape = [
        # gdp,  unemp, rate,  hpi,   cre,   equity, ig,    hy,    vol, activity
        (-0.030, 0.058, 0.055, -0.140, -0.220, -0.350, 0.028, 0.095, 2.20, 0.55),
        (-0.015, 0.082, 0.045, -0.145, -0.200, -0.120, 0.032, 0.110, 1.90, 0.45),
        (0.012, 0.079, 0.030, 0.010, -0.040, 0.180, 0.020, 0.065, 1.35, 0.70),
        (0.020, 0.068, 0.025, 0.030, 0.020, 0.120, 0.015, 0.048, 1.15, 0.90),
        (0.018, 0.058, 0.028, 0.030, 0.025, 0.090, 0.013, 0.042, 1.05, 1.00),
    ]
    out = []
    for i in range(n):
        g, u, r, h, c, e, ig, hy, vol, act = shape[min(i, len(shape) - 1)]
        out.append(MacroState(
            year=start_year + i, gdp_growth=g, unemployment=u, bank_rate=r,
            gilt_5y=r + 0.005, hpi_growth=h, cre_growth=c, equity_return=e,
            gbp_usd=1.13 + 0.02 * i, ig_spread=ig, hy_spread=hy,
            volatility_index=vol, activity_index=act,
        ))
    return out


def _stagflation(start_year: int = 2027, n: int = 5) -> list[MacroState]:
    """Inflation persists, so rates stay high while growth stalls. Good for
    net interest income, bad for credit quality and for fee pools."""
    out = []
    for i in range(n):
        out.append(MacroState(
            year=start_year + i,
            gdp_growth=0.002 if i < 3 else 0.008,
            unemployment=0.050 + 0.004 * min(i, 3),
            bank_rate=0.055 - 0.003 * max(0, i - 2),
            gilt_5y=0.058 - 0.003 * max(0, i - 2),
            hpi_growth=-0.020 if i < 3 else 0.005,
            cre_growth=-0.045 if i < 3 else 0.010,
            equity_return=-0.020 if i < 2 else 0.040,
            gbp_usd=1.20,
            ig_spread=0.018, hy_spread=0.058,
            volatility_index=1.45, activity_index=0.78,
        ))
    return out


def _upside(start_year: int = 2027, n: int = 5) -> list[MacroState]:
    """The IFRS 9 upside scenario. Needed because ECL is convex in the macro
    path — averaging over scenarios gives a different answer from running the
    central path alone, and that difference is the point of the exercise."""
    out = []
    for i in range(n):
        out.append(MacroState(
            year=start_year + i,
            gdp_growth=0.028, unemployment=0.038, bank_rate=0.030,
            gilt_5y=0.034, hpi_growth=0.055, cre_growth=0.045,
            equity_return=0.120, gbp_usd=1.34, ig_spread=0.008, hy_spread=0.028,
            volatility_index=0.85, activity_index=1.25,
        ))
    return out


def standard_scenarios(start_year: int = 2027, n: int = 5) -> dict[str, Scenario]:
    """The scenario set used for planning and for IFRS 9 ECL weighting.

    The weights are the kind of split UK banks disclose: most of the weight on
    the central case, a meaningful tail weight on the downside.
    """
    return {
        "baseline": Scenario(
            "baseline", "Central case: trend growth, Bank Rate easing to neutral",
            _baseline(start_year, n), weight=0.45),
        "upside": Scenario(
            "upside", "Stronger growth, firmer asset prices, tighter spreads",
            _upside(start_year, n), weight=0.20),
        "stagflation": Scenario(
            "stagflation", "Persistent inflation: high rates, stalled growth",
            _stagflation(start_year, n), weight=0.20),
        "acs_severe": Scenario(
            "acs_severe", "Severe stress shaped like the BoE annual cyclical scenario",
            _acs_severe(start_year, n), weight=0.15),
    }
