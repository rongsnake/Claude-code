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

python cds_dc_scraper.py           # live refresh -> data/determinations.csv
python build_dashboard.py          # -> dashboard.html  (upload this to gcburton.org)

# or, interactive:
streamlit run dashboard.py
```

## Files

| File | Purpose |
|---|---|
| `cds_dc_scraper.py` | Scrapes the DC site (WordPress REST API → sitemap → optional PDF parsing), normalises to a tidy table |
| `analytics.py` | Derives columns (days-to-auction, is-restructuring, …) and computes the metrics that answer the common questions |
| `build_dashboard.py` | Renders a self-contained static `dashboard.html` (Plotly.js via CDN) with charts, an "ask the data" pivot, and downloads |
| `dashboard.py` | Interactive Streamlit dashboard incl. a DuckDB SQL "ask the data" box |
| `setup.sh` / `run_dashboard.sh` | venv setup and one-command refresh+build |
| `data/determinations.csv` / `.json` | Raw scraper output |
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
