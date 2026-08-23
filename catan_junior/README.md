# Coco's Rulebook — Catan Junior rules bot

A single self-contained HTML page that answers Catan Junior rules questions at
the table. No build step, no network calls, no API key: open `rules_bot.html`
in a browser, or publish it as an Artifact.

Unrelated to the CDS determinations pipeline in the repo root — it just lives
here for version control.

## Two ways in

**Ask** — a running thread. Type a question, get an answer card, keep going;
the last 20 exchanges persist in `localStorage`. Questions phrased as "was it
wrong to…" / "did we play this right?" are detected and answered as a
play-check rather than a definition, and a question spanning two rules gets a
card for each.

**Check a turn** — the interactive resolver, and the reason this isn't just a
lookup table. Pick what you rolled, tick which islands on *your* board show
that number, say who's playing and how many lairs each has touching each
island, and it works out exactly who takes what from the stockpile. It handles
Ghost Captain blocking, a roll of 6, multiple lairs on one island, and players
who earn nothing. It computes situations the knowledge base never enumerated.

**Reference** — build costs, turn order, Ghost Captain, victory condition.

## How the Ask engine works

`rules_bot.html` embeds a curated knowledge base of ~25 rules entries and a
small retrieval engine:

1. The query is normalised and tokenised.
2. Tokens are expanded through a synonym map to canonical terms, so "rum",
   "sword", "hideout", "robber" and "dev card" reach molasses, cutlass, lair,
   Ghost Captain and Coco tile respectively.
3. Entries are scored: 3 points per strong term, 1 per supporting term, 5 for
   an exact phrase hit.
4. Below a score of 3 the bot says it doesn't know and offers the closest
   topics rather than inventing a ruling.
5. A runner-up card is shown only when it scores >= 5 *and* >= 60% of the best
   — enough for genuinely two-part questions, not enough for incidental
   keyword overlap.

There is no LLM call: published Artifact pages have no such runtime capability
on this account, so the interactivity comes from retrieval plus the resolver.

## Honesty about sources

Every answer carries a confidence tag:

| Tag | Meaning |
| --- | --- |
| In the rulebook | Stated in the official CATAN Junior rules |
| Widely agreed | Follows from the rules; consistent across published summaries |
| Genuinely ambiguous | Sources conflict, or the rulebook is silent |

Four entries are deliberately marked ambiguous: player-to-player trading,
whether a Ghost Captain Coco tile also grants the 2 resource tiles, what to do
when the stockpile empties, and the board's island numbering — the official
rulebook host was unreachable, so the resolver asks you which islands show the
rolled number instead of asserting a layout.

## Editing the rules

The knowledge base is the `KB` array in the inline `<script>`. Each entry:

```js
{
  id:      "unique-slug",
  title:   "Headline answer",
  conf:    "official" | "clarified" | "open",
  strong:  ["canonical","terms","worth 3"],
  k:       ["supporting","terms","worth 1"],
  phrases: ["literal substrings worth 5"],
  body:    "<p>HTML answer</p>",
  src:     "Where this comes from"
}
```

Canonical terms must exist as keys in the `SYN` map. Keep `phrases` specific —
a phrase that is a substring of many questions ("ghost captain") will hijack
the ranking.
