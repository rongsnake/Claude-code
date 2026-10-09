"""The era decks and the council: well formed, in their eras, and honest."""

import unittest

from banksim.saga import cities, deck, eras, events


ERAS = {e["id"]: e for e in eras.ERAS}
CITIES = {c["id"] for c in cities.CITIES}


class DeckShape(unittest.TestCase):
    def test_every_era_has_a_deck(self):
        have = {c["era"] for c in deck.CARDS}
        self.assertEqual(have, set(ERAS), "every era needs its deck")

    def test_decks_are_a_fair_size_with_dilemmas_and_good_news(self):
        for era in ERAS:
            cs = [c for c in deck.CARDS if c["era"] == era]
            self.assertGreaterEqual(len(cs), 20, era)
            self.assertGreaterEqual(sum(1 for c in cs if c.get("choice")), 3, era + ": dilemmas")
            good = [c for c in cs if any(f["type"] in ("windfall", "deposits") and (f.get("share") or 0) > 0
                                         for f in c["effects"])]
            self.assertGreaterEqual(len(good), 2, era + ": some good news")

    def test_unique_ids(self):
        ids = [c["id"] for c in deck.CARDS]
        self.assertEqual(len(ids), len(set(ids)))


class CardFields(unittest.TestCase):
    def test_targets_signals_art(self):
        for c in deck.CARDS:
            self.assertIn(c["target"], deck.TARGETS, c["id"])
            if c["target"] == "cities":
                self.assertTrue(c.get("cities"), c["id"])
                for x in c["cities"]:
                    self.assertIn(x, CITIES, c["id"])
            for o in c["odds"]:
                self.assertIn(o["signal"], deck.SIGNALS, c["id"])
                self.assertTrue(0 < o["weight"] <= 8, c["id"])
            self.assertIn(c["art"], deck.ART, c["id"])

    def test_effects_are_ones_the_engine_knows(self):
        def check(cid, f):
            self.assertIn(f["type"], deck.EFFECTS, cid)
            extra = set(f) - {"type"} - deck.EFFECTS[f["type"]]
            self.assertFalse(extra, f"{cid}: unknown params {extra}")
            if f["type"] == "shock":
                self.assertIn(f["kind"], deck.SHOCK_KINDS, cid)
                self.assertTrue(0 < f["size"] <= 0.5, cid)
            if f["type"] == "sovereign_default":
                self.assertTrue(0 < f["haircut"] <= 0.95, cid)
            if f["type"] == "panic":
                self.assertTrue(0 < f["size"] <= 0.5, cid)
            if f["type"] == "standing":
                self.assertIn(f["who"], ("crown", "merchants", "regulator"), cid)
        for c in deck.CARDS:
            for f in c["effects"]:
                check(c["id"], f)
            for o in c.get("choice") or []:
                self.assertTrue(o.get("label"), c["id"])
                for f in o["effects"]:
                    check(c["id"], f)

    def test_hazards_and_windows(self):
        for c in deck.CARDS:
            self.assertTrue(0 < c["hazard"] <= 0.1, c["id"])
            e = ERAS[c["era"]]
            if c.get("window"):
                a, b = c["window"]
                self.assertTrue(e["start"] <= a < b <= e["end"], f"{c['id']}: window {c['window']} outside {e['id']}")
            if not c["once"]:
                self.assertGreaterEqual(c["cooldown"], 0, c["id"])

    def test_catastrophes_are_rare(self):
        for c in deck.CARDS:
            for f in c["effects"]:
                big = (f["type"] == "sovereign_default" and f["haircut"] > 0.7) or \
                      (f["type"] == "shock" and f["size"] > 0.35) or (f["type"] == "panic" and f["size"] > 0.3)
                if big:
                    self.assertLessEqual(c["hazard"], 0.015, c["id"])

    def test_every_card_remembers_its_history(self):
        for c in deck.CARDS:
            self.assertTrue(c.get("precedent"), c["id"])
            self.assertTrue(c.get("source"), c["id"])
            self.assertEqual(c.get("provenance"), "ARCHETYPE", c["id"])

    def test_the_council_advises_on_every_card(self):
        for c in deck.CARDS:
            for s in deck.SEATS:
                self.assertTrue((c.get("advice") or {}).get(s), f"{c['id']}: {s}")

    def test_rumours_have_text_and_a_false_rate(self):
        for c in deck.CARDS:
            r = c.get("rumour")
            if r:
                self.assertTrue(r.get("text"), c["id"])
                self.assertTrue(0 <= r.get("false_rate", 0.3) <= 0.6, c["id"])


class FixedEvents(unittest.TestCase):
    def test_anchors_exist_and_are_shocks(self):
        ids = {e["id"]: e for e in events.EVENTS}
        for a in deck.ANCHORS:
            self.assertIn(a, ids)
            self.assertEqual(ids[a]["effect"]["type"], "shock", a)

    def test_structural_events_stay_fixed(self):
        # what changes the rules of the game is never left to the deck
        for e in events.EVENTS:
            if e["effect"]["type"] in ("rule", "regime", "centre", "city", "tech_gate", "gsib_on", "lifeboat"):
                self.assertNotIn(e["effect"]["type"], deck.DECKABLE, e["id"])


class Council(unittest.TestCase):
    def test_four_seats_every_era(self):
        for era in ERAS:
            self.assertIn(era, deck.COUNCIL)
            for s in deck.SEATS:
                p = deck.COUNCIL[era][s]
                self.assertTrue(p.get("name") and p.get("title"), f"{era}/{s}")
                self.assertIn("portrait", p, f"{era}/{s}")

    def test_remarks_cover_the_situations(self):
        for era in ERAS:
            for s in deck.SEATS:
                rem = deck.COUNCIL[era][s].get("remarks") or {}
                self.assertIn("quiet", rem, f"{era}/{s}")
                self.assertGreaterEqual(len([k for k in deck.REMARK_KEYS if rem.get(k)]), 8, f"{era}/{s}")


if __name__ == "__main__":
    unittest.main()
