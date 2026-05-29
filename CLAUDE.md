# CLAUDE.md — project context (loaded every session)

**Project:** scraper + dashboards for the **Credit Derivatives Determinations
Committees** (CDS = credit default swaps; source
`https://www.cdsdeterminationscommittees.org/`). Not climate data.

**If you are picking this up on a new machine, read `HANDOFF.md` first.**

## Layout
- `cds_dc_scraper.py` — scrape DC site → `data/determinations.csv`/`.json`.
  Modes: live (default), `--pdf`, `--demo`, `--seed-only`.
- `analytics.py` — derived columns + metrics → `determinations_tidy.csv`,
  `determinations_analytics.json`.
- `build_dashboard.py` — static `dashboard.html` (deploy target: **gcburton.org**).
- `dashboard.py` — Streamlit app with a DuckDB "ask the data" SQL box.

## Conventions
- Determination schema: `date, committee, reference_entity, issue_number,
  credit_event_type, decision, doc_type, url, source, auction_date, auction_held`.
- Committees: Americas / EMEA / Asia ex-Japan / Japan / Australia-New Zealand / All DCs.
- Keep data **honest**: `source` ∈ {`rest-api`, `sitemap`, `reference`,
  `synthetic-demo`}; dashboards must banner demo/seed vs live. Never present
  synthetic rows as real determinations.

## Known constraints
- The DC site blocks bots (403) and some networks; the live refresh needs a
  permitted network. Without it the scraper falls back to verified seed refs.
- Deploy to gcburton.org happens from the user's own host (no creds in CI/cloud).

## Workflow
- Branch: `claude/setup-cds-scraper-dashboard-i0TxS`; PR **#1**.
- After changes: `python analytics.py && python build_dashboard.py`, then commit.
