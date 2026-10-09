"""
The Long Ledger — a turn-based history of one banking house, from a bench on
the Rialto in 1300 to designation as a UK G-SIB.

The game is data-driven. Everything historical lives in these modules as plain
dicts — eras and their rules, cities and their rise and fall, the financial
innovations you can adopt, the borrower classes you can lend to, and the
scripted events that hit whoever is exposed — and `build.py` bakes it into a
single HTML page whose JavaScript engine plays the turns. The Python side owns
the history and is what the tests check; the page owns the play.

Honesty rule, inherited from the rest of banksim: every event and parameter
carries a provenance. `HISTORICAL` means the date and the shape of the thing
are real; `STYLISED` means the number is a game dial tuned for play. The house
itself is fictional. No real bank's figures appear anywhere.
"""

from .eras import ERAS
from .cities import CITIES, SOVEREIGNS
from .techs import TECHS
from .borrowers import BORROWERS, CAPITAL_REGIMES
from .events import EVENTS
from .rivals import RIVALS

__all__ = ["ERAS", "CITIES", "SOVEREIGNS", "TECHS", "BORROWERS", "CAPITAL_REGIMES", "EVENTS", "RIVALS"]
