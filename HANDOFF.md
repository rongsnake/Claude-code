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

## Current state

- ✅ Scraper, analytics, static + Streamlit dashboards built and tested.
- ⚠️ **Live data not refreshed here**: `cdsdeterminationscommittees.org` returns
  403 (bot protection) and this sandbox's egress is allowlisted, so it can't
  reach the site. Committed data is the **6 verified seed references**.
- ⚠️ **Not deployed to gcburton.org**: no hosting creds in this session.

## Next steps (run on the Pi / gcburton.org host — it can reach the DC site)

```bash
bash setup.sh && source .venv/bin/activate
python cds_dc_scraper.py --pdf                  # FULL live refresh (+ parse PDFs)
python analytics.py                             # refresh metrics + tidy export
python build_dashboard.py --output public/index.html
# deploy, e.g.:  rsync -av public/index.html gcburton.org:/var/www/html/
streamlit run dashboard.py                      # optional: interactive + SQL box
```

If the live scrape still 403s from the Pi, the site may require a residential IP
/ real browser — fall back to `--pdf` from a desktop browser network, or wire a
`playwright`-based fetch (TODO).
