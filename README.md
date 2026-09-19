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
| `build_dashboard.py` | Renders a self-contained static `dashboard.html` (Plotly.js via CDN) with charts, an "ask the data" pivot, and downloads |
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

## Deploying to gcburton.org

`dashboard.html` is fully self-contained (data embedded, Plotly.js from CDN), so
deployment is just copying one file, e.g.:

```bash
python build_dashboard.py --output public/index.html
# then upload public/index.html via your normal gcburton.org deploy (scp/rsync/CI)
```

## Hands-off autopilot (set up once, never touch again)

The full loop links the Pi (which can reach the sites) to publishing:

```
Pi systemd timer (weekly)
  → git pull → live scrape → reconcile → analytics → build → git push
      → push triggers the GitHub Action → publishes to GitHub Pages
```

**One-time, on the Pi:**

```bash
git clone https://github.com/rongsnake/claude-code.git cds-dashboard
cd cds-dashboard && git checkout claude/setup-cds-scraper-dashboard-i0TxS
bash pi_autopilot.sh            # installs venv + a weekly systemd timer (uses sudo)
```

That's it — the Pi now refreshes and pushes on its own (`--daily` or
`--on-calendar "…"` to change the schedule). Useful commands it prints:
`sudo systemctl start cds-refresh.service` (run now),
`journalctl -u cds-refresh.service -n 50` (logs),
`systemctl list-timers cds-refresh.timer` (next run).

**One-time, on GitHub:** repo **Settings → Pages → Source: "GitHub Actions"**.
After that every push publishes `public/index.html` to a stable Pages URL — no
hosting credentials, no manual deploy. `.github/workflows/refresh-dashboard.yml`
handles it (and runs a weekly fallback rebuild; hosted runners are 403'd by the
sites, so the Pi is what pulls fresh data).

**Point gcburton.org at it (optional, one-time):** add a `CNAME` DNS record for
`gcburton.org` → `rongsnake.github.io`, then set the custom domain under
Settings → Pages. Until then the dashboard lives at the Pages URL.

**Deploy somewhere other than Pages?** Copy `deploy.sh.example` → `deploy.sh`,
fill in your one line (local copy / rsync / Netlify), `chmod +x deploy.sh`, and
the Pi's weekly refresh will publish there too.
