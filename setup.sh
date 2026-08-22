#!/usr/bin/env bash
# Set up the CDS Determinations Committees scraper virtual environment.
# Usage: bash setup.sh

set -euo pipefail

VENV_DIR=".venv"

echo "==> Creating virtual environment in ${VENV_DIR}/"
python3 -m venv "${VENV_DIR}"

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "==> Upgrading pip"
pip install --quiet --upgrade pip

echo "==> Installing dependencies from requirements.txt"
pip install --quiet -r requirements.txt

echo ""
echo "✅  Setup complete."
echo ""
echo "Next steps:"
echo "  1. Activate:        source ${VENV_DIR}/bin/activate"
echo "  2. Refresh data:    python cds_dc_scraper.py          # live scrape"
echo "       (offline/dev):  python cds_dc_scraper.py --demo   # synthetic data"
echo "  3a. Static site:    python build_dashboard.py          # -> dashboard.html"
echo "  3b. Interactive:    streamlit run dashboard.py"
echo ""
echo "  NOTE: the live scrape only works from a network that can reach"
echo "        cdsdeterminationscommittees.org (it blocks bots / unknown egress)."
