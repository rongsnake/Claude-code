"""
Fact-check The Long Ledger's history against sources, on a hard dollar budget.

Every dated, named or quoted claim in the game's data is checked by Claude with
web search: the scripted events, the deck cards' real precedents, the rival
houses' founding and fates, the innovations' dates, the cities' opening and
first-contact years, the courts' life spans, the eras. Game mechanics (yields,
sizes, odds, effects) are STYLISED dials and are not checked.

It reads the data from a git ref (default: the newest game branch), so it runs
from any checkout of the repo. It writes, under banksim/saga/factcheck/:

    results.jsonl   one verdict per record per pass, with sources (resumable)
    spend.json      running cost, by pass, priced from each response's usage
    report.md       the findings, worst first

Nothing in the game is changed. Applying the corrections is a separate,
reviewed step.

Run (needs `pip install anthropic`; the key is read from LEDGER_API_KEY,
ANTHROPIC_API_KEY or --key-file, and is never printed):

    python3 -m banksim.saga.tools.factcheck --ping            # one tiny call
    python3 -m banksim.saga.tools.factcheck --dry-run         # list the records, no calls
    python3 -m banksim.saga.tools.factcheck --budget 76       # spend up to $76, then stop

The budget is a hard ceiling. Before each request the script reserves the
largest cost any record has needed so far, and starts no request that could
cross the ceiling. Pass 1 checks every record (most consequential first); pass 2
spends what is left re-checking every record pass 1 found wrong, doubtful or
unverifiable, with more searches and more effort.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

def _root() -> Path:
    """The repository the script is run from (so it also works as a copy outside the repo)."""
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if r.returncode == 0 and (Path(r.stdout.strip()) / "banksim").is_dir():
        return Path(r.stdout.strip())
    return Path(__file__).resolve().parents[3]


ROOT = _root()
OUT = ROOT / "banksim" / "saga" / "factcheck"
DEFAULT_REF = "origin/claude/ledger-art-music"
DEFAULT_MODEL = "claude-opus-5-5"
PING_MODEL = "claude-haiku-5-5"

#: $ per million tokens: input, output, cache write (5 min), cache read; and $ per web search.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
    "claude-fable-5-1": (10.00, 50.00, 12.50, 0.25),
}
#: Any model not in the table (a refusal fallback, say) is priced at the dearest rate.
DEAREST = max(PRICES.values(), key=lambda p: p[1])
SEARCH_PRICE = 0.01

SYSTEM = """You are a careful historian of banking and finance checking the historical content of a strategy game, The Long Ledger. The game's banking house is fictional; everything else it states as history must be true. Each record you receive is one piece of the game's data.

Check every factual claim in the record that a historian could verify: dates and years, names of people, firms, places and rulers, sums of money, who did what to whom, the sequence of events, and whether any cited source exists and says roughly what is attributed to it. Ignore game mechanics (sizes, yields, odds, effects, weights, turns): those are deliberate stylised dials, not claims.

Use web search to verify. Prefer scholarly and primary sources (academic books and articles, central bank and official histories, ISDA, BIS, FSB, national archives) over encyclopedias, and encyclopedias over blogs. Where sources disagree, say so and give the better-supported reading. Do not invent sources: cite only pages you actually found.

