"""
The era decks: what an age could do to a house, without saying when.

Until October 2026 every event fired on its real date. Now only two kinds of
event keep a date:

* STRUCTURAL events change the rules of the game: a city opens or changes
  hands, the centre of money moves, a law or a capital regime comes in, a
  technology is gated, the Lifeboat sails. Those stay in `events.py`.
* ANCHORS: a handful of epoch-making shocks no player of the period could
  have escaped or delayed (below).

Everything else (a king's default, a run, a forced loan, a lost fleet, a
mania) is drawn from the era's DECK. A card is an archetype with no named
ruler; it carries a `precedent`, the real episode it echoes, which the game
prints as a footnote. Each card has a yearly hazard, optional odds that rise
with what the house is doing (lend a court too much and it is likelier to
default), an optional rumour posted a turn ahead (sometimes false), the
council's advice, and an art motif for its card.

`python -m banksim.saga.build` bakes the deck into the page. The historical
chronicle (every event on its date) remains a game mode: "As it happened".

Generated with Claude Opus from the era context and the historical events
it replaces, checked by a second review pass, then validated by
`tests/test_saga_deck.py`. Hazards and magnitudes are STYLISED; precedents
and sources are HISTORICAL.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECK_DIR = HERE / "deck"

#: effect types an event in events.py may have that the deck now covers
DECKABLE = {"offer", "sovereign_default", "panic", "forced_loan", "shock"}

#: epoch shocks that keep their date in every mode
ANCHORS = {"black_death", "constantinople", "south_sea", "crisis_1914", "crash_1929", "gfc"}

SIGNALS = {"sov_exposure", "city_heat", "leverage", "thin_till", "far_branches",
           "trading_book", "low_standing", "fame", "many_branches"}
TARGETS = {"lent_sovereign", "reachable_sovereign", "seat_sovereign", "branch_city", "seat", "cities", "none"}
EFFECTS = {
    "sovereign_default": {"haircut"},
    "offer": {"size", "yield", "turns"},
    "forced_loan": {"share", "yield"},
    "shock": {"kind", "size", "panic"},
    "panic": {"size"},
    "windfall": {"share"},
    "deposits": {"share"},
    "standing": {"who", "delta"},
    "commerce": {"delta"},
    "control": {"delta"},
    "flavour": set(),
}
SHOCK_KINDS = {"trade", "markets", "property", "plague", "sovereign"}
ART = {"crown", "ship", "plague", "fire", "war", "riot", "coin", "ledger", "bubble", "quake", "flood", "letter",
       "scales", "cross", "seal", "train", "telegraph", "screen", "factory", "gold", "grain", "harbour"}
SEATS = ("growth", "prudence", "court", "conscience")
REMARK_KEYS = ("thin_till", "flush_till", "high_leverage", "big_prince_exposure", "bubble_city", "far_branches",
               "loss_turn", "good_turn", "court_offer", "new_tech", "centre_moving", "quiet")


def _load(name):
    p = DECK_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _effect(f: dict) -> dict:
    """Accept {"type": t, ...params} or {"kind": t, "params": {...}}; return the flat form."""
    if "type" in f:
        return dict(f)
    out = {"type": f.get("kind")}
    out.update(f.get("params") or {})
    return out


def normalise(c: dict, era: str) -> dict:
    c = dict(c)
    c["era"] = era
    c["effects"] = [_effect(f) for f in (c.get("effects") or [])]
    if c.get("choice"):
        c["choice"] = [dict(o, effects=[_effect(f) for f in (o.get("effects") or [])]) for o in c["choice"]]
    c.setdefault("odds", [])
    c.setdefault("cooldown", 0)
    c.setdefault("once", False)
    return c


def cards() -> list[dict]:
    out = []
    for p in sorted(DECK_DIR.glob("deck-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        era = d.get("era") or p.stem.split("-", 1)[1]
        out.extend(normalise(c, era) for c in d["cards"])
    return out


def council() -> dict:
    return (_load("council.json") or {}).get("council", {})


CARDS = cards()
COUNCIL = council()
