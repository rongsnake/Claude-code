"""
banksim — a commercial/investment banking simulator built from first principles.

Models a hypothetical UK wholesale bank ("Kingsgate Bank plc") end to end:
its balance sheet, its P&L, the regulatory capital and liquidity it must hold
under the UK implementation of Basel 3.1, and how all three move together
through a macroeconomic scenario.

Design rules (inherited from this repo's data-honesty conventions):
  * Every number carries a `Provenance`. Regulatory parameters are the rules as
    written; anything invented for the simulation is tagged `STYLISED` and the
    reports banner it. The bank is hypothetical — no output here is a statement
    about any real firm.
  * The core engine depends only on the Python standard library, so it runs on
    a Raspberry Pi with no wheels to build.

Entry point:  python -m banksim.cli --help
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
