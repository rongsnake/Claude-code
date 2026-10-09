"""
Build the Long Ledger page.

Same pattern as the Kingsgate dashboard: the history lives in Python, is
validated by the tests, and is baked as JSON into a single self-contained HTML
file. The page's JavaScript plays the turns; the map board's script lives in
`board.js` and is spliced into the template at `/*__BOARD_JS__*/`. No server, no build step beyond
this script, deploys by copying one file.

    python -m banksim.saga.build
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import borrowers, cities, deck, eras, events, geo, rivals, techs

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "saga_template.html"
#: the map board's script, spliced into the template's script block
BOARD_JS = HERE / "board.js"
#: the era decks, rumours, council, cards and the drawn seat, spliced after the board
DECK_JS = HERE / "deck.js"
OUT_HTML = HERE.parent / "saga.html"
OUT_FRAGMENT = HERE.parent / "saga_artifact.html"
OUT_JSON = HERE.parent / "data" / "saga.json"

STANDALONE_HEAD = (
    "<!doctype html>\n<html lang=\"en\">\n<head>\n"
    "<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,"
    "viewport-fit=cover\">\n</head>\n<body>\n"
)
STANDALONE_TAIL = "\n</body>\n</html>\n"


def data() -> dict:
    return {
        "built": date.today().isoformat(),
        "eras": eras.ERAS,
        "cities": cities.CITIES,
        "sovereigns": cities.SOVEREIGNS,
        "pool": cities.DEPOSIT_POOL,
        "max_pool_share": cities.MAX_POOL_SHARE,
        "lending_market": cities.LENDING_MARKET,
        "techs": techs.TECHS,
        "borrowers": borrowers.BORROWERS,
        "funding": borrowers.FUNDING,
        "regimes": borrowers.CAPITAL_REGIMES,
        "gsib": borrowers.GSIB,
        # fixed: kept on its date in "As it might have been" (structural, or an epoch anchor)
        "events": [dict(e, fixed=(e["effect"]["type"] not in deck.DECKABLE or e["id"] in deck.ANCHORS))
                   for e in sorted(events.EVENTS, key=lambda e: e["year"])],
        "deck": deck.CARDS,
        "council": deck.COUNCIL,
        "rivals": rivals.RIVALS,
        "acquisition": rivals.ACQUISITION,
        "branch_weight": rivals.BRANCH_WEIGHT,
        "court_contest": rivals.COURT_CONTEST,
        "turns": eras.total_turns(),
        "geo": geo.payload(),
    }


def build() -> dict:
    payload = data()
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # keep the JSON safe inside a <script> block
    blob = blob.replace("</", "<\\/")
    template = TEMPLATE.read_text(encoding="utf-8")
    board = BOARD_JS.read_text(encoding="utf-8")
    deckjs = DECK_JS.read_text(encoding="utf-8")
    for name, js in (("board.js", board), ("deck.js", deckjs)):
        if "</script" in js.lower():
            raise ValueError(name + " must not contain a closing script tag")
    fragment = (template
                .replace("/*__BOARD_JS__*/", board, 1)
                .replace("/*__DECK_JS__*/", deckjs, 1)
                .replace("/*__SAGA_DATA__*/null", blob, 1))
    OUT_FRAGMENT.write_text(fragment, encoding="utf-8")
    OUT_HTML.write_text(STANDALONE_HEAD + fragment + STANDALONE_TAIL, encoding="utf-8")
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


if __name__ == "__main__":
    p = build()
    print(f"wrote {OUT_HTML.relative_to(HERE.parent.parent)} — {p['turns']} turns, "
          f"{len(p['events'])} events, {len(p['techs'])} innovations, {len(p['cities'])} cities, {len(p['rivals'])} rival houses")
