"""
The Long Ledger's history is data; these tests keep it consistent.

They check the things a broken page would not tell you: that eras tile the
timeline, that every event lands in a playable year and refers to things that
exist, that the tech tree is acyclic and never requires something invented
later, that every borrower class has numbers for every era it is live in, and
that provenance is declared everywhere.
"""

import unittest

from banksim.saga import ERAS, CITIES, SOVEREIGNS, TECHS, BORROWERS, CAPITAL_REGIMES, EVENTS
from banksim.saga.borrowers import FUNDING, GSIB
from banksim.saga.eras import era_for_year, total_turns
from banksim.saga.techs import tech_by_id
from banksim.saga.rivals import RIVALS, ACQUISITION, BRANCH_WEIGHT, COURT_CONTEST

ERA_IDS = [e["id"] for e in ERAS]
CITY_IDS = {c["id"] for c in CITIES}
TECH_IDS = {t["id"] for t in TECHS}
CLASS_IDS = {b["id"] for b in BORROWERS}
EFFECT_TYPES = {
    "sovereign_default", "forced_loan", "shock", "panic", "rule", "centre", "city",
    "regime", "tech_gate", "offer", "flavour", "lifeboat", "gsib_on", "fraud_check",
}


class EraTests(unittest.TestCase):
    def test_eras_tile_the_timeline(self):
        self.assertEqual(ERAS[0]["start"], 1300)
        self.assertEqual(ERAS[-1]["end"], 2027)
        for a, b in zip(ERAS, ERAS[1:]):
            self.assertEqual(a["end"], b["start"], f"gap between {a['id']} and {b['id']}")

    def test_turn_lengths_divide_spans(self):
        for e in ERAS:
            self.assertEqual((e["end"] - e["start"]) % e["turn_years"], 0, e["id"])

    def test_turn_count_is_what_was_promised(self):
        # era-scaled turns, about 250 in all
        self.assertTrue(230 <= total_turns() <= 280, total_turns())

    def test_turns_get_shorter(self):
        lengths = [e["turn_years"] for e in ERAS]
        self.assertEqual(lengths, sorted(lengths, reverse=True))

    def test_every_era_has_rules_and_provenance(self):
        keys = {"usury", "liability", "joint_stock", "lolr", "deposit_insurance", "supervision",
                "reserve_floor", "capital_regime", "notes_allowed", "gold_standard", "own_account_trade"}
        for e in ERAS:
            self.assertTrue(keys <= set(e["rules"]), e["id"])
            self.assertIn(e["provenance"], ("HISTORICAL", "STYLISED"))
            self.assertTrue(e["source"])
            self.assertIn(e["centre"], CITY_IDS)

    def test_era_lookup(self):
        self.assertEqual(era_for_year(1300)["id"], "rialto")
        self.assertEqual(era_for_year(1499)["id"], "medici")
        self.assertEqual(era_for_year(1500)["id"], "princes")
        self.assertEqual(era_for_year(2026)["id"], "basel")


class CityTests(unittest.TestCase):
    def test_sovereigns_exist(self):
        for c in CITIES:
            self.assertIn(c["sovereign"], SOVEREIGNS, c["id"])

    def test_company_courts_only_act_while_chartered(self):
        # a court with a life span (Burgundy, the VOC, the EIC) can only ask for money,
        # default or hold a city inside it
        for sid, s in SOVEREIGNS.items():
            if "from" not in s and "until" not in s:
                continue
            start, end = s.get("from", 1300), s.get("until", 2028)
            self.assertLess(start, end, sid)
            for e in EVENTS:
                f = e["effect"]
                if f.get("sovereign") == sid and f["type"] in ("offer", "sovereign_default", "forced_loan"):
                    self.assertTrue(start <= e["year"] < end, e["id"])
            for c in CITIES:
                if c["sovereign"] != sid:
                    continue
                self.assertGreaterEqual(c["opens"], start, c["id"])
                if "until" in s:
                    # a court that ends must hand its cities to another before it does
                    handed = [e["year"] for e in EVENTS for g in (e["effect"], e["effect"].get("also") or {})
                              if g.get("type") == "city" and g.get("city") == c["id"] and g.get("field") == "sovereign"]
                    self.assertTrue(handed and min(handed) <= end, c["id"])

    def test_prosperity_in_range_and_keyed_by_era(self):
        for c in CITIES:
            for era_id, p in c["prosperity"].items():
                self.assertIn(era_id, ERA_IDS, c["id"])
                self.assertTrue(0.0 <= p <= 1.0, (c["id"], era_id, p))

    def test_opening_year_precedes_first_prosperity_era(self):
        for c in CITIES:
            first = min(ERAS[ERA_IDS.index(k)]["start"] for k in c["prosperity"])
            self.assertLess(c["opens"], ERAS[ERA_IDS.index(max(c["prosperity"], key=ERA_IDS.index))]["end"], c["id"])
            # a city must be openable before its first prosperous era ends
            first_era = min(c["prosperity"], key=ERA_IDS.index)
            self.assertLess(c["opens"], ERAS[ERA_IDS.index(first_era)]["end"], c["id"])

    def test_start_city_is_venice_and_open(self):
        v = next(c for c in CITIES if c["id"] == "venice")
        self.assertEqual(v["opens"], 1300)
        self.assertEqual(v["prosperity"]["rialto"], 1.0)

    def test_every_era_has_a_centre_with_full_prosperity(self):
        for e in ERAS:
            c = next(c for c in CITIES if c["id"] == e["centre"])
            self.assertGreaterEqual(c["prosperity"].get(e["id"], 0), 0.9, e["id"])


