#!/usr/bin/env bash
# Install Auto Smart Mode into the existing Alstin Lodge energy dashboard on the Pi.
#
# What it does (idempotent, with backups; prints every change it makes):
#   1. Copies auto_smart_mode.py, energy_api.py and smart_mode_card.html next to webapp.py.
#   2. Patches webapp.py to mount the Smart Mode API under /smart  (app.include_router).
#   3. Injects the Smart Mode card into the dashboard's HTML (before </body>) if a
#      single index/template HTML file can be found; otherwise tells you where to put it.
#   4. Installs + starts the engine as a user systemd unit (energy-smart.service) using
#      the same Python as the dashboard.
#   5. Writes config.json with defaults if missing (provider dry-run until you switch it).
#
# Usage on the Pi:   bash install_smart_mode.sh /path/to/alstin-lodge-energy
#   env overrides:   PYTHON=/path/to/venv/bin/python  APP_UNIT=alstin-lodge-energy.service
set -euo pipefail

APP_DIR="${1:-}"
[ -n "$APP_DIR" ] || { echo "usage: $0 /path/to/alstin-lodge-energy" >&2; exit 2; }
[ -f "$APP_DIR/webapp.py" ] || { echo "no webapp.py in $APP_DIR" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-$( [ -x "$APP_DIR/.venv/bin/python" ] && echo "$APP_DIR/.venv/bin/python" || command -v python3 )}"
APP_UNIT="${APP_UNIT:-}"
STAMP="$(date +%Y%m%d-%H%M%S)"
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

say "Copying engine + API + card into $APP_DIR"
cp "$HERE/auto_smart_mode.py" "$HERE/energy_api.py" "$HERE/smart_mode_card.html" "$APP_DIR/"
"$PYTHON" -c "import fastapi, uvicorn" 2>/dev/null || "$PYTHON" -m pip install -q fastapi uvicorn
"$PYTHON" -c "import teslapy" 2>/dev/null || echo "note: teslapy not installed for $PYTHON — engine runs dry-run until: $PYTHON -m pip install teslapy"

# --- 2. mount the router in webapp.py -------------------------------------------------
if grep -q "smart_mode_router" "$APP_DIR/webapp.py"; then
  say "webapp.py already mounts the Smart Mode router"
else
  cp "$APP_DIR/webapp.py" "$APP_DIR/webapp.py.bak-$STAMP"
  APPVAR="$(grep -oE '^[A-Za-z_][A-Za-z0-9_]*\s*=\s*FastAPI\(' "$APP_DIR/webapp.py" | head -1 | sed -E 's/\s*=.*//')"
  [ -n "$APPVAR" ] || { echo "could not find 'xxx = FastAPI(' in webapp.py — add manually:
    from energy_api import router as smart_mode_router
    app.include_router(smart_mode_router, prefix=\"/smart\")" >&2; exit 1; }
  cat >> "$APP_DIR/webapp.py" <<EOF

# --- Auto Smart Mode (Tesla overnight charging) — added by install_smart_mode.sh $STAMP ---
from energy_api import router as smart_mode_router  # noqa: E402
$APPVAR.include_router(smart_mode_router, prefix="/smart")
EOF
  say "Patched webapp.py: $APPVAR.include_router(smart_mode_router, prefix=\"/smart\")  (backup: webapp.py.bak-$STAMP)"
  (cd "$APP_DIR" && "$PYTHON" -c "import ast,sys; ast.parse(open('webapp.py').read())") && say "webapp.py parses"
fi

# --- 3. inject the card into the page -------------------------------------------------
mapfile -t PAGES < <(cd "$APP_DIR" && grep -lis "</body>" index.html templates/*.html static/*.html *.html 2>/dev/null | grep -v '^smart_mode_card.html$' | sort -u)
if [ "${#PAGES[@]}" -eq 1 ]; then
  PAGE="$APP_DIR/${PAGES[0]}"
  if grep -q 'id="smartMode"' "$PAGE"; then
    say "Card already present in ${PAGES[0]}"
  else
    cp "$PAGE" "$PAGE.bak-$STAMP"
    "$PYTHON" - "$PAGE" "$APP_DIR/smart_mode_card.html" <<'EOF'
import sys, re
page, card = sys.argv[1], sys.argv[2]
html = open(page).read(); snippet = open(card).read()
i = html.lower().rfind("</body>")
html = html[:i] + snippet + "\n" + html[i:] if i >= 0 else html + snippet
open(page, "w").write(html)
EOF
    say "Injected the Smart Mode card into ${PAGES[0]} (backup: ${PAGES[0]}.bak-$STAMP)"
  fi
elif [ "${#PAGES[@]}" -eq 0 ]; then
  echo "No HTML page with </body> found in $APP_DIR — if webapp.py renders HTML from a Python string, paste the contents of smart_mode_card.html before </body> there." >&2
else
  echo "Several HTML pages found (${PAGES[*]}) — paste smart_mode_card.html before </body> in the dashboard's main page." >&2
fi

# --- 4. engine service ------------------------------------------------------------------
(cd "$APP_DIR" && ENERGY_DIR="$APP_DIR" "$PYTHON" auto_smart_mode.py --init-config) || true
if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user daemon-reload >/dev/null 2>&1; then
  echo "user systemd not available here — skipping the service steps (run the engine with: $PYTHON $APP_DIR/auto_smart_mode.py --daemon)" >&2
  exit 0
fi
say "Installing the engine as a user systemd unit"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/energy-smart.service" <<EOF
[Unit]
Description=Auto Smart Mode — overnight Tesla charging engine (Octopus Go window)
After=network-online.target

[Service]
WorkingDirectory=$APP_DIR
Environment=ENERGY_DIR=$APP_DIR
ExecStart=$PYTHON $APP_DIR/auto_smart_mode.py --daemon
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now energy-smart.service
systemctl --user --no-pager --lines=3 status energy-smart.service || true

# --- 5. restart the dashboard so the router is live -------------------------------------
if [ -z "$APP_UNIT" ]; then
  APP_UNIT="$(systemctl --user list-units --type=service --all --no-legend 2>/dev/null | awk '{print $1}' | grep -iE 'energy|alstin|webapp' | grep -v energy-smart | head -1 || true)"
fi
if [ -n "$APP_UNIT" ]; then
  say "Restarting dashboard unit $APP_UNIT"
  systemctl --user restart "$APP_UNIT" 2>/dev/null || sudo systemctl restart "$APP_UNIT"
else
  echo "Could not identify the dashboard's systemd unit — restart it by hand so /smart/status goes live." >&2
fi

say "Done. Check:  curl -s http://127.0.0.1:5077/smart/status | head -c 400"
say "Then edit $APP_DIR/config.json: provider=teslapy, tesla_email, battery_kwh, charger_kw; run '$PYTHON auto_smart_mode.py --once' for the Tesla login; systemctl --user restart energy-smart"
