# Risk Books archive — map + fetcher

Source: `RiskBooks-full-book-list_2.xlsx` (107 subscriber titles on risk.net).

- `RiskBooks_mapped.csv` / `RiskBooks_mapped.xlsx` — every title mapped to a
  theme and a priority tier. Tier 1 (16 titles) = the CDS / credit-risk-transfer /
  regulatory-capital beat; Tier 2 (31) = supporting (stress testing, IFRS 9/CECL,
  ALM, model risk, systemic); Tier 3 (60) = peripheral (op risk, insurance,
  energy, ESG, tech, buy-side). Tiering is editorial — edit column A and rerun.
- `fetch_riskbooks.py` — run **locally** (laptop or Pi, on the home LAN):
  downloads entitled PDFs with your risk.net browser cookies, files them on the
  PiNAS (`192.168.50.185` mount) by tier/theme/title, writes `manifest.csv`,
  optionally syncs to Google Drive via rclone. See the script docstring.

Why local: risk.net is subscriber-gated (needs your session) and both risk.net
and the LAN NAS are unreachable from the cloud session that built this.

Quick start on the Pi:
```bash
pip install requests beautifulsoup4
# export cookies.txt from your logged-in browser into this folder
python3 fetch_riskbooks.py --tier 1 --dry-run          # sanity check
python3 fetch_riskbooks.py --tier 1 --dest /mnt/pinas/RiskBooks --drive gdrive:RiskBooks
```
