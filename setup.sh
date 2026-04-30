#!/usr/bin/env bash
# Set up the CDS scraper virtual environment.
# Usage: bash setup.sh

set -euo pipefail

VENV_DIR=".venv"

echo "==> Creating virtual environment in ${VENV_DIR}/"
python3 -m venv "${VENV_DIR}"

echo "==> Activating virtual environment"
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
echo "  1. Activate the venv:  source ${VENV_DIR}/bin/activate"
echo "  2. (Optional) Add CDS credentials to ~/.cdsapirc"
echo "     See: https://cds.climate.copernicus.eu/api-how-to"
echo "  3. Fetch data:         python scraper.py --demo"
echo "  4. Run dashboard:      streamlit run dashboard.py"
echo "     or use the helper:  bash run_dashboard.sh"
