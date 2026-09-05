# CLAUDE.md — project context (loaded every session)

**Project:** scraper + dashboards for the **Credit Derivatives Determinations
Committees** (CDS = credit default swaps; source
`https://www.cdsdeterminationscommittees.org/`). Not climate data.

**If you are picking this up on a new machine, read `HANDOFF.md` first.**

## Layout
- `cds_dc_scraper.py` — scrape DC site → `data/determinations.csv`/`.json`.
  Modes: live (default), `--pdf`, `--demo`, `--seed-only`.
- `creditex_scraper.py` — scrape Creditex/creditfixings.com auctions
  (`results.jsp?ticker=…`) → `data/auctions.csv`. Same modes.
- `reconcile.py` — join auctions↔determinations → `data/reconciled.csv`
  (`match_status`: matched / determination_only / auction_only).
- `analytics.py` — derived columns + metrics over the reconciled table →
  `determinations_tidy.csv`, `determinations_analytics.json`.
- `build_dashboard.py` — static `dashboard.html` (deploy target: **gcburton.org**).
  Now a filterable app: committee/event/year/entity/notable dropdowns, a wide
  sortable determinations table, per-row **document drawers** (decisions, explanatory
  statements, pro-forma ASTs, final lists…), a free-text **Ask** box, and an **Update**
  button. The Ask box + Update call the local API; both degrade gracefully when it's off.
- `fetch_docs.py` — downloads source docs (ASTs, statements, decisions) → `data/docs/`,
  extracts text → `data/doctext/`, writes the `data/documents.csv` provenance manifest.
- `build_index.py` — offline builder → `data/index/`: `determinations_clean.csv`,
  `documents.json` (doc_kind, entity, meeting date, vote, qualitative flags, snippet),
  `chunks.json` + `embeddings.npy` (RAG via local Ollama `nomic-embed-text`). Prefers
  `data/documents.csv` when present, else scans `data/docs`+`data/doctext` locally.
- `cds_api.py` — FastAPI (uvicorn :5055) behind Caddy at **/cds/api/**. `POST /ask`
  streams a local-LLM RAG answer (`llama3.2:1b`, override `CDS_LLM_MODEL`) + citations;
  `POST /refresh` runs the pipeline async (locked, rate-limited); `GET /status`;
  `POST /reload` re-reads the index. Run via the `cds-api.service` user unit.
- `dashboard.py` — Streamlit app with a DuckDB "ask the data" SQL box.
- `energy/` + `public/energy/index.html` — **Auto Smart Mode** for the energy page (the Alstin Lodge
  dashboard, energy.gcburton.org = `webapp.py` on the Pi :5077; source on the Mac at
  `~/Claude/Projects/alstin-lodge-energy/`, not in git). Drop-in via `energy/install_smart_mode.sh`: overnight
  Tesla charging engine for the Octopus Go off-peak window (00:30–05:30). `auto_smart_mode.py
  --daemon` plans + drives the car (teslapy or dry-run), `energy_api.py` (uvicorn :5056,
  Caddy `/energy/api/`) serves the page's toggle/settings/boost. See `energy/README.md`.

## Serving / scheduling (this Pi)
- `/cds/` = static `index.html` behind Caddy basic_auth (user `gareth`); `/cds/api/*`
  reverse-proxied to `localhost:5055` (same gate, `flush_interval -1` for streaming).
- systemd **user** units: `cds-api.service` (the API) + `cds-refresh.timer`
  (Mon 06:00) → `cds-refresh.service` (= `cds_refresh.sh`). Linger is enabled.
- The embedding reindex is heavy on a Pi (~8.8k chunks ≈ 70 min) — it runs weekly or
  on demand via the dashboard's Update button, never per query.

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

## Auctions & reconciliation
- Auction schema: `reference_entity, auction_date, currency, final_price,
  initial_market_midpoint, net_open_interest_amount/direction, transaction_type,
  ticker, url, source`. `final_price` = recovery / cash-settlement price.
- Reconcile by normalised entity name + date window (auction on/after the DC
  determination). Dashboards/analytics prefer `reconciled.csv` when present.

## Workflow
- Branch: `claude/setup-cds-scraper-dashboard-i0TxS`; PR **#1**.
- Pipeline: `cds_dc_scraper.py` → `creditex_scraper.py` → `reconcile.py` →
  `analytics.py` → `build_dashboard.py` (or just `bash run_dashboard.sh`).
- After changes regenerate artifacts, then commit.