class TechTests(unittest.TestCase):
    def test_prerequisites_exist_and_are_older(self):
        for t in TECHS:
            for r in t["requires"]:
                self.assertIn(r, TECH_IDS, (t["id"], r))
                self.assertLessEqual(tech_by_id(r)["available"], t["available"], (t["id"], r))

    def test_acyclic(self):
        seen = set()

        def walk(tid, stack):
            self.assertNotIn(tid, stack, f"cycle through {tid}")
            for r in tech_by_id(tid)["requires"]:
                walk(r, stack + [tid])
            seen.add(tid)

        for t in TECHS:
            walk(t["id"], [])
        self.assertEqual(seen, TECH_IDS)

    def test_one_starting_tech(self):
        self.assertEqual([t["id"] for t in TECHS if t.get("starting")], ["giro"])

    def test_effects_reference_real_classes_and_funding(self):
        funding_ids = {f["id"] for f in FUNDING}
        for t in TECHS:
            e = t["effects"]
            if "unlock_class" in e:
                self.assertIn(e["unlock_class"], CLASS_IDS, t["id"])
            if "unlock_funding" in e:
                self.assertIn(e["unlock_funding"], funding_ids, t["id"])
            for k in ("liquidity", "yield", "loss"):
                for c in e.get(k, {}):
                    self.assertIn(c, CLASS_IDS, (t["id"], k, c))
            self.assertTrue(0.0 <= t["cost"] <= 0.3, t["id"])

    def test_dates_are_monotone_in_the_tree(self):
        self.assertEqual([t["available"] for t in TECHS], sorted(t["available"] for t in TECHS))

    def test_provenance_and_source(self):
        for t in TECHS:
            self.assertEqual(t["provenance"], "HISTORICAL", t["id"])
            self.assertTrue(t["source"], t["id"])


class BorrowerTests(unittest.TestCase):
    def test_numbers_for_every_live_era(self):
        for b in BORROWERS:
            for e in ERAS:
                live = b["from"] < e["end"] and (b.get("until", 9999) > e["start"])
                if live and b["id"] != "cash":
                    self.assertIn(e["id"], b["yield"], (b["id"], e["id"]))
                    self.assertIn(e["id"], b["loss"], (b["id"], e["id"]))

    def test_yield_exceeds_loss(self):
        for b in BORROWERS:
            if b["id"] == "cash":
                continue
            for era_id, y in b["yield"].items():
                self.assertGreater(y, b["loss"][era_id], (b["id"], era_id))

    def test_princes_pay_most_and_are_least_liquid(self):
        p = next(b for b in BORROWERS if b["id"] == "princes")
        for b in BORROWERS:
            if b["id"] in ("princes", "commodities", "trading_book"):
                continue
            for era_id, y in p["yield"].items():
                if era_id in b["yield"] and era_id in ("rialto", "medici", "princes"):
                    self.assertGreater(y, b["yield"][era_id], (b["id"], era_id))
        self.assertLessEqual(p["liquidity"], min(b["liquidity"] for b in BORROWERS if b["id"] != "princes"))

    def test_required_techs_exist(self):
        for b in BORROWERS:
            if "requires_tech" in b:
                self.assertIn(b["requires_tech"], TECH_IDS, b["id"])
                self.assertLessEqual(tech_by_id(b["requires_tech"])["available"], b["from"] + 1, b["id"])

    def test_capital_regimes_cover_every_class(self):
        for rid, reg in CAPITAL_REGIMES.items():
            for b in BORROWERS:
                if b["from"] <= 1988 and b.get("until", 9999) > 1988:
                    self.assertIn(b["id"], reg["rw"], (rid, b["id"]))
            self.assertEqual(reg["minimum"], 0.08, rid)
        self.assertEqual(CAPITAL_REGIMES["basel31"]["output_floor"], 0.725)
        self.assertIsNone(CAPITAL_REGIMES["basel1"]["output_floor"])

    def test_gsib_buckets_match_the_fsb_schedule(self):
        self.assertEqual([s for _, s in GSIB["buckets"]], [0.010, 0.015, 0.020, 0.025, 0.035])
        self.assertEqual(GSIB["designation_score"], 130)
        self.assertEqual(len(GSIB["categories"]), 5)


