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
| `build_dashboard.py` | Renders `data/determinations.csv` into a self-contained static `dashboard.html` (Plotly.js via CDN) |
| `dashboard.py` | Interactive Streamlit dashboard over the same data |
| `setup.sh` / `run_dashboard.sh` | venv setup and one-command refresh+build |
| `data/determinations.csv` / `.json` | Scraper output |

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
