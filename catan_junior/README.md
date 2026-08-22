# Coco's Rulebook — Catan Junior rules bot

A single self-contained HTML page that answers Catan Junior rules questions at
the table. No build step, no network calls, no API key: open `rules_bot.html`
in a browser, or publish it as an Artifact.

Unrelated to the CDS determinations pipeline in the repo root — it just lives
here for version control.

## How it works

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

## Honesty about sources

Every answer carries a confidence tag:

| Tag | Meaning |
| --- | --- |
| In the rulebook | Stated in the official CATAN Junior rules |
| Widely agreed | Follows from the rules; consistent across published summaries |
| Genuinely ambiguous | Sources conflict, or the rulebook is silent |

Three entries are deliberately marked ambiguous: player-to-player trading,
whether a Ghost Captain Coco tile also grants the 2 resource tiles, and what
to do when the stockpile empties.

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
