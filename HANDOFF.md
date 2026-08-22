# Handoff — continuing this work on your Raspberry Pi

This file is the durable handoff. The work lives in **git** (branch
`claude/setup-cds-scraper-dashboard-i0TxS`, PR **#1**), which is the real
"save state" — there is no in-memory session to magically teleport unchanged.

## TL;DR — how to pick up where this left off

On the Pi:

```bash
git clone <your-fork-url> && cd claude-code      # or: git fetch && …
git checkout claude/setup-cds-scraper-dashboard-i0TxS
claude                                            # fresh session; reads CLAUDE.md + this file
```

That alone gives a new Claude Code session full context (via `CLAUDE.md` and
this doc). To literally resume *this* conversation, see the options below.

## Your questions, answered (verified against Claude Code docs, 2026)

**1. Is there a "handshake code" to resume this exact session on the Pi?**
There's no pairing token that copies a session between two *different local
machines*. Local session history is stored per-machine at
`~/.claude/projects/<project>/<id>.jsonl` and is **not synced**. BUT this is a
**cloud session**, and Claude Code has cloud↔local bridges:

- `claude --from-pr https://github.com/rongsnake/claude-code/pull/1`
  → resumes the session **linked to that PR** and checks out its branch.
- `claude --teleport <session-id>`
  → pulls a **cloud** session (and its branch) down to the local machine.
  (The `<session-id>` is shown in the web session UI.)

The closest thing to a "handshake code" is therefore **the PR link** (with
`--from-pr`) or **the session id** (with `--teleport`). Exact flags can vary by
Claude Code version — if either isn't present, the git checkout above always
works.

**2. Can you hardwire a link so this session transmits instructions to the Pi?**
There is **no peer-to-peer remote-control channel** between two Claude Code
instances on different machines. (`--remote-control` only lets a browser steer a
*local* session; MCP "channels" are one-way external→session.) What *does* work
as an instruction bus is **GitHub**, which both sides already share:

- I (this session) write instructions into the repo — `CLAUDE.md`, this file,
  a `TASKS.md`, or **PR/issue comments** — and the Pi's Claude Code reads/acts on
  them.
- This session is **subscribed to PR #1 activity**, so anything you (or the Pi's
  session) post on the PR comes back to me here. That's a real async loop today.
- Optional: install the **Claude Code GitHub Action**. Then an `@claude …`
  mention in an issue/PR triggers a Claude run that opens a PR — instructions
  left on GitHub get executed automatically (runs in Actions, not on the Pi).

## 2026-06 update — richer presentation + local-LLM Q&A

- The static dashboard was rebuilt: dropdown **filters** (committee incl. EMEA-only,
  credit event, decision, year range, entity, notable-issue), a wide **sortable table**,
  per-row **document drawers** (decisions / explanatory statements / pro-forma ASTs /
  final lists / participating bidders), a free-text **Ask** box, and an **Update** button.
- New `build_index.py` builds `data/index/` (cleaned determinations, a `documents.json`
  manifest with qualitative flags — discretion under the Rules, external review, lock-up,
  restructuring… — and RAG `chunks.json`+`embeddings.npy` via local Ollama).
- New `cds_api.py` (FastAPI :5055, behind Caddy `/cds/api/`) streams local-LLM RAG
  answers (`llama3.2:1b` — chosen because CPU prompt-eval dominates on the Pi; 1B evals
  ~3.6× faster than 3B) with citations, plus `/refresh` and `/status`. **Zero API cost.**
- systemd user units `cds-api.service` + `cds-refresh.timer` (Mon 06:00) installed; linger on.
- The Caddy reverse-proxy block for `/cds/api/*` → `localhost:5055` is **applied and live**.

## Current state (updated 2026-06-14, on the Pi)

