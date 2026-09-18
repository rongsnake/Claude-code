# Risk Books archive — map, download plan + fetcher

Source: `RiskBooks-full-book-list_2.xlsx` (107 subscriber titles on risk.net).

## Two prudential regimes, filed separately

`RiskBooks_download_plan.csv` / `.xlsx` tag every title with a **regime** and,
for banking, a **wave**. Banking and insurance are different prudential
regimes, so they go to different folders.

### Banking model — 49 titles, in download waves
- **Wave 1 — 16.** Tier-1 core: capital, derivatives, credit derivatives,
  counterparty/collateral, credit modelling.
- **Wave 2 — 25.** All remaining credit + regulatory: FRTB, market risk,
  stress testing/CCAR, IFRS 9/CECL, model risk & validation, BCBS 239,
  systemic risk.
- **Wave 3 — 8.** Rest of the banking-model stack: ALM/IRRBB, liquidity,
  operational-risk capital models.

### Insurance / Solvency II — 8 titles (separate regime, separate folder)
Internal Models and Solvency II, The Solvency II Handbook, ORSA Design and
Implementation, Risk Management for Insurers, Life Annuities, Longevity Risk,
Non-traditional Life Insurance Products with Guarantees, Fundamentals of
Operational Risk for Insurers.

### Neither regime — 50 titles
Energy, buy-side portfolio, ESG, tech/AI, general op/conduct risk. Still
listed (regime `—`), just not scheduled.

Regimes and waves are editorial — re-sort columns A/B in the xlsx to change
them. `RiskBooks_mapped.*` are the earlier theme+tier view, kept for reference.

## Fetching (run locally — laptop or Pi, on the home LAN)

risk.net is subscriber-gated (needs your logged-in cookies) and the LAN NAS is
unreachable from the cloud session that built this, so the download runs where
the network and entitlement live.

```bash
pip install requests beautifulsoup4
# export cookies.txt from your logged-in browser into this folder
python3 fetch_riskbooks.py --wave 1 --dry-run                                       # sanity check
python3 fetch_riskbooks.py --wave 1      --dest /mnt/pinas/RiskBooks --drive gdrive:RiskBooks
python3 fetch_riskbooks.py --bank-model  --dest /mnt/pinas/RiskBooks --drive gdrive:RiskBooks
python3 fetch_riskbooks.py --regime insurance --dest /mnt/pinas/RiskBooks --drive gdrive:RiskBooks
```

Each regime lands in its own top-level folder under `<dest>` (and on Drive):
`Banking/Wave N - <Theme>/<Title>/` and `Insurance (Solvency II)/Wave 1 - <Theme>/<Title>/`,
with `manifest.csv` logging every fetch. Re-runs skip what's already there;
`--drive` rclone-syncs the regime folder to a matching Drive subfolder. If a
book page yields no PDF the manifest says so — layouts differ per title, so
check one such URL in the browser and adjust `PDF_LINK_HINTS` in the script.
