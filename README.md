# CDS Determinations Committees — scraper & dashboard

Scrapes determinations published by the **Credit Derivatives Determinations
Committees** (CDS / credit-default-swap credit-event decisions) from
[cdsdeterminationscommittees.org](https://www.cdsdeterminationscommittees.org/)
and renders them as a dashboard — both a static `dashboard.html` (deployable to
a plain web host such as **gcburton.org**) and an interactive Streamlit app.

## Quick start

```bash
bash setup.sh                      # create .venv + install deps
source .venv/bin/activate

python cds_dc_scraper.py           # DC determinations  -> data/determinations.csv
python creditex_scraper.py         # Creditex auctions  -> data/auctions.csv
python reconcile.py                # join the two       -> data/reconciled.csv
python analytics.py                # metrics + tidy export
python build_dashboard.py          # -> dashboard.html  (upload this to gcburton.org)

# …or do all of that + launch Streamlit in one go:
bash run_dashboard.sh              # add --demo for synthetic data, --static for html only
```

## Files

| File | Purpose |
|---|---|
| `cds_dc_scraper.py` | Scrapes the DC site (WordPress REST API → sitemap → optional PDF parsing), normalises to a tidy table |
| `creditex_scraper.py` | Scrapes Creditex/Markit auction results from creditfixings.com (`results.jsp?ticker=…`): final price, initial market midpoint, net open interest |
| `reconcile.py` | Joins auctions to determinations by normalised entity + date window → `data/reconciled.csv` (`match_status`: matched / determination_only / auction_only) |
| `analytics.py` | Derives columns (days-to-auction, recovery, is-restructuring, …) and computes the metrics that answer the common questions |
| `build_dashboard.py` | Renders a self-contained static `dashboard.html` (Plotly.js via CDN) with charts, an "ask the data" pivot, filters, document drawers, and downloads |
| `fetch_docs.py` | Downloads source docs (ASTs, statements, decisions) → `data/docs/`, extracts text → `data/doctext/`, writes the `data/documents.csv` manifest |
| `build_index.py` | Offline builder → `data/index/`: cleaned determinations, a `documents.json` manifest (doc kind, vote, qualitative flags), and RAG `chunks.json` + `embeddings.npy` (local Ollama embeddings) |
| `cds_api.py` | FastAPI (uvicorn :5055, behind Caddy `/cds/api/`): streams local-LLM RAG answers + citations, plus `/refresh`, `/status`, `/reload`. No external API cost |
| `credit_events.py` / `summaries.py` | Build the curated credit-events table/exports and per-event commentary used by the dashboard |
| `dashboard.py` | Interactive Streamlit dashboard incl. a DuckDB SQL "ask the data" box |
| `setup.sh` / `run_dashboard.sh` | venv setup and one-command refresh+build |
| `data/determinations.csv` / `.json` | Raw DC scraper output |
| `data/auctions.csv` / `.json` | Raw Creditex auction output |
| `data/reconciled.csv` / `.json` | Determinations joined to auctions (the dashboards' primary input) |
| `data/determinations_tidy.csv` | Derived/analysis-ready table (for your own graphs) |
| `data/determinations_analytics.json` | Pre-computed metrics |

## Scraper modes

```bash
python cds_dc_scraper.py            # live scrape (+ folds in verified references)
python cds_dc_scraper.py --pdf      # also download & parse decision PDFs
python cds_dc_scraper.py --demo     # synthetic, clearly-labelled demo data
python cds_dc_scraper.py --seed-only # only the verified reference determinations
```

Each determination is normalised to:
`date, committee (Americas/EMEA/Asia ex-Japan/Japan/Australia-NZ),
reference_entity, issue_number, credit_event_type, decision, doc_type, url, source`.

## Creditex auctions & reconciliation

The DC **declares** a credit event; **Creditex + S&P Global** (formerly Markit)
then run the **settlement auction** that fixes the final price (recovery),
published at [creditfixings.com](https://www.creditfixings.com/). `reconcile.py`
links each auction to its determination by normalised reference-entity name
within a date window, so the dataset carries — per credit event — both the DC
decision and the auction outcome (`final_price`, `initial_market_midpoint`,
`net_open_interest_*`, `auction_date`, `currency`, `ticker`). Rows are tagged
`matched`, `determination_only`, or `auction_only`. This unlocks
*days-to-auction* and *recovery* analysis (e.g. avg final price by credit-event
type).

## Ask the data / analytics

Both dashboards answer questions like *"average days to auction"* or *"what % of
credit events are Restructuring"*:

- **Static `dashboard.html`** — headline answers + an interactive **group-by pivot**
  (group by region / credit-event type / year / decision × measure count / % /
  avg days-to-auction / credit-event rate), computed client-side. No server.
- **Streamlit `dashboard.py`** — the same headline answers plus a **DuckDB SQL box**:
  query the `determinations` table directly, e.g.

  ```sql
  SELECT credit_event_type, count(*) n,
         round(100.0*count(*)/sum(count(*)) over (),1) pct
  FROM determinations WHERE credit_event_type IS NOT NULL
  GROUP BY credit_event_type ORDER BY n DESC;
  ```

### Downloadable data (for your own graphs)

| File / button | Contents |
|---|---|
| `determinations.csv` | raw scraped rows |
| `determinations_tidy.csv` | derived columns: `year, month, days_to_auction, is_restructuring, credit_event_occurred, …` |
| `determinations_analytics.json` | pre-computed metrics |

All three are downloadable from both dashboards, or regenerated with
`python analytics.py`.

## ⚠️ Network note (important)

The DC site is behind bot protection and only serves clients on permitted
networks. The **live refresh therefore only works when run from a host that can
reach the site** (e.g. your own machine or the gcburton.org server) — it will
**not** work from a restricted/sandboxed environment, where it instead falls
back to a small set of verified seed references and tells you no live data was
pulled. The dashboard shows a banner indicating whether it is displaying live,
seed, or demo data.

## Deploying to gcburton.org (login-gated, via Caddy)

> **Reverse proxy:** gcburton.org is served by **Caddy**, not nginx. The whole
> site (including `/cds/`) sits behind Caddy `basic_auth`, so the static
> dashboard needs no auth of its own — deployment is just copying the built file
> into the already-gated Caddy docroot. (The older `deploy_gcburton_gated.sh`
> assumes nginx and is **not** used on this host; see its header note.)

`dashboard.html` is fully self-contained (data embedded, Plotly.js from CDN), so
deployment is just copying one file into the Caddy webroot under `/cds/`:

```bash
python build_dashboard.py --output public/index.html
# publish into the Caddy-gated docroot (this is exactly what deploy.sh does):
install -d /home/test/www/gcburton.org/cds
install -m 644 public/index.html /home/test/www/gcburton.org/cds/index.html
# served (after login) at https://gcburton.org/cds/
```

On the Pi, the weekly refresh runs `./deploy.sh` automatically, which copies
`public/index.html` (plus the Credit Events CSV/XLSX and a symlink to
`data/docs/`) into `/home/test/www/gcburton.org/cds/`. The local Q&A API
(`cds_api.py`, uvicorn :5055) is reverse-proxied by Caddy at `/cds/api/*` behind
the same gate.

## Hands-off autopilot (set up once, never touch again)

The live loop runs entirely on the Pi (which can reach the bot-protected sites)
and publishes into the Caddy-gated docroot — no third-party hosting involved:

```
Pi systemd timer (weekly)
  → git pull → live scrape → reconcile → analytics → fetch_docs → build_index
      → build dashboard → ./deploy.sh → copy into Caddy docroot (/cds/)
      → (optional) git commit/push
```

**One-time, on the Pi:**

```bash
cd /home/test/cds-dashboard           # the working copy on the Pi
bash pi_autopilot.sh                  # installs venv + a weekly systemd timer (uses sudo)
```

That's it — the Pi now refreshes on its own (`--daily` or `--on-calendar "…"` to
change the schedule). Useful commands it prints:
`sudo systemctl start cds-refresh.service` (run now),
`journalctl -u cds-refresh.service -n 50` (logs),
`systemctl list-timers cds-refresh.timer` (next run).

Publishing happens via `./deploy.sh`, which the refresh script invokes after each
build — it copies `public/index.html` into `/home/test/www/gcburton.org/cds/`,
where Caddy already serves it behind the site-wide `basic_auth` gate.

**Optional — GitHub Pages mirror.** `.github/workflows/refresh-dashboard.yml`
can also publish `public/index.html` to GitHub Pages on push (repo
**Settings → Pages → Source: "GitHub Actions"**). This is a *public* mirror and
is **not** the gated gcburton.org deployment; do not point the gcburton.org DNS
at a Pages site if you want the dashboard to stay behind the login. Hosted
runners are 403'd by the source sites, so a Pages build only rebuilds from
already-committed data — the Pi is what pulls fresh data.

**Deploy somewhere else too?** Copy `deploy.sh.example` → `deploy.sh` and edit
the target (local copy / rsync / Netlify). Note that on this host `deploy.sh`
already exists and copies into the Caddy docroot, so it is **gitignored** to
avoid clobbering the live one.
