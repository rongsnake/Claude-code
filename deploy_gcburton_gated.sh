#!/usr/bin/env bash
#
# Deploy the CDS dashboard to gcburton.org BEHIND A LOGIN (nginx HTTP Basic auth).
# Run this ON THE HOST that serves gcburton.org (your Pi or web server).
#
#   sudo bash deploy_gcburton_gated.sh
#
# It is idempotent: re-running updates the dashboard file and (if you pass a new
# password) the credentials, without duplicating nginx config.
#
# Result:  https://gcburton.org/cds/   →  prompts for username + password,
#          then serves the dashboard. Nothing is exposed publicly.
#
# ── Tunables (override via env) ──────────────────────────────────────────────
#   AUTH_USER=gareth AUTH_PASS='s3cret' sudo -E bash deploy_gcburton_gated.sh
#   URL_PATH=/cds/  WEBROOT=/var/www/gcburton-gated  DOMAIN=gcburton.org
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

DOMAIN="${DOMAIN:-gcburton.org}"
URL_PATH="${URL_PATH:-/cds/}"                       # public path, must start+end with /
WEBROOT="${WEBROOT:-/var/www/gcburton-gated}"       # auth-only docroot (NOT /var/www/html)
HTPASSWD="${HTPASSWD:-/etc/nginx/.htpasswd-cds}"
SNIPPET="${SNIPPET:-/etc/nginx/snippets/cds-gated.conf}"
AUTH_USER="${AUTH_USER:-}"                           # prompted if empty
AUTH_PASS="${AUTH_PASS:-}"                           # prompted (hidden) if empty

# Must run as root (writes under /etc/nginx, /var/www, reloads nginx).
if [[ $EUID -ne 0 ]]; then
  echo "Please run as root:  sudo bash $0" >&2; exit 1
fi

sub_path="${URL_PATH#/}"; sub_path="${sub_path%/}"   # "cds"
DEST_DIR="$WEBROOT/$sub_path"

# ── 1) Build a fresh dashboard ───────────────────────────────────────────────
# Prefer the project venv; fall back to system python3. Skip if you've already
# built public/index.html and just want to (re)publish: pass SKIP_BUILD=1.
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  PY="python3"
  [[ -x .venv/bin/python ]] && PY=".venv/bin/python"
  echo "→ Building dashboard with $PY …"
  "$PY" build_dashboard.py --output public/index.html
fi
[[ -f public/index.html ]] || { echo "public/index.html missing (build failed?)" >&2; exit 1; }

# ── 2) Publish the file into the auth-gated docroot ──────────────────────────
echo "→ Publishing to $DEST_DIR/index.html"
install -d -m 755 "$DEST_DIR"
install -m 644 public/index.html "$DEST_DIR/index.html"
# Let nginx's worker user read it (www-data on Debian/RPi OS, nginx on RHEL).
WWW_USER="www-data"; id "$WWW_USER" &>/dev/null || WWW_USER="nginx"
chown -R "$WWW_USER":"$WWW_USER" "$WEBROOT" 2>/dev/null || true

# ── 3) Credentials (bcrypt .htpasswd) ────────────────────────────────────────
[[ -n "$AUTH_USER" ]] || read -r -p "Basic-auth username: " AUTH_USER
if [[ -z "$AUTH_PASS" ]]; then
  read -r -s -p "Basic-auth password: " AUTH_PASS; echo
  read -r -s -p "Confirm password:    " _p2; echo
  [[ "$AUTH_PASS" == "$_p2" ]] || { echo "Passwords did not match." >&2; exit 1; }
fi
if command -v htpasswd &>/dev/null; then
  # -c only when the file doesn't exist yet, so we don't wipe other users.
  [[ -f "$HTPASSWD" ]] && htpasswd -bB "$HTPASSWD" "$AUTH_USER" "$AUTH_PASS" \
                       || htpasswd -cbB "$HTPASSWD" "$AUTH_USER" "$AUTH_PASS"
else
  echo "  (htpasswd not found — using openssl; install apache2-utils for bcrypt)"
  hash="$(openssl passwd -apr1 "$AUTH_PASS")"
  if [[ -f "$HTPASSWD" ]]; then
    grep -qv "^$AUTH_USER:" "$HTPASSWD" 2>/dev/null && sed -i "/^$AUTH_USER:/d" "$HTPASSWD" || true
    echo "$AUTH_USER:$hash" >> "$HTPASSWD"
  else
    echo "$AUTH_USER:$hash" > "$HTPASSWD"
  fi
fi
chmod 640 "$HTPASSWD"; chown root:"$WWW_USER" "$HTPASSWD" 2>/dev/null || true

# ── 4) nginx location snippet (the gate) ─────────────────────────────────────
echo "→ Writing $SNIPPET"
install -d -m 755 "$(dirname "$SNIPPET")"
cat > "$SNIPPET" <<EOF
# CDS dashboard — login-gated. Included from the ${DOMAIN} server block.
location ${URL_PATH} {
    alias ${DEST_DIR}/;
    index index.html;
    auth_basic           "CDS dashboard — restricted";
    auth_basic_user_file ${HTPASSWD};
}
EOF

# ── 5) Wire the snippet into the gcburton.org server block ────────────────────
# Find the site config that owns this domain.
SITE_CONF="$(grep -rlE "server_name[^;]*\b${DOMAIN//./\\.}\b" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -1 || true)"
INCLUDE_LINE="    include ${SNIPPET};"
if [[ -n "$SITE_CONF" ]]; then
  if grep -qF "$SNIPPET" "$SITE_CONF"; then
    echo "→ Include already present in $SITE_CONF"
  else
    echo "→ Adding include to $SITE_CONF (backup: $SITE_CONF.bak-cds)"
    cp -a "$SITE_CONF" "$SITE_CONF.bak-cds"
    # Insert right after the first matching server_name line in that file.
    awk -v inc="$INCLUDE_LINE" -v dom="$DOMAIN" '
      !done && $0 ~ "server_name" && index($0, dom) { print; print inc; done=1; next } { print }
    ' "$SITE_CONF" > "$SITE_CONF.tmp-cds" && mv "$SITE_CONF.tmp-cds" "$SITE_CONF"
  fi
else
  cat <<MANUAL
⚠ Could not auto-locate the ${DOMAIN} server block under
  /etc/nginx/sites-enabled or /etc/nginx/conf.d. Add this line INSIDE that
  server { … } block yourself, then reload nginx:

${INCLUDE_LINE}

MANUAL
fi

# ── 6) Validate + reload ─────────────────────────────────────────────────────
echo "→ Testing nginx config"
if nginx -t; then
  systemctl reload nginx || service nginx reload
  echo
  echo "✅ Deployed. Visit: https://${DOMAIN}${URL_PATH}"
  echo "   Login as '${AUTH_USER}' with the password you set."
else
  echo "✗ nginx -t failed." >&2
  [[ -n "${SITE_CONF:-}" && -f "$SITE_CONF.bak-cds" ]] && {
    echo "  Restoring $SITE_CONF from backup." >&2; mv "$SITE_CONF.bak-cds" "$SITE_CONF"; }
  exit 1
fi