class EventTests(unittest.TestCase):
    def test_sorted_and_in_range(self):
        years = [e["year"] for e in EVENTS]
        self.assertEqual(years, sorted(years))
        for e in EVENTS:
            self.assertTrue(1300 <= e["year"] <= 2027, e["id"])

    def test_unique_ids(self):
        ids = [e["id"] for e in EVENTS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_effects_are_well_formed(self):
        for e in EVENTS:
            f = e["effect"]
            self.assertIn(f["type"], EFFECT_TYPES, e["id"])
            if f["type"] in ("sovereign_default", "forced_loan", "offer"):
                self.assertIn(f["sovereign"], SOVEREIGNS, e["id"])
            if f["type"] in ("centre", "city", "fraud_check"):
                self.assertIn(f["city"], CITY_IDS, e["id"])
            if f["type"] == "regime":
                self.assertIn(f["id"], CAPITAL_REGIMES, e["id"])
            if f["type"] == "tech_gate":
                self.assertIn(f["tech"], TECH_IDS, e["id"])
            if f["type"] == "sovereign_default":
                self.assertTrue(0 < f["haircut"] <= 1, e["id"])
            for c in f.get("cities", []) or []:
                self.assertIn(c, CITY_IDS, (e["id"], c))
            if "scope" in f:
                self.assertIn(f["scope"], SOVEREIGNS, e["id"])
            if f["type"] == "city" and f.get("field") == "sovereign":
                self.assertIn(f["value"], SOVEREIGNS, e["id"])
            if "also" in f:
                g = f["also"]
                self.assertIn(g["type"], EFFECT_TYPES, e["id"])
                if g["type"] == "city":
                    self.assertIn(g["city"], CITY_IDS, e["id"])
                    if g.get("field") == "sovereign":
                        self.assertIn(g["value"], SOVEREIGNS, e["id"])
            self.assertIn(e["provenance"], ("HISTORICAL", "STYLISED"), e["id"])
            self.assertTrue(e["text"], e["id"])

    def test_the_spine_of_the_story_is_present(self):
        ids = {e["id"] for e in EVENTS}
        for must in ("peruzzi", "bardi", "black_death", "nancy", "spain_1557", "spanish_fury",
                     "stop_exchequer", "bank_of_england", "south_sea", "ayr_bank", "panic_1825",
                     "peel", "overend_gurney", "city_of_glasgow", "baring_crisis", "crisis_1914",
                     "secondary_banking", "basel_1", "barings_1995", "gfc", "gsib_list", "basel_31"):
            self.assertIn(must, ids)

    def test_every_default_has_a_matching_offer_or_reachable_exposure(self):
        # a scripted default should be preceded by some way of being exposed to that sovereign
        offered = {}
        for e in EVENTS:
            f = e["effect"]
            if f["type"] in ("offer", "forced_loan"):
                offered.setdefault(f["sovereign"], e["year"])
        for e in EVENTS:
            f = e["effect"]
            if f["type"] == "sovereign_default":
                self.assertIn(f["sovereign"], offered, e["id"])
                self.assertLess(offered[f["sovereign"]], e["year"], e["id"])

    def test_lolr_arrives_in_1866_and_basel_in_1988(self):
        og = next(e for e in EVENTS if e["id"] == "overend_gurney")
        self.assertEqual((og["effect"]["field"], og["effect"]["value"]), ("lolr", True))
        b1 = next(e for e in EVENTS if e["id"] == "basel_1")
        self.assertEqual(b1["effect"], {"type": "regime", "id": "basel1"})

    def test_jurisdictional_rules_are_scoped(self):
        for eid in ("peel", "ring_fence", "venice_bans_trade", "provveditori", "banking_act"):
            e = next(e for e in EVENTS if e["id"] == eid)
            self.assertIn("scope", e["effect"], eid)


class RivalTests(unittest.TestCase):
    def test_homes_cities_and_techs_exist(self):
        for r in RIVALS:
            self.assertIn(r["home"], CITY_IDS, r["id"])
            self.assertIn(r["home"], r["cities"], r["id"])
            for c in r["cities"]:
                self.assertIn(c, CITY_IDS, (r["id"], c))
            for t in r["techs"]:
                self.assertIn(t, TECH_IDS, (r["id"], t))

    def test_sizes_are_shares_keyed_by_era(self):
        for r in RIVALS:
            self.assertTrue(r["size"], r["id"])
            for era_id, share in r["size"].items():
                self.assertIn(era_id, ERA_IDS, r["id"])
                self.assertTrue(0 < share <= 0.5, (r["id"], era_id, share))

    def test_fates_are_ordered_after_founding_and_well_formed(self):
        kinds = {"failed", "absorbed", "rescued", "gutted"}
        for r in RIVALS:
            years = [f["year"] for f in r["fates"]]
            self.assertEqual(years, sorted(years), r["id"])
            for f in r["fates"]:
                self.assertGreater(f["year"], r["founded"], r["id"])
                self.assertIn(f["kind"], kinds, r["id"])
                self.assertTrue(f["text"], r["id"])
                if f["kind"] in ("rescued", "gutted"):
                    self.assertTrue(0 < f.get("size_mult", 0.5) < 1, r["id"])
            terminal = [f for f in r["fates"] if f["kind"] in ("failed", "absorbed")]
            self.assertLessEqual(len(terminal), 1, r["id"])
            if terminal:
                self.assertEqual(terminal[0], r["fates"][-1], r["id"])

    def test_a_rival_is_alive_in_the_eras_it_has_a_size_for(self):
        for r in RIVALS:
            end = next((f["year"] for f in r["fates"] if f["kind"] in ("failed", "absorbed")), 9999)
            for era_id in r["size"]:
                e = ERAS[ERA_IDS.index(era_id)]
                self.assertLess(r["founded"], e["end"], (r["id"], era_id))
                self.assertGreater(end, e["start"], (r["id"], era_id))

    def test_the_famous_fall_on_the_right_dates(self):
        fell = {r["id"]: next((f["year"] for f in r["fates"] if f["kind"] == "failed"), None) for r in RIVALS}
        self.assertEqual(fell["peruzzi"], 1343)
        self.assertEqual(fell["bardi"], 1346)
        self.assertEqual(fell["medici"], 1494)
        self.assertEqual(fell["backwell"], 1672)
        self.assertEqual(fell["overend"], 1866)
        self.assertEqual(fell["glasgow"], 1878)
        self.assertEqual(fell["barings"], 1995)
        self.assertEqual(fell["lehman"], 2008)
        self.assertIsNone(fell["rothschild"])
        self.assertIsNone(fell["hoare"])

    def test_fates_coincide_with_scripted_events(self):
        event_years = {e["year"] for e in EVENTS}
        for rid, year in (("peruzzi", 1343), ("bardi", 1346), ("medici", 1494), ("lippomano", 1499),
                          ("fugger", 1557), ("pisani", 1584), ("backwell", 1672), ("overend", 1866),
                          ("glasgow", 1878), ("barings", 1890), ("bcci", 1991), ("barings", 1995), ("lehman", 2008)):
            r = next(r for r in RIVALS if r["id"] == rid)
            self.assertIn(year, [f["year"] for f in r["fates"]], rid)
            self.assertIn(year, event_years, (rid, year))

    def test_acquisition_terms(self):
        for mode, t in ACQUISITION.items():
            self.assertTrue(0 < t["price"] < 0.2, mode)
            self.assertTrue(0 < t["deposits_kept"] <= 1, mode)
            self.assertTrue(0 <= t["bad_book"] < 0.5, mode)
        self.assertGreater(ACQUISITION["rescued"]["price"], ACQUISITION["failed"]["price"])
        self.assertGreater(ACQUISITION["rescued"]["bad_book"], ACQUISITION["failed"]["bad_book"])
        self.assertTrue(0 < BRANCH_WEIGHT < 1 and 0 < COURT_CONTEST < 1)

    def test_provenance_and_source(self):
        for r in RIVALS:
            self.assertEqual(r["provenance"], "HISTORICAL", r["id"])
            self.assertTrue(r["source"], r["id"])


class BuildTests(unittest.TestCase):
    def test_build_produces_a_page(self):
        from banksim.saga.build import build, OUT_HTML, OUT_FRAGMENT
        payload = build()
        html = OUT_HTML.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", html)
        self.assertNotIn("/*__SAGA_DATA__*/null", html)
        self.assertIn('"designation_score":130', html)
        self.assertEqual(payload["turns"], total_turns())
        self.assertNotIn("<!doctype html>", OUT_FRAGMENT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
