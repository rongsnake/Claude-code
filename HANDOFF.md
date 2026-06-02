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
- **Action still needed:** the Caddy reverse-proxy block for `/cds/api/*` (see the prepared
  `/tmp/Caddyfile.new`) must be applied with sudo + `systemctl reload caddy` — this was
  deliberately left for explicit approval as it edits the live production Caddyfile.

## Current state

- ✅ DC scraper, **Creditex auction scraper**, **reconciliation**, analytics, and
  static + Streamlit dashboards built and tested (recovery / days-to-auction).
- ⚠️ **Live data not refreshed here**: both `cdsdeterminationscommittees.org` and
  `creditfixings.com` return 403 (bot protection) and this sandbox's egress is
  allowlisted, so neither is reachable. Committed data is the verified seed
  (6 determinations + 3 auctions; Hertz & Ardagh reconciled with real recoveries).
- ⚠️ **Not deployed to gcburton.org**: no hosting creds in this session.
- 📌 **Requirement (Gareth):** the dashboard must be **accessible behind a login
  at gcburton.org** — not public. Deploy gated, not to an open `/var/www/html`.

## Next steps (run on the Pi / gcburton.org host — it can reach the DC site)

```bash
bash setup.sh && source .venv/bin/activate
python cds_dc_scraper.py --pdf                  # FULL live DC refresh (+ parse PDFs)
python creditex_scraper.py                      # live Creditex auction scrape
python reconcile.py                             # join auctions ↔ determinations
python analytics.py                             # refresh metrics + tidy export
python build_dashboard.py --output public/index.html
# deploy behind a login (see "Gated access" below — do NOT deploy public)
streamlit run dashboard.py                      # optional: interactive + SQL box
# (all of the above except deploy: `bash run_dashboard.sh`)
```

## Gated access at gcburton.org (required)

Gareth wants this reachable **only after a login** at gcburton.org. The static
`dashboard.html` has no auth of its own, so put the gate in front of it. Pick one:

- **nginx HTTP Basic auth (simplest):** serve `public/` from an auth-protected
  location and rsync the build to it:
  ```nginx
  location /cds/ {
      auth_basic           "CDS dashboard";
      auth_basic_user_file /etc/nginx/.htpasswd;   # htpasswd -c … <user>
      root /var/www/gated;                          # file at /var/www/gated/cds/index.html
  }
  ```
  `rsync -av public/index.html gcburton.org:/var/www/gated/cds/index.html`
- **Cloudflare Access (SSO, no server config):** front gcburton.org with
  Cloudflare, add an Access policy on `/cds/*` (email OTP or Google). Best if the
  site is already on Cloudflare.
- **Streamlit instead of static:** run `dashboard.py` behind the same nginx
  Basic-auth `location` (reverse-proxy to the Streamlit port) for the live SQL box.

Deploy creds live on the Pi / host, not in this session — run the chosen option there.

If the live scrape still 403s from the Pi, the site may require a residential IP
/ real browser — fall back to `--pdf` from a desktop browser network, or wire a
`playwright`-based fetch (TODO).