- ✅ **Live refresh done on the Pi.** Both `cdsdeterminationscommittees.org` and
  `creditfixings.com` are reachable from this host (HTTP 200; the earlier 403s
  were the cloud sandbox's allowlisted egress, not the sites). Full pipeline ran:
  DC document-feed crawl → ISDA-index enrichment → Creditex auctions → reconcile →
  analytics → dashboard rebuild.
- ✅ **Data is genuinely live, not seed** (last good run, 2026-06-20): 2,574
  determinations (2009-12-09 → 2026-05-08) + 245 auctions. Sources:
  `document-feed` (2447), `dc-isda` (122), verified `reference` seed (4),
  `rest-api` (1). **0 `synthetic-demo` rows.** Reconciliation 4.7%.
- ⚠️ **OPEN — silent data regression on 2026-06-22 (and repeated 06-29).** The
  weekly refresh committed a *partial* scrape over the good data and deployed it:

  | | 06-20 (good) | 06-22 → now |
  |---|---|---|
  | determinations | 2,574 | 2,452 (all 122 `dc-isda` rows gone) |
  | auctions | 245 | 15 (`creditfixings` 245 → 12) |
  | matched | 120 | **0** (reconciliation 4.7% → 0.0%) |

  Cause: the scrapers are best-effort (`|| true` in `cds_refresh.sh`), so a 403 /
  changed selector yields partial data instead of a failure, and nothing checked
  the result before deploy + commit + push. The live `/cds/` dashboard has been
  serving a dataset with **zero reconciled auctions** since 06-22 — no recovery
  or days-to-auction analysis. Both scrapes need re-running on the Pi (with the
  new gate below); if the fresh scrape is good the numbers return on their own.
  To restore the last known-good data immediately instead:
  `git checkout 0ec12a4 -- data` (then rebuild + redeploy).
- ✅ **Gate added (`check_refresh.py`)** so this cannot recur silently. It runs
  after `analytics.py` and before build/deploy/commit, compares the run against
  the last commit, and rejects a collapsed table, a vanished source, or stray
  `synthetic-demo` rows — restoring the previous data and exiting non-zero.
  Verified against the real 06-22 data: it flags all three failures above.
  **It only takes effect on the Pi once `bash pi_autopilot.sh` is re-run** (that
  regenerates `cds_refresh.sh`), or the gate is pasted into the existing
  `cds_refresh.sh` by hand.
- ✅ **Data-honesty fix:** `enrich_from_dc_page()` previously stamped 6 historical
  LCDS determinations (TOYS, Avaya, Mediannuaire, Yell, Boston Generating, Truvo)
  with *today's* date when their DC page only exposed a post-auction footer date —
  giving determination dates years after their own auctions. Now it never assigns a
  post-auction/future date (leaves it blank). 0 determination-after-auction rows remain.
- ✅ **Deployed behind the login** at `https://gcburton.org/cds/`. The whole
  gcburton.org site is gated by Caddy `basic_auth` (user `Gareth`); `/cds/` returns
  HTTP 401 without credentials. Published files live at
  `/home/test/www/gcburton.org/cds/{index.html,credit_events.csv,credit_events.xlsx}`
  (prior index backed up as `index.html.bak-20260614-predeploy`).
- ✅ **Infra live:** `cds-api.service` running (uvicorn :5055), `cds-refresh.timer`
  next Mon 06:00, linger on; Caddy `/cds/api/*` proxy applied.
- ℹ️ **nginx vs Caddy:** this host serves gcburton.org with **Caddy**, so the
  nginx-based `deploy_gcburton_gated.sh` is not used here — deploy is a file copy
  into the already-gated Caddy docroot (above). The script now refuses to run when
  Caddy is present (`FORCE_NGINX=1` overrides).

## Next steps (run on the Pi / gcburton.org host — it can reach the DC site)

```bash
bash setup.sh && source .venv/bin/activate
python cds_dc_scraper.py --pdf                  # FULL live DC refresh (+ parse PDFs)
python creditex_scraper.py                      # live Creditex auction scrape
python reconcile.py                             # join auctions ↔ determinations
python analytics.py                             # refresh metrics + tidy export
python check_refresh.py                         # GATE: reject a collapsed scrape
python build_dashboard.py --output public/index.html
# deploy behind a login (see "Gated access" below — do NOT deploy public)
streamlit run dashboard.py                      # optional: interactive + SQL box
# (all of the above except deploy: `bash run_dashboard.sh`)
```

## Gated access at gcburton.org (DECIDED — Caddy, live)

Gareth wants this reachable **only after a login** at gcburton.org, and that is
already in place. **The host serves gcburton.org with Caddy** (not nginx), and
the whole site — including `/cds/` and `/cds/api/*` — sits behind a single Caddy
`basic_auth` block (user `Gareth`). The static `dashboard.html` therefore needs
no auth of its own; deployment is just a file copy into the gated docroot:

```bash
install -d /home/test/www/gcburton.org/cds
install -m 644 public/index.html /home/test/www/gcburton.org/cds/index.html
# served (after login) at https://gcburton.org/cds/
```

`./deploy.sh` does exactly this (plus the Credit Events exports and a `data/docs/`
symlink) and is invoked automatically by the Pi's weekly `cds_refresh.sh`.

> **Do not use `deploy_gcburton_gated.sh` on this host** — it is the older
> *nginx* recipe (writes `/etc/nginx/...`, runs `nginx -t`/`systemctl reload
> nginx`). It is kept only as a reference for an nginx host; this Pi runs Caddy.
> Cloudflare Access and a Streamlit-behind-proxy variant were also considered but
> are **not** what's deployed.

If the live scrape ever 403s from the Pi, the site may require a residential IP
/ real browser — fall back to `--pdf` from a desktop browser network, or use the
existing `playwright`-based `browser_fetch` path in `cds_dc_scraper.py`.
