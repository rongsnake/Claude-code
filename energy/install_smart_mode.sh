#!/usr/bin/env bash
# Install / update Auto Smart Mode on the Pi's live Alstin Lodge energy dashboard.
#
#   sudo bash install_smart_mode.sh [/mnt/media/ai-projects/alstin-lodge-energy]
#
# Idempotent, keeps a backup of every file it changes, prints each step. It:
#   1. copies the Smart Mode files from this checkout (energy/alstin/) next to webapp.py:
#      auto_smart_mode.py, smart_mode_api.py, web/smart_mode_card.html
#   2. mounts the API in webapp.py  (app.include_router(smart_mode_router, prefix="/smart"))
#   3. puts the Smart Mode card into web/index.html under the Battery-controls row
#   4. writes config.json (seeded from config.yaml: 13.5 kWh, 5 kW, reserve floor…)
#   5. installs energy-smart.service (system unit, User=test, .venv python) and starts it
#   6. restarts energy-web.service so /smart/… is live
# The engine picks up the dashboard's Tesla Fleet API token file automatically.
set -euo pipefail

APP_DIR="${1:-/mnt/media/ai-projects/alstin-lodge-energy}"
SRC="$(cd "$(dirname "$0")/alstin" && pwd)"
[ -f "$APP_DIR/webapp.py" ] || { echo "no webapp.py in $APP_DIR" >&2; exit 2; }
PYTHON="${PYTHON:-$( [ -x "$APP_DIR/.venv/bin/python" ] && echo "$APP_DIR/.venv/bin/python" || command -v python3 )}"
OWNER="$(stat -c %U "$APP_DIR/webapp.py" 2>/dev/null || echo "$USER")"
STAMP="$(date +%Y%m%d-%H%M%S)"
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
as_owner() { if [ "$(id -un)" != "$OWNER" ] && command -v sudo >/dev/null; then sudo -u "$OWNER" "$@"; else "$@"; fi; }

say "Copying Smart Mode files into $APP_DIR (owner $OWNER, python $PYTHON)"
mkdir -p "$APP_DIR/web"
for f in auto_smart_mode.py smart_mode_api.py web/smart_mode_card.html; do
  cp "$SRC/$f" "$APP_DIR/$f"; chown "$OWNER" "$APP_DIR/$f" 2>/dev/null || true
done
"$PYTHON" -c "import fastapi, uvicorn, yaml, pypowerwall" 2>/dev/null || echo "note: the app venv lacks one of fastapi/uvicorn/yaml/pypowerwall — install them first" >&2

# --- 2. mount the router --------------------------------------------------------------
if grep -q "smart_mode_router" "$APP_DIR/webapp.py"; then
  say "webapp.py already mounts the Smart Mode router"
else
  cp -p "$APP_DIR/webapp.py" "$APP_DIR/webapp.py.bak-$STAMP"
  APPVAR="$(grep -oE '^[A-Za-z_][A-Za-z0-9_]*\s*=\s*FastAPI\(' "$APP_DIR/webapp.py" | head -1 | sed -E 's/\s*=.*//')"
  [ -n "$APPVAR" ] || { echo "could not find 'xxx = FastAPI(' in webapp.py" >&2; exit 1; }
  cat >> "$APP_DIR/webapp.py" <<EOF

# --- Auto Smart Mode (overnight Powerwall grid charge in the Octopus Go window) — install_smart_mode.sh $STAMP
from smart_mode_api import router as smart_mode_router  # noqa: E402
$APPVAR.include_router(smart_mode_router, prefix="/smart")
EOF
  (cd "$APP_DIR" && "$PYTHON" -c "import ast; ast.parse(open('webapp.py').read())")
  say "Patched webapp.py (backup webapp.py.bak-$STAMP)"
fi

# --- 3. the card in the page ------------------------------------------------------------
PAGE="$APP_DIR/web/index.html"
if [ ! -f "$PAGE" ]; then
  echo "no web/index.html in $APP_DIR — paste web/smart_mode_card.html into the dashboard page by hand" >&2
elif grep -q 'id="smartMode"' "$PAGE"; then
  say "Card already present in web/index.html"
else
  cp -p "$PAGE" "$PAGE.bak-$STAMP"
  "$PYTHON" - "$PAGE" "$APP_DIR/web/smart_mode_card.html" <<'EOF'
import sys
page, card = sys.argv[1], sys.argv[2]
html = open(page).read(); snippet = open(card).read()
anchor = "  <!-- SOLAR OUTLOOK -->"
if anchor in html:
    html = html.replace(anchor, "  <!-- AUTO SMART MODE -->\n" + snippet + "\n" + anchor, 1)
else:
    i = html.lower().rfind("</body>")
    html = (html[:i] + snippet + "\n" + html[i:]) if i >= 0 else html + snippet
open(page, "w").write(html)
EOF
  say "Card added to web/index.html (backup index.html.bak-$STAMP)"
fi

# --- 4. config.json ----------------------------------------------------------------------
if [ ! -f "$APP_DIR/config.json" ]; then
  (cd "$APP_DIR" && ENERGY_DIR="$APP_DIR" as_owner "$PYTHON" auto_smart_mode.py --init-config)
else
  say "config.json already exists (kept)"
fi
[ -f "$APP_DIR/.pypowerwall.fleetapi" ] && say "Found .pypowerwall.fleetapi — engine will use the Fleet API (provider auto → fleetapi)" \
  || echo "WARNING: no .pypowerwall.fleetapi in $APP_DIR — the engine will run in dry-run against a simulated Powerwall" >&2
if "$PYTHON" - "$APP_DIR" <<'EOF'
import sys, yaml, pathlib
c = (yaml.safe_load((pathlib.Path(sys.argv[1]) / "config.yaml").read_text()) or {}).get("control") or {}
sys.exit(0 if (c.get("enabled") and not c.get("dry_run", True)) else 1)
EOF
then echo "WARNING: feed.py live control is ON in config.yaml — Smart Mode will stand down until you disable one of them" >&2; fi

# --- 5/6. services ----------------------------------------------------------------------
if ! command -v systemctl >/dev/null 2>&1; then
  echo "no systemctl here — run the engine with: $PYTHON $APP_DIR/auto_smart_mode.py --daemon" >&2; exit 0
fi
UNIT=/etc/systemd/system/energy-smart.service
say "Installing $UNIT"
sed -e "s#/mnt/media/ai-projects/alstin-lodge-energy#$APP_DIR#g" -e "s#^User=.*#User=$OWNER#" \
    -e "s#\.venv/bin/python#$(realpath --relative-to="$APP_DIR" "$PYTHON" 2>/dev/null || echo "$PYTHON")#" \
    "$SRC/energy-smart.service" | sudo tee "$UNIT" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now energy-smart.service
sudo systemctl restart energy-web.service 2>/dev/null || echo "note: could not restart energy-web.service — restart the dashboard by hand" >&2
sleep 2
sudo systemctl --no-pager --lines=5 status energy-smart.service || true
say "Check: curl -s http://127.0.0.1:5077/smart/status | head -c 400"
say "Then open energy.gcburton.org — the Auto Smart Mode card sits under Battery controls. Toggle it on there."
