#!/usr/bin/env bash
# Activate the venv (if present) and launch the Streamlit dashboard.
# Usage: bash run_dashboard.sh

set -euo pipefail

VENV_DIR=".venv"

if [ -d "${VENV_DIR}" ]; then
    # shellcheck disable=SC1090
    source "${VENV_DIR}/bin/activate"
fi

# Pre-fetch demo data so the first dashboard load is instant
if [ ! -f "data/era5_demo.csv" ]; then
    echo "==> Pre-fetching demo data…"
    python scraper.py --demo
fi

echo "==> Starting CDS dashboard…"
streamlit run dashboard.py "$@"
