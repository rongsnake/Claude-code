#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# pi_autopilot.sh — RUN ONCE on the Raspberry Pi. After this, the Pi refreshes
# the CDS dashboard on a schedule (live scrape → build → commit → push), and the
# GitHub Action publishes it to Pages on every push.
#
#   Idempotent. Re-running it re-installs the timer and rewrites cds_refresh.sh.
#
#   Usage:
#     bash pi_autopilot.sh                 # weekly (Mondays 06:00 local)
#     bash pi_autopilot.sh --daily         # daily 06:00
#     bash pi_autopilot.sh --on-calendar "Mon *-*-* 06:00:00"   # custom OnCalendar
#     bash pi_autopilot.sh --status        # health check: is the loop actually working?
#
# It installs a systemd *system* timer (needs sudo). The work runs as the current
# user so git push uses that user's credentials.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(id -un)"
ONCAL="Mon *-*-* 06:00:00"          # default: weekly
STATUS_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --daily)        ONCAL="*-*-* 06:00:00" ;;
    --on-calendar)  shift; ONCAL="$1" ;;
    --status)       STATUS_ONLY=1 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
  shift
done

# ── --status: report whether the loop is genuinely working ───────────────────
if [ "$STATUS_ONLY" -eq 1 ]; then
  echo "=== timer ==="
  systemctl list-timers cds-refresh.timer --no-pager 2>/dev/null || echo "(timer not installed)"
  echo
  echo "=== last service result ==="
  systemctl show cds-refresh.service -p Result -p ExecMainStatus -p ActiveState 2>/dev/null \
    || echo "(service not installed)"
  echo
  echo "=== last successful refresh (heartbeat) ==="
  if [ -f "$REPO_DIR/data/.last_refresh" ]; then
    cat "$REPO_DIR/data/.last_refresh"
    echo
    LAST_EPOCH="$(sed -n 's/^epoch=//p' "$REPO_DIR/data/.last_refresh" | head -1)"
    if [ -n "${LAST_EPOCH:-}" ]; then
      AGE_DAYS=$(( ( $(date +%s) - LAST_EPOCH ) / 86400 ))
      echo "age: ${AGE_DAYS} days"
      [ "$AGE_DAYS" -gt 14 ] && echo "⚠️  STALE — the refresh has not completed in over 2 weeks."
    fi
  else
    echo "(no heartbeat yet — the refresh has never completed successfully)"
  fi
  echo
  echo "=== can this user push? ==="
  if git -C "$REPO_DIR" push --dry-run origin "$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)" >/dev/null 2>&1; then
    echo "✅ push OK"
  else
    echo "❌ push FAILS — this is the usual cause of a silently dead loop."
    echo "   Fix with a credential helper the timer can use non-interactively:"
    echo "     git config --global credential.helper store"
    echo "     git push        # once, interactively, to save the token"
    echo "   (or switch the remote to SSH with a passphrase-less deploy key)"
  fi
  echo
  echo "=== recent service log ==="
  journalctl -u cds-refresh.service -n 25 --no-pager 2>/dev/null || true
  exit 0
fi

echo "==> Repo:     $REPO_DIR"
echo "==> User:     $RUN_USER"
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
#
# Design note: every step that matters fails LOUDLY (non-zero exit), so a broken
# loop shows up as a failed systemd unit instead of quietly doing nothing. The
# previous version swallowed push failures, so the unit reported success for
# weeks while nothing reached GitHub.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source .venv/bin/activate

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# ── preflight: verify we can push BEFORE spending an hour scraping ───────────
if ! git push --dry-run origin "$BRANCH" >/dev/null 2>&1; then
  echo "FATAL: git push is not possible as user $(id -un) in this environment." >&2
  echo "       The scrape would run and then be thrown away, so aborting now." >&2
  echo "       Fix: git config --global credential.helper store && git push" >&2
  echo "       (or use a passphrase-less SSH deploy key for origin)" >&2
  exit 1
fi

# Survive divergence: a plain --ff-only pull fails whenever the branch has moved
# on both sides, which then guarantees a rejected push.
git fetch origin "$BRANCH"
git pull --rebase --autostash origin "$BRANCH"

echo "== live scrape =="
SCRAPE_OK=1
python cds_dc_scraper.py --pdf || python cds_dc_scraper.py || SCRAPE_OK=0
python creditex_scraper.py || SCRAPE_OK=0
[ "$SCRAPE_OK" -eq 1 ] || echo "WARNING: at least one scraper failed; rebuilding from existing data."

python reconcile.py
python analytics.py

# Gate the scrape before anything leaves this box. The scrapers above are
# best-effort (`|| true`), so a 403 or a changed selector yields a *partial*
# dataset rather than a failure. That already produced a collapsed dataset on
# the refine/2026-06-15 branch (auctions 245 -> 15, matched 120 -> 0) which was
# committed and deployed without complaint. check_refresh.py compares this run
# against the last commit and rejects a collapsed table or a vanished source.
if ! python check_refresh.py; then
  echo "== refresh REJECTED: restoring last good data, nothing built or deployed =="
  git checkout -- data
  exit 1
fi

python build_dashboard.py
mkdir -p public
python build_dashboard.py --output public/index.html

# Optional local deploy hook: if you create ./deploy.sh it runs here.
# (See deploy.sh.example for local-copy / rsync / Netlify variants.)
if [ -x ./deploy.sh ]; then
  echo "== running local deploy hook =="
  ./deploy.sh || echo "deploy.sh failed (continuing)"
fi

# Record a heartbeat so staleness is visible even if nothing else changed.
printf 'utc=%s\nepoch=%s\nscrape_ok=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(date +%s)" "$SCRAPE_OK" > data/.last_refresh

# `public/` in full: credit_events.csv and .xlsx live there too and were being
# left behind by the old `git add data dashboard.html public/index.html`, so the
# published XLSX drifted out of sync with the CSV.
git add -A data public dashboard.html
if git diff --cached --quiet; then
  echo "No changes this run."
  exit 0
fi

git commit -m "chore: automated CDS dashboard refresh [skip ci]"
for i in 1 2 3 4; do
  if git push origin "$BRANCH"; then
    echo "pushed."
    exit 0
  fi
  echo "push failed (attempt $i)"; sleep $((2**i))
  git pull --rebase --autostash origin "$BRANCH" || true
done
echo "FATAL: could not push after 4 attempts — the commit is local only." >&2
exit 1
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
echo "✅ Done. The Pi will refresh the dashboard automatically ($ONCAL)."
echo "   • Run it right now:   sudo systemctl start cds-refresh.service"
echo "   • Health check:       bash pi_autopilot.sh --status"
echo "   • Logs:               journalctl -u cds-refresh.service -n 50 --no-pager"
echo
echo "Publishing: each push triggers the GitHub Action -> GitHub Pages."
