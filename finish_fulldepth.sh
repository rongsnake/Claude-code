#!/usr/bin/env bash
# One-shot, session-independent finisher for the full-depth rebuild.
# Waits for the in-flight fetch_docs download to complete, then rebuilds the
# joined/analytics tables, the run index + extractive summaries, the dashboard,
# reloads the API, deploys the gated docs, and commits + pushes to the branch.
# Launched as a transient systemd --user unit so it survives terminal/session close.
set -uo pipefail
cd /home/test/cds-dashboard
PY=/home/test/cds-dashboard/.venv/bin/python
LOG=/home/test/cds-dashboard/finish_fulldepth.log
exec >>"$LOG" 2>&1
echo "================ finish_fulldepth started $(date -Is) ================"

# 1) wait for the running download to finish (documents.csv is written at the end)
echo "waiting for any running fetch_docs.py to finish…"
while pgrep -f "fetch_docs.py" >/dev/null 2>&1; do sleep 30; done
echo "fetch_docs done. documents.csv rows: $(wc -l < data/documents.csv 2>/dev/null || echo MISSING)"
echo "docs on disk: $(ls data/docs 2>/dev/null | wc -l)"

# 2) rejoin auctions↔determinations + refresh analytics over the full set
$PY reconcile.py || echo "reconcile failed (continuing)"
$PY analytics.py || echo "analytics failed (continuing)"

# 3) build the run index + extractive summaries (RAG embedding capped) + dashboard
$PY build_index.py || $PY build_index.py --no-embed || echo "build_index failed"
mkdir -p public
$PY build_dashboard.py --output public/index.html || echo "build_dashboard failed"

# 4) reload the running Q&A API and deploy the gated document downloads
curl -s -m 5 -X POST http://localhost:5055/cds/api/reload >/dev/null 2>&1 || true
if [ -x ./deploy.sh ]; then ./deploy.sh || echo "deploy.sh failed"; fi

# 5) commit + push (code + data + dashboard); untrack now-ignored doctext
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git rm -r --cached --quiet --ignore-unmatch data/doctext >/dev/null 2>&1 || true
git add -A
if git diff --cached --quiet; then
  echo "nothing to commit"
else
  git commit -m "Full-depth DC archive: feed crawler, gated doc downloads, extractive run summaries

Crawl the entire WP Document Revisions archive via the document RSS feed (the
REST API is Wordfence-locked): ~2.5k determinations across all regions and years
(2009-2026) vs the previous 130 auction-anchored rows. fetch_docs downloads every
linked document; build_index groups them into determination runs with extractive
(no-LLM) summaries — entity, committee, credit event, meeting/auction dates,
outcome, vote, auction recovery, and notable flags — plus a per-name download
list served as gated local copies at /cds/docs/. The dashboard now lists runs,
each with its summary and grouped document downloads behind the existing login.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
  for i in 1 2 3 4; do
    git push origin "$BRANCH" && break || { echo "push retry $i"; sleep $((2**i)); }
  done
fi
echo "================ finish_fulldepth done $(date -Is) ================"
