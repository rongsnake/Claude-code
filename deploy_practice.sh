#!/usr/bin/env bash
#
# Publish The Practice to gcburton.org — and, optionally, to a password-free
# local listener on the same machine.
#
# Run this ON THE HOST that serves gcburton.org (the Pi). That host serves the
# site with Caddy behind a site-wide basic_auth, so publishing is a file copy
# into the already-gated docroot: no new gate, no new credentials.
#
#   bash deploy_practice.sh                     # build + publish to /practice/
#   LOCAL=1 bash deploy_practice.sh             # also install the local listener
#   DOCROOT=/srv/www bash deploy_practice.sh    # different docroot
#
# Result:
#   https://gcburton.org/practice/   → the existing site password
#   http://localhost:8080/           → same page, no password (LOCAL=1)
#
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

DOCROOT="${DOCROOT:-/home/test/www/gcburton.org}"   # Caddy docroot for the site
SUBDIR="${SUBDIR:-practice}"
DEST="$DOCROOT/$SUBDIR"
LOCAL="${LOCAL:-0}"
LOCAL_PORT="${LOCAL_PORT:-8080}"
CADDY_SNIPPET="${CADDY_SNIPPET:-/etc/caddy/practice-local.caddy}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"

PY="python3"
[[ -x .venv/bin/python ]] && PY=".venv/bin/python"

# ── 1) Build the page ────────────────────────────────────────────────────────
echo "→ Building the page"
"$PY" build_practice.py

# ── 2) Build the contents index, if it is missing ────────────────────────────
# Re-run build_contents.py yourself with --root arguments to pull in the
# definitions sets and reports that live outside this repo. See README.
if [[ ! -f public/practice/contents.js ]]; then
  if [[ -f data/documents.csv ]]; then
    echo "→ Building the contents index from data/documents.csv"
    "$PY" build_contents.py --docs data/documents.csv
  else
    echo "  (no contents.js and no data/documents.csv — Contents will show setup steps)"
  fi
fi

# ── 3) Publish into the gated docroot ────────────────────────────────────────
if [[ ! -d "$DOCROOT" ]]; then
  echo "✗ Docroot $DOCROOT not found. Set DOCROOT=… to the directory Caddy serves." >&2
  exit 1
fi

echo "→ Publishing to $DEST"
mkdir -p "$DEST"
[[ -f "$DEST/index.html" ]] && cp -a "$DEST/index.html" "$DEST/index.html.bak-$(date +%Y%m%d-%H%M%S)"
install -m 644 public/practice/index.html "$DEST/index.html"
[[ -f public/practice/contents.js ]] && install -m 644 public/practice/contents.js "$DEST/contents.js"

# Keep ownership consistent with the rest of the docroot.
owner="$(stat -c '%U:%G' "$DOCROOT" 2>/dev/null || true)"
[[ -n "$owner" ]] && chown -R "$owner" "$DEST" 2>/dev/null || true

# ── 4) Optional: the password-free local listener ────────────────────────────
if [[ "$LOCAL" == "1" ]]; then
  if [[ $EUID -ne 0 ]]; then
    echo "  ! LOCAL=1 needs root to write $CADDY_SNIPPET — re-run with sudo -E" >&2
  else
    echo "→ Installing the local listener on 127.0.0.1:$LOCAL_PORT"
    sed -e "s#/home/test/www/gcburton.org/practice#$DEST#" \
        -e "s#127.0.0.1:8080#127.0.0.1:$LOCAL_PORT#" \
        practice/practice-local.caddy > "$CADDY_SNIPPET"
    if ! grep -qF "$CADDY_SNIPPET" "$CADDYFILE"; then
      cp -a "$CADDYFILE" "$CADDYFILE.bak-practice"
      printf '\nimport %s\n' "$CADDY_SNIPPET" >> "$CADDYFILE"
      echo "  added 'import $CADDY_SNIPPET' to $CADDYFILE (backup: $CADDYFILE.bak-practice)"
    fi
    if caddy validate --config "$CADDYFILE" >/dev/null 2>&1; then
      systemctl reload caddy
      echo "  local listener live"
    else
      echo "✗ caddy validate failed — restoring $CADDYFILE" >&2
      [[ -f "$CADDYFILE.bak-practice" ]] && mv "$CADDYFILE.bak-practice" "$CADDYFILE"
      caddy validate --config "$CADDYFILE" >/dev/null 2>&1 && systemctl reload caddy || true
      exit 1
    fi
  fi
fi

echo
echo "✅ Published"
echo "   https://gcburton.org/$SUBDIR/        (site password)"
[[ "$LOCAL" == "1" ]] && echo "   http://localhost:$LOCAL_PORT/          (no password, this machine only)"
echo "   file://$DEST/index.html              (no password, no server at all)"
