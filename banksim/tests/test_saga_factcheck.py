"""
The fact-check tool's offline parts: reading a verdict out of a reply, the
budget ceiling, and finding the records to check. No API calls are made.
"""

import subprocess
import types
import unittest

from banksim.saga.tools import factcheck as fc


class ExtractTests(unittest.TestCase):
    def test_fenced_block(self):
        text = 'Looked it up.\n```json\n{"verdict": "confirmed", "issues": []}\n```'
        self.assertEqual(fc.extract_json(text)["verdict"], "confirmed")

    def test_last_fenced_block_wins(self):
        text = '```json\n{"verdict": "incorrect"}\n```\nOn reflection:\n```json\n{"verdict": "confirmed"}\n```'
        self.assertEqual(fc.extract_json(text)["verdict"], "confirmed")

    def test_bare_object(self):
        self.assertEqual(fc.extract_json('Verdict follows {"verdict": "minor_issues", "issues": [{"a": 1}]}')["verdict"],
                         "minor_issues")

    def test_no_verdict(self):
        self.assertIsNone(fc.extract_json("I could not decide."))
        self.assertIsNone(fc.extract_json('{"something": "else"}'))


class BudgetTests(unittest.TestCase):
    def test_never_reserves_past_the_ceiling(self):
        b = fc.Budget(1.0, 0.0)
        held = [b.reserve() for _ in range(3)]
        self.assertEqual(held[:1], [0.60])
        self.assertIsNone(held[1])  # 0.60 + 0.60 > 1.00
        b.settle(held[0], 0.30)
        self.assertAlmostEqual(b.spent, 0.30)
        self.assertEqual(b.worst, 0.60)
        b2 = b.reserve()
        self.assertIsNotNone(b2)  # 0.30 + 0.60 <= 1.00
        b.settle(b2, 0.65)
        self.assertAlmostEqual(b.worst, 0.65)  # the reserve grows with the dearest record
        self.assertIsNone(b.reserve())

    def test_unknown_model_priced_at_the_dearest_rate(self):
        usage = types.SimpleNamespace(input_tokens=1_000_000, output_tokens=0, cache_creation_input_tokens=0,
                                      cache_read_input_tokens=0, server_tool_use=types.SimpleNamespace(web_search_requests=3))
        known = fc.cost_of(types.SimpleNamespace(usage=usage, model="claude-opus-5-5"))
        unknown = fc.cost_of(types.SimpleNamespace(usage=usage, model="some-future-model"))
        self.assertAlmostEqual(known, 4.00 + 0.03)
        self.assertGreaterEqual(unknown, known)


class RecordTests(unittest.TestCase):
    def test_records_from_this_checkout(self):
        recs = fc.records("HEAD")
        kinds = {r["kind"] for r in recs}
        self.assertTrue({"event", "rival", "innovation", "city", "era"} <= kinds)
        self.assertEqual(len({r["id"] for r in recs}), len(recs))
        # mechanics are never sent for checking
        for r in recs:
            self.assertNotIn("effect", r["record"])
            self.assertNotIn("size", r["record"])

    def test_deck_cards_when_the_ref_has_them(self):
        ref = fc.DEFAULT_REF
        if subprocess.run(["git", "-C", str(fc.ROOT), "rev-parse", "--verify", "-q", ref],
                          capture_output=True).returncode != 0:
            self.skipTest(f"{ref} not fetched")
        recs = fc.records(ref)
        self.assertGreater(sum(r["kind"] == "deck card" for r in recs), 200)
        self.assertEqual(recs[0]["kind"], "event")
        self.assertEqual(recs[-1]["kind"], "deck card")


if __name__ == "__main__":
    unittest.main()
