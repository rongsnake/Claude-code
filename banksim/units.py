"""
Units, provenance tagging and the small numeric helpers used everywhere else.

Money is carried as a float in **millions of pounds** (£m) throughout. Rates,
risk weights and haircuts are carried as **decimals** (0.02 == 2%), never as
percentage points — the single most common source of silent factor-of-100 bugs
in capital models, so the convention is enforced by naming: anything ending
`_pct` is a decimal fraction, anything ending `_bps` is basis points.

`Provenance` is the honesty mechanism. A capital model is only as trustworthy
as its inputs, and a simulator's inputs are mostly invented. Tagging each one
lets the reports separate "this is what the rulebook says" from "this is a
number we made up for a fictional bank".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from statistics import NormalDist
from typing import Iterable

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class Provenance(str, Enum):
    """Where a number came from. Printed in the assumptions appendix."""

    #: Fixed by the rulebook — a supervisory risk weight, a floor, a CCF.
    REGULATORY = "regulatory"
    #: Firm-specific and set by the supervisor — Pillar 2A, the PRA buffer.
    #: Real firms' values are disclosed (P2A) or confidential (PRA buffer);
    #: ours are plausible placeholders.
    SUPERVISORY = "supervisory"
    #: Taken from published market or peer data (index levels, spread ranges).
    MARKET_REF = "market-reference"
    #: Invented for the simulation. NOT a real firm's number.
    STYLISED = "stylised"
    #: Computed from the above by the model.
    DERIVED = "derived"


@dataclass(frozen=True)
class Assumption:
    """A single named input, with enough metadata to defend it in a footnote."""

    name: str
    value: float
    provenance: Provenance
    note: str = ""
    source: str = ""
    unit: str = ""

    def __float__(self) -> float:
        return float(self.value)

    def describe(self) -> str:
        unit = f" {self.unit}" if self.unit else ""
        src = f"  [{self.source}]" if self.source else ""
        return f"{self.name} = {self.value:g}{unit}  ({self.provenance.value}){src}"


class AssumptionSet:
    """Ordered registry of assumptions, so a run can print exactly what it used."""

    def __init__(self) -> None:
        self._items: dict[str, Assumption] = {}

    def add(self, a: Assumption) -> Assumption:
        self._items[a.name] = a
        return a

    def value(self, name: str, default: float | None = None) -> float:
        if name in self._items:
            return self._items[name].value
        if default is None:
            raise KeyError(f"no assumption named {name!r}")
        return default

    def by_provenance(self, p: Provenance) -> list[Assumption]:
        return [a for a in self._items.values() if a.provenance is p]

    def __iter__(self) -> Iterable[Assumption]:
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def stylised_share(self) -> float:
        """Fraction of registered inputs that are invented. Reported up front."""
        if not self._items:
            return 0.0
        n = sum(1 for a in self._items.values() if a.provenance is Provenance.STYLISED)
        return n / len(self._items)


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

_NORM = NormalDist()


def norm_cdf(x: float) -> float:
    """Standard normal CDF — N(.) in the Basel IRB risk-weight function."""
    return _NORM.cdf(x)


def norm_ppf(p: float) -> float:
    """Standard normal inverse CDF — G(.) in the Basel IRB risk-weight function.

    Clamped away from the open interval's endpoints: G(0) and G(1) are infinite,
    and a PD of exactly 0 or 1 is a data error we would rather survive than
    crash on.
    """
    p = min(max(p, 1e-12), 1.0 - 1e-12)
    return _NORM.inv_cdf(p)


#: The rate at which the PRA converted euro thresholds into sterling.
#:
#: The CRR and the Basel text set dozens of thresholds in euro. Rather than let
#: firms use the euro figures — which it declined to permit, on competition and
#: safety-and-soundness grounds, so that every UK bank uses the same numbers —
#: the PRA redenominated them using the average daily spot rate over the twelve
#: months to 10 July 2020, rounded to two significant figures. That works out
#: at 0.88, which is why the operational risk buckets break at £880m and £26bn
#: rather than £1bn and £30bn.
PRA_EUR_GBP_RATE = 0.88


def redenominate_eur_to_gbp(eur: float) -> float:
    """Apply the PRA's euro-to-sterling redenomination, to two significant figures.

    Deriving the sterling thresholds rather than hard-coding them keeps the
    convention visible and makes every threshold in the model consistent with
    every other one — the tests check the derived values against the figures
    the PRA actually publishes.
    """
    value = eur * PRA_EUR_GBP_RATE
    if value == 0:
        return 0.0
    magnitude = math.floor(math.log10(abs(value)))
    factor = 10.0 ** (magnitude - 1)
    return round(value / factor) * factor


def bps(x: float) -> float:
    """Basis points -> decimal. bps(25) == 0.0025."""
    return x / 10_000.0


def pct(x: float) -> float:
    """Percentage points -> decimal. pct(2.5) == 0.025."""
    return x / 100.0


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    """Division that returns `default` rather than raising on a zero divisor.

    Capital ratios are full of denominators (RWAs, exposure measures, outflows)
    that are legitimately zero in a degenerate or newly-started portfolio.
    """
    return num / den if den else default


def sqrt_sum_sq(values: Iterable[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


def fmt_gbp_m(x: float) -> str:
    """Format £m with thousands separators, and in £bn once it gets silly."""
    if abs(x) >= 1_000:
        return f"£{x / 1_000:,.2f}bn"
    return f"£{x:,.1f}m"


def fmt_pct(x: float, dp: int = 2) -> str:
    return f"{x * 100:.{dp}f}%"
