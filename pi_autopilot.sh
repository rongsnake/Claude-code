#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# pi_autopilot.sh — RUN ONCE on the Raspberry Pi. After this, the Pi refreshes
# the CDS dashboard on a weekly schedule forever (live scrape → build → push),
# and a GitHub Action publishes it to GitHub Pages on every push.
#
#   curl-free, idempotent. Re-running it just updates the timer.
#
#   Usage:
#     bash pi_autopilot.sh                 # weekly (Mondays 06:00 local)
#     bash pi_autopilot.sh --daily         # daily 06:00
#     bash pi_autopilot.sh --on-calendar "Mon *-*-* 06:00:00"   # custom systemd OnCalendar
#
# It installs a systemd *system* timer (needs sudo). The work itself runs as the
# current user so git push uses your existing credentials/SSH agent.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(id -un)"
ONCAL="Mon *-*-* 06:00:00"          # default: weekly

while [ $# -gt 0 ]; do
  case "$1" in
    --daily)        ONCAL="*-*-* 06:00:00" ;;
    --on-calendar)  shift; ONCAL="$1" ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
  shift
done

echo "==> Repo:    $REPO_DIR"
echo "==> User:    $RUN_USER"
echo "==> Schedule: $ONCAL"

# 1. venv + deps ──────────────────────────────────────────────────────────────
echo "==> Setting up virtualenv + dependencies…"
[ -d "$REPO_DIR/.venv" ] || python3 -m venv "$REPO_DIR/.venv"
# shellcheck disable=SC1091
source "$REPO_DIR/.venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$REPO_DIR/requirements.txt"
deactivate

# 2. the refresh script the timer will call ───────────────────────────────────
cat > "$REPO_DIR/cds_refresh.sh" <<'REFRESH'
#!/usr/bin/env bash
# Live refresh + build + commit/push. Invoked by the systemd timer (or by hand).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source .venv/bin/activate

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git pull --ff-only origin "$BRANCH" || true

echo "== live scrape =="
python cds_dc_scraper.py --pdf || python cds_dc_scraper.py || true
python creditex_scraper.py     || true
python reconcile.py
python analytics.py

# Gate the scrape before anything leaves this box. The scrapers above are
# best-effort (`|| true`), so a 403 or a changed selector yields a *partial*
# dataset rather than a failure — and on 2026-06-22 that partial run silently
# replaced good data (auctions 245 -> 15, matched 120 -> 0), deployed it, and
# pushed it. check_refresh.py compares this run against the last commit and
# rejects a collapsed table or a vanished source.
if ! python check_refresh.py; then
  echo "== refresh REJECTED: restoring last good data, nothing built or deployed =="
  git checkout -- data
  exit 1
fi

python build_dashboard.py
mkdir -p public
python build_dashboard.py --output public/index.html

# Optional local deploy hook: if you create ./deploy.sh it runs here.
# (Use it the day you learn where gcburton.org is served from. See deploy.sh.example.)
if [ -x ./deploy.sh ]; then
  echo "== running local deploy hook =="
  ./deploy.sh || echo "deploy.sh failed (continuing)"
fi

git add -A data dashboard.html public/index.html
if git diff --cached --quiet; then
  echo "No data changes this run."
else
  git commit -m "chore: automated CDS dashboard refresh [skip ci]"
  for i in 1 2 3 4; do
    git push origin "$BRANCH" && break || { echo "push retry $i"; sleep $((2**i)); }
  done
fi
REFRESH
chmod +x "$REPO_DIR/cds_refresh.sh"

# 3. systemd service + timer ───────────────────────────────────────────────────
echo "==> Installing systemd service + timer (sudo)…"
sudo tee /etc/systemd/system/cds-refresh.service >/dev/null <<UNIT
[Unit]
Description=Refresh CDS Determinations dashboard (scrape, build, push)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/env bash $REPO_DIR/cds_refresh.sh
UNIT

sudo tee /etc/systemd/system/cds-refresh.timer >/dev/null <<UNIT
[Unit]
Description=Schedule for CDS dashboard refresh

[Timer]
OnCalendar=$ONCAL
Persistent=true

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now cds-refresh.timer

echo
echo "✅ Done. The Pi will now refresh the dashboard automatically ($ONCAL)."
echo "   • Run it right now:        sudo systemctl start cds-refresh.service"
echo "   • Watch the last run:      journalctl -u cds-refresh.service -n 50 --no-pager"
echo "   • Next scheduled run:      systemctl list-timers cds-refresh.timer"
echo
echo "Publishing: each push triggers the GitHub Action -> GitHub Pages."
echo "Enable Pages once: repo Settings -> Pages -> Source: GitHub Actions."
