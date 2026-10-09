"""Sound and art: self-contained, never touching the game's dice, and honest about the tunes."""

import re
import unittest
from pathlib import Path

from banksim.saga import eras

SAGA = Path(__file__).resolve().parents[1] / "saga"
FILES = ("music.js", "art.js", "ambience.js")


class SoundAndArt(unittest.TestCase):
    def read(self, name):
        return (SAGA / name).read_text(encoding="utf-8")

    def test_files_are_self_contained(self):
        for name in FILES:
            js = self.read(name)
            self.assertNotIn("</script", js.lower(), name)
            self.assertIsNone(re.search(r"https?://(?!www\.w3\.org)", js), name + " must not load anything")

    def test_no_shared_randomness(self):
        # animation and audio use their own seeded generator, so they cannot change an outcome
        for name in FILES:
            code = re.sub(r"//[^\n]*|/\*.*?\*/", "", self.read(name), flags=re.S)
            self.assertNotIn("Math.random", code, name)
            self.assertNotIn("S.rng", code, name)

    def test_every_era_has_music_and_every_tune_is_accounted_for(self):
        js = self.read("music.js")
        head = js[: js.index("*/")]
        for e in eras.ERAS:
            self.assertIn(e["id"], js, e["id"])
            self.assertRegex(head, r"-\s*" + e["id"] + r":", "tune note missing for " + e["id"])
        for line in head.splitlines():
            if re.match(r"\s*\*\s+-\s+\w+:", line):
                self.assertRegex(line + head, r"public domain|original", line)

    def test_every_card_motif_is_redrawn(self):
        art = self.read("art.js")
        for key in ("crown", "ship", "plague", "fire", "war", "riot", "coin", "ledger", "bubble", "quake", "flood",
                    "letter", "scales", "cross", "seal", "train", "telegraph", "screen", "factory", "gold", "grain", "harbour"):
            self.assertRegex(art, r"\b" + key + r"\s*:", key)


if __name__ == "__main__":
    unittest.main()