When you are done, end your reply with exactly one JSON object in a ```json fenced block, with these keys:
- "verdict": "confirmed" (every checkable claim holds), "minor_issues" (small slips: a year off by one, a name variant, a figure rounded misleadingly), "incorrect" (a claim is wrong in a way a knowledgeable player would notice), or "unverifiable" (you could not find sources either way).
- "issues": a list of objects with "field" (which field of the record), "claim" (what it says), "finding" (what the sources say), and "suggested" (replacement wording, in the record's own style, or "" if none is needed). Empty if confirmed.
- "sources": a list of objects with "title" and "url" for the pages you relied on.
- "notes": one or two sentences for the game's author, or "".
"""

RECHECK = """This record was checked once before. The first check's verdict and findings are below. Check them independently: confirm the record or the first check, whichever the sources support, and look harder for anything the first check could not verify. Treat the first check as a claim to test, not as evidence."""


# --------------------------------------------------------------------------- loading the records

def git_show(ref: str, path: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def load_module(ref: str, name: str) -> dict:
    src = git_show(ref, f"banksim/saga/{name}.py")
    if src is None:
        return {}
    ns: dict = {}
    exec(compile(src, f"{ref}:{name}.py", "exec"), ns)  # the data modules are plain literals
    return ns


def pick(d: dict, keys) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] not in (None, "", [], {})}


def records(ref: str) -> list[dict]:
    """Every checkable record, most consequential first: the scripted events, the
    rivals, the innovations, the cities, courts and eras, then the deck cards'
    precedents (the most numerous, and footnotes rather than the spine)."""
    out: list[dict] = []
    ev = load_module(ref, "events").get("EVENTS", [])
    for e in ev:
        if e.get("provenance") != "HISTORICAL":
            continue
        out.append({"id": f"event:{e['id']}", "kind": "event",
                    "record": pick(e, ["year", "title", "text", "source", "provenance"])})
    for r in load_module(ref, "rivals").get("RIVALS", []):
        out.append({"id": f"rival:{r['id']}", "kind": "rival",
                    "record": pick(r, ["name", "home", "founded", "text", "fates", "source", "provenance"])})
    for t in load_module(ref, "techs").get("TECHS", []):
        out.append({"id": f"tech:{t['id']}", "kind": "innovation",
                    "record": pick(t, ["name", "available", "requires", "text", "source", "provenance"])})
    cities = load_module(ref, "cities")
    known = load_module(ref, "geo").get("KNOWN", {})
    for c in cities.get("CITIES", []):
        rec = pick(c, ["name", "region", "sovereign", "opens", "blurb"])
        if c["id"] in known:
            rec["first_reached_by_europeans"] = known[c["id"]]
        out.append({"id": f"city:{c['id']}", "kind": "city", "record": rec})
    for sid, s in cities.get("SOVEREIGNS", {}).items():
        if "from" in s or "until" in s:
            out.append({"id": f"court:{sid}", "kind": "court",
                        "record": pick(s, ["name", "title", "seat", "from", "until"])})
    for e in load_module(ref, "eras").get("ERAS", []):
        out.append({"id": f"era:{e['id']}", "kind": "era",
                    "record": pick(e, ["name", "subtitle", "start", "end", "centre", "intro", "source"])})
    deck_files = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "--name-only", f"{ref}:banksim/saga/deck"],
                                capture_output=True, text=True).stdout.split()
    for f in sorted(deck_files):
        if not f.startswith("deck-") or not f.endswith(".json"):
            continue
        d = json.loads(git_show(ref, f"banksim/saga/deck/{f}") or "{}")
        for c in d.get("cards", []):
            if not c.get("precedent"):
                continue
            out.append({"id": f"card:{c['id']}", "kind": "deck card",
                        "record": dict(era=d.get("era"), **pick(c, ["title", "text", "window", "precedent", "source"]))})
    return out


# --------------------------------------------------------------------------- spending

class Budget:
    """A hard ceiling: a request starts only if its reserve fits under it."""

    def __init__(self, ceiling: float, spent: float):
        self.ceiling, self.spent, self.reserved = ceiling, spent, 0.0
        self.worst = 0.60  # $ reserved per record until a real record shows what one costs
        self.lock = threading.Lock()

    def reserve(self, factor: float = 1.0) -> float | None:
        with self.lock:
            amt = self.worst * factor
            if self.spent + self.reserved + amt > self.ceiling:
                return None
            self.reserved += amt
            return amt

    def settle(self, reserved: float, actual: float, factor: float = 1.0) -> None:
        with self.lock:
            self.reserved -= reserved
            self.spent += actual
            if actual / factor > self.worst:
                self.worst = actual / factor


def cost_of(resp) -> float:
    u = resp.usage
    p = PRICES.get(getattr(resp, "model", ""), DEAREST)
    toks = ((u.input_tokens or 0) * p[0] + (u.output_tokens or 0) * p[1]
            + (getattr(u, "cache_creation_input_tokens", 0) or 0) * p[2]
            + (getattr(u, "cache_read_input_tokens", 0) or 0) * p[3]) / 1e6
    stu = getattr(u, "server_tool_use", None)
    searches = (getattr(stu, "web_search_requests", 0) or 0) if stu else 0
    return toks + searches * SEARCH_PRICE


# --------------------------------------------------------------------------- one check

def extract_json(text: str) -> dict | None:
    m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    cands = m[::-1] if m else []
    if not cands:
        # the last balanced {...} in the reply
        depth, start = 0, None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}" and depth:
                depth -= 1
                if depth == 0 and start is not None:
                    cands.insert(0, text[start:i + 1])
    for c in cands:
        try:
            v = json.loads(c)
            if isinstance(v, dict) and "verdict" in v:
                return v
        except json.JSONDecodeError:
            continue
    return None


def check(client, args, rec: dict, pass_no: int, prior: dict | None) -> tuple[dict, float]:
    body = (f"Record type: {rec['kind']}\nRecord id: {rec['id']}\n\n```json\n"
            f"{json.dumps(rec['record'], ensure_ascii=False, indent=1)}\n```")
    if prior:
        body = (RECHECK + f"\n\nFirst check:\n```json\n{json.dumps(prior, ensure_ascii=False, indent=1)}\n```\n\n" + body)
    messages = [{"role": "user", "content": body}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": args.searches * (2 if pass_no == 2 else 1)}]
    kw = dict(model=args.model, max_tokens=16000, system=SYSTEM, tools=tools,
              output_config={"effort": "high" if pass_no == 2 else args.effort})
    if args.fallback:
        kw["betas"] = ["server-side-fallback-2026-07-01"]
        kw["extra_body"] = {"fallbacks": "default"}
    spent, resp = 0.0, None
    for _ in range(6):  # a server-side search loop can pause; resume it a few times at most
        call = client.beta.messages.create if args.fallback else client.messages.create
        resp = call(messages=messages, **kw)
        spent += cost_of(resp)
        if resp.stop_reason != "pause_turn":
            break
        messages = messages[:1] + [{"role": "assistant", "content": resp.content}]
    text = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    if resp.stop_reason == "refusal":
        verdict = {"verdict": "refused", "issues": [], "sources": [], "notes": "The model declined this record."}
    else:
        verdict = extract_json(text) or {"verdict": "parse_error", "issues": [], "sources": [],
                                          "notes": "No JSON verdict in the reply.", "raw": text[-4000:]}
    verdict.update({"id": rec["id"], "kind": rec["kind"], "pass": pass_no, "model": getattr(resp, "model", args.model),
                    "cost": round(spent, 4), "record": rec["record"]})
    return verdict, spent


# --------------------------------------------------------------------------- the run

def load_results() -> dict:
    done = {}
    f = OUT / "results.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[(r["pass"], r["id"])] = r
    return done


def save_spend(budget: Budget, by_pass: dict) -> None:
    (OUT / "spend.json").write_text(json.dumps({"spent": round(budget.spent, 4), "ceiling": budget.ceiling,
                                                "by_pass": {k: round(v, 4) for k, v in by_pass.items()},
                                                "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1))


def run_pass(client, args, budget, recs, pass_no, done, by_pass, prior_of=None) -> int:
    todo = [r for r in recs if (pass_no, r["id"]) not in done]
    lock = threading.Lock()
    n_done = 0
    factor = 2.0 if pass_no == 2 else 1.0

    def work(rec):
        reserved = budget.reserve(factor)
        if reserved is None:
            return None
        try:
            v, spent = check(client, args, rec, pass_no, prior_of(rec) if prior_of else None)
        except Exception as e:  # noqa: BLE001 — record the failure and keep going
            budget.settle(reserved, 0.0, factor)
            return {"id": rec["id"], "error": f"{type(e).__name__}: {e}"}
        budget.settle(reserved, spent, factor)
        with lock:
            by_pass[str(pass_no)] = by_pass.get(str(pass_no), 0.0) + spent
            with open(OUT / "results.jsonl", "a") as f:
                f.write(json.dumps(v, ensure_ascii=False) + "\n")
            done[(pass_no, rec["id"])] = v
            save_spend(budget, by_pass)
        return v

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        it = iter(todo)
        stopped = False
        while True:
            while not stopped and len(futs) < args.workers:
                rec = next(it, None)
                if rec is None:
                    stopped = True
                    break
                if budget.spent + budget.reserved + budget.worst * factor > budget.ceiling:
                    stopped = True
                    print(f"  budget reached: ${budget.spent:.2f} spent of ${budget.ceiling:.2f}; stopping pass {pass_no}")
                    break
                futs[ex.submit(work, rec)] = rec
            if not futs:
                break
            fut = next(as_completed(futs))
            rec = futs.pop(fut)
            v = fut.result()
            if v and "error" in v:
                print(f"  ! {rec['id']}: {v['error']}")
            elif v:
                n_done += 1
                print(f"  [{pass_no}] {v['verdict']:<13} ${v['cost']:.3f}  total ${budget.spent:6.2f}  {rec['id']}")
    return n_done


def report(recs: list[dict], done: dict) -> Path:
    order = {"incorrect": 0, "minor_issues": 1, "unverifiable": 2, "parse_error": 3, "refused": 4, "confirmed": 5}
    final = {}
    for r in recs:
        v = done.get((2, r["id"])) or done.get((1, r["id"]))
        if v:
            final[r["id"]] = v
    counts: dict[str, int] = {}
    for v in final.values():
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    spend = json.loads((OUT / "spend.json").read_text()) if (OUT / "spend.json").exists() else {}
    lines = ["# The Long Ledger: fact-check report", "",
             f"Checked {len(final)} of {len(recs)} records. Spent ${spend.get('spent', 0):.2f}.", "",
             "| Verdict | Records |", "|---|---|"]
    lines += [f"| {k} | {counts[k]} |" for k in sorted(counts, key=lambda k: order.get(k, 9))]
    lines += ["", "Where a record was re-checked, the second check's verdict is shown.", ""]
    for v in sorted(final.values(), key=lambda v: (order.get(v["verdict"], 9), v["id"])):
        if v["verdict"] == "confirmed":
            continue
        lines += [f"## {v['id']} — {v['verdict']}" + (" (re-checked)" if v["pass"] == 2 else ""), ""]
        for i in v.get("issues", []):
            lines.append(f"- **{i.get('field', '')}**: {i.get('claim', '')}")
            lines.append(f"  - Sources say: {i.get('finding', '')}")
            if i.get("suggested"):
                lines.append(f"  - Suggested: {i['suggested']}")
        if v.get("notes"):
            lines += ["", v["notes"]]
        if v.get("sources"):
            lines += [""] + [f"- [{s.get('title') or s.get('url')}]({s.get('url')})" for s in v["sources"] if s.get("url")]
        lines.append("")
    path = OUT / "report.md"
    path.write_text("\n".join(lines))
    return path


def client_from(args):
    import anthropic  # imported here so --dry-run works without the SDK
    key = os.environ.get("LEDGER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if args.key_file:
        key = Path(args.key_file).expanduser().read_text().strip()
    if not key:
        sys.exit("No API key: set LEDGER_API_KEY or ANTHROPIC_API_KEY, or pass --key-file.")
    return anthropic.Anthropic(api_key=key, max_retries=4, timeout=600.0)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ref", default=DEFAULT_REF, help="git ref holding the game data")
    ap.add_argument("--budget", type=float, default=76.0, help="hard ceiling in US dollars")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--searches", type=int, default=4, help="web searches per record in pass 1 (doubled in pass 2)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--key-file")
    ap.add_argument("--no-fallback", dest="fallback", action="store_false",
                    help="don't let a refused request fall back to another model")
    ap.add_argument("--no-recheck", dest="recheck", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ping", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    if args.ping:
        client = client_from(args)
        r = client.messages.create(model=PING_MODEL, max_tokens=16, messages=[{"role": "user", "content": "ping"}])
        print(f"OK  model {r.model}  stop {r.stop_reason}  usage {r.usage.input_tokens} in / {r.usage.output_tokens} out"
              f"  cost ${cost_of(r):.6f}")
        return

    recs = records(args.ref)
    if not recs:
        sys.exit(f"No records found at {args.ref}. Run `git fetch origin` or pass --ref.")
    kinds: dict[str, int] = {}
    for r in recs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"{len(recs)} records from {args.ref}: " + ", ".join(f"{v} {k}" for k, v in kinds.items()))
    done = load_results()
    if args.dry_run or args.report_only:
        if args.report_only:
            print(f"wrote {report(recs, done)}")
        return

    prev = json.loads((OUT / "spend.json").read_text()) if (OUT / "spend.json").exists() else {}
    by_pass = dict(prev.get("by_pass", {}))
    budget = Budget(args.budget, float(prev.get("spent", 0.0)))
    print(f"Budget ${args.budget:.2f}; already spent ${budget.spent:.2f} in earlier runs.")
    client = client_from(args)

    print("Pass 1: every record")
    run_pass(client, args, budget, recs, 1, done, by_pass)
    if args.recheck:
        doubtful = [r for r in recs if (1, r["id"]) in done
                    and done[(1, r["id"])]["verdict"] in ("incorrect", "minor_issues", "unverifiable", "parse_error")]
        print(f"Pass 2: re-checking {len(doubtful)} doubtful records")
        run_pass(client, args, budget, doubtful, 2, done, by_pass,
                 prior_of=lambda r: {k: done[(1, r["id"])].get(k) for k in ("verdict", "issues", "sources", "notes")})
    save_spend(budget, by_pass)
    print(f"Spent ${budget.spent:.2f} of ${args.budget:.2f}. Wrote {report(recs, done)}")


if __name__ == "__main__":
    main()
