#!/usr/bin/env bash
# Refresh data, build the static dashboard, and (optionally) launch Streamlit.
#
#   bash run_dashboard.sh            # live refresh -> dashboard.html + Streamlit
#   bash run_dashboard.sh --demo     # synthetic data -> dashboard.html + Streamlit
#   bash run_dashboard.sh --static   # just (re)build dashboard.html, no Streamlit

set -euo pipefail

VENV_DIR=".venv"
[ -d "${VENV_DIR}" ] && source "${VENV_DIR}/bin/activate"

SCRAPE_MODE=""
STATIC_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --demo)   SCRAPE_MODE="--demo" ;;
    --static) STATIC_ONLY=1 ;;
  esac
done

if [ ! -f "data/determinations.csv" ] || [ -n "${SCRAPE_MODE}" ]; then
  echo "==> Refreshing determinations data…"
  python cds_dc_scraper.py ${SCRAPE_MODE} || true
fi

echo "==> Building static dashboard (dashboard.html)…"
python build_dashboard.py

if [ "${STATIC_ONLY}" -eq 1 ]; then
  echo "==> dashboard.html ready. Upload it to gcburton.org."
  exit 0
fi

echo "==> Launching interactive Streamlit dashboard…"
streamlit run dashboard.py
