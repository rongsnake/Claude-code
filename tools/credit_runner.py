"""
Spend a fixed amount of Claude API credit on improving Gareth's projects, and no more.

Runs on Gareth's Mac. Three jobs, in this order, all drawing on one ledger with
a hard cap:

  1. energy  — a coding agent (Claude Agent SDK) on the Alstin Lodge energy
               dashboard, working on a separate copy of the secrets-free
               snapshot (branch mac/alstin-lodge-energy-src).
  2. lidar   — a coding agent on the home lidar project at Alstin, on a copy.
  3. ledger  — the Long Ledger fact-checker (banksim/saga/tools/factcheck.py),
               which takes whatever is left, up to the cap.

Each agent works only in its own copy, commits to its own local branch, and
writes IMPROVEMENTS.md. Nothing is pushed, deployed or run against live
systems: a pre-tool hook blocks writes outside the copy, reads of secret
files, shell commands other than tests and local git, and anything that
would reach the Powerwall, Octopus, Tesla or the network.

Spending is capped three ways:
  - each agent run has max_budget_usd, and the runner never gives a job more
    than the cap minus what the ledger has already recorded;
  - the fact-checker has its own hard ceiling (the remainder);
  - the account itself: the remaining API credit is promotional, there is no
    purchased credit and auto-reload is off, so when the promotional credit
    runs out requests simply fail. No card is charged.

Costs are the SDK's and the API's own figures, logged in
~/credit-work/ledger.json. The agents' figures are client-side estimates and
can run slightly past a cap, which is why the default cap leaves headroom
below the $78.51 balance.

    python3 credit_runner.py --key-file ~/.anthropic_key --lidar "<path>"   # all three
    python3 credit_runner.py --key-file ~/.anthropic_key --dry-run          # plan only
    python3 credit_runner.py --key-file ~/.anthropic_key --only ledger      # one job

Needs: pip install claude-agent-sdk anthropic ; run from inside the Long Ledger
repo (~/Claude/Projects/Long Ledger/repo), which is a clone of rongsnake/claude-code.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path.home() / "credit-work"
LEDGER = WORK / "ledger.json"
TODAY = dt.date.today().isoformat()
ENERGY_BRANCH = "origin/mac/alstin-lodge-energy-src"
FACTCHECK_REF = "origin/claude/quirky-bell-7hkici"
#: Default dollar shares. The fact-checker takes whatever is left after the agents.
SHARES = {"energy": 20.0, "lidar": 22.0}
DATA_EXT = {".las", ".laz", ".ply", ".pcd", ".e57", ".bin", ".bag", ".db3", ".mcap", ".npy", ".npz",
            ".h5", ".hdf5", ".tif", ".tiff", ".mp4", ".mov", ".zip", ".tar", ".gz"}

# --------------------------------------------------------------------------- the ledger

def load_ledger(cap: float) -> dict:
    if LEDGER.exists():
        led = json.loads(LEDGER.read_text())
        led["cap"] = cap
        return led
    return {"cap": cap, "spent": 0.0, "jobs": {}}


def save_ledger(led: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    led["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    LEDGER.write_text(json.dumps(led, indent=1))


def remaining(led: dict) -> float:
    return max(0.0, led["cap"] - led["spent"])


# --------------------------------------------------------------------------- the guard

SECRET = re.compile(r"(^|/)(\.env[^/]*|.*\.pem|\.pypowerwall[^/]*|config\.ya?ml|\.anthropic_key|"
                    r"\.ssh(/.*)?|\.aws(/.*)?|\.netrc|id_[a-z0-9]+|.*token.*\.json|credentials[^/]*)$", re.I)
#: Shell commands an agent may run: tests, compiling, and local git. Nothing that reaches the network.
SHELL_OK = [
    r"python3? -m (pytest|unittest|py_compile|compileall)\b",
    r"\.venv/bin/python3? -m (pytest|unittest|py_compile|compileall)\b",
    r"pytest\b",
    r"git (status|diff|log|show|add|commit|branch|restore|mv|rm)\b",
    r"ls\b", r"wc\b", r"mkdir\b",
]
SHELL_BAD = re.compile(r"(\bgit\s+(push|pull|fetch|remote|clone|config)\b|\bcurl\b|\bwget\b|\bssh\b|\bscp\b|\brsync\b|"
                       r"\bnc\b|\benv\b|\bprintenv\b|\bexport\b|\bsudo\b|\brm\s+-\w*r|>\s*[~/]|feed\.py|controller\.py|"
                       r"discover\.py|webapp\.py|\bsystemctl\b|\blaunchctl\b|\bcrontab\b|\bpip3?\b|\bbrew\b|\bnpm\b)")
#: Command substitution runs even inside double quotes, so it is refused anywhere in the command.
SHELL_SUBST = re.compile(r"\$\(|`|\$\{?[A-Z_]*KEY")


def guard_decision(tool: str, tool_input: dict, workdir: Path) -> str | None:
    """None to allow, or the reason to deny."""
    workdir = workdir.resolve()

    def inside(p: str) -> bool:
        try:
            return (workdir / p).resolve().is_relative_to(workdir) if not os.path.isabs(p) else \
                Path(p).resolve().is_relative_to(workdir)
        except (OSError, ValueError):
            return False

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        p = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if not inside(p):
            return f"Writes are only allowed inside {workdir}."
        if SECRET.search(p):
            return "Secret-bearing files may not be written."
        return None
    if tool in ("Read", "Grep", "Glob"):
        p = tool_input.get("file_path") or tool_input.get("path") or ""
        if p and not inside(p):
            return f"Reads are only allowed inside {workdir}."
        if p and SECRET.search(p.rstrip("/")):
            return "Secret-bearing files may not be read."
        return None
    if tool == "Bash":
        cmd = tool_input.get("command", "").strip()
        if SHELL_SUBST.search(cmd):
            return "Command substitution and environment variables are not allowed here."
        bare = re.sub(r"'[^']*'|\"[^\"]*\"", "''", cmd)  # judge the command, not the text of a commit message
        if SHELL_BAD.search(bare):
            return "That command is not allowed here: no network, environment, installs, live services or pushes."
        for part in re.split(r"\s*(?:&&|\|\||;|\|)\s*", bare):
            part = re.sub(r"^cd\s+\S+\s*$", "", part).strip()
            if part and not any(re.match(rx, part) for rx in SHELL_OK):
                return f"Only tests, compilation and local git are allowed in the shell, not: {part[:80]}"
        return None
    if tool in ("WebFetch", "WebSearch", "TodoWrite", "Task", "Agent"):
        return None
    return f"The {tool} tool is not enabled for this job."


# --------------------------------------------------------------------------- workspaces

def git(*a, cwd=None, check=True) -> str:
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout.strip()


def repo_root() -> Path:
    root = Path(git("rev-parse", "--show-toplevel"))
    if not (root / ".git").exists():
        raise RuntimeError("Run this from inside the Long Ledger repo.")
    return root


def energy_workspace(repo: Path) -> Path:
    dest = WORK / "energy"
    if not dest.exists():
        git("fetch", "origin", "mac/alstin-lodge-energy-src", cwd=repo)
        git("worktree", "add", "-b", f"credit/energy-{TODAY}", str(dest), ENERGY_BRANCH, cwd=repo)
    return dest / "energy" / "alstin"


def lidar_workspace(src: Path) -> Path:
    dest = WORK / "lidar"
    if dest.exists():
        return dest
    if (src / ".git").exists():
        git("worktree", "add", "-b", f"credit/lidar-{TODAY}", str(dest), "HEAD", cwd=src)
        return dest

    def ignore(d, names):
        out = []
        for n in names:
            p = Path(d) / n
            if n in (".venv", "venv", "node_modules", "__pycache__", ".git") or SECRET.search(n):
                out.append(n)
            elif p.is_file() and (p.suffix.lower() in DATA_EXT or p.stat().st_size > 20_000_000):
                out.append(n)
        return out

    shutil.copytree(src, dest, ignore=ignore)
    git("init", "-q", cwd=dest)
    git("add", "-A", cwd=dest)
    git("-c", "user.name=credit-runner", "-c", "user.email=noreply@localhost", "commit", "-qm", "Snapshot before the agent", cwd=dest)
    return dest


def find_lidar() -> list[Path]:
    base = Path.home() / "Claude" / "Projects"
    if not base.exists():
        return []
    return sorted({p for p in base.rglob("*") if p.is_dir() and "lidar" in p.name.lower()
                   and ".git" not in p.parts and "node_modules" not in p.parts}, key=lambda p: len(p.parts))[:5]


# --------------------------------------------------------------------------- the agents

COMMON = """You are improving one of Gareth's own projects, unattended, on a fixed API budget. Gareth will review your work when he's back; nothing you do goes live until he says so.

How to work:
- Start by reading the README and any notes files (RESUME, NOTES, TODO, HANDOFF, CLAUDE.md) to learn what the project is, what state it is in and what is open.
- Choose the improvements most worth making that you can finish and verify here: bugs, missing or failing tests, fragile code, unclear docs, small features the notes already ask for. Prefer a few complete, tested changes to many half-done ones.
- Verify every change by running the project's tests (python3 -m unittest or pytest). Add tests for what you change.
- Commit each finished improvement with a clear message (git add, git commit). Never push.
- Finish by writing IMPROVEMENTS.md in the project root: what you changed and why, the test results, what you found but did not fix, and anything that needs Gareth (hardware, accounts, decisions). Commit it.

Rules you must keep:
- Work only inside the current directory. Don't read or write secrets (.env, keys, tokens, live config).
- The shell allows only tests, compilation and local git. Don't try to install packages, reach the network from the shell, or run the live services; such commands are blocked.
- Keep the project's existing style and conventions. Don't reformat files you aren't otherwise changing.
"""

ENERGY = """The project: the Alstin Lodge energy controller, a Raspberry Pi service that optimises a Tesla Powerwall against Octopus Energy prices and serves the dashboard at energy.gcburton.org. This is a secrets-free snapshot; the live copy runs on the Pi.
It controls real hardware, so be conservative: never weaken the safety rails in controller.py, keep the dry-run default, and don't change anything that alters what the battery is told to do unless a test proves the change correct. Read RESUME.md and README.md first; the open items there (for example the hot-water diverter's software side, go-live readiness against the Netzero app, the dormant gas and SolarEdge cards) are good candidates if they can be done and tested without hardware or credentials."""

LIDAR = """The project: Gareth's home lidar project at Alstin Lodge. Work out from its files what it does (scanning, point clouds, floor plans or measurements) and where it has got to. Large data files may have been left out of this copy; if you need sample data, make a tiny synthetic one in a test. Don't try to run hardware or capture tools."""


async def run_agent(name: str, workdir: Path, brief: str, budget: float, model: str) -> float:
    from claude_agent_sdk import (ClaudeAgentOptions, HookMatcher, ProcessError, ResultMessage, SystemMessage,
                                  query)

    async def guard(input_data, tool_use_id, context):
        reason = guard_decision(input_data.get("tool_name", ""), input_data.get("tool_input", {}) or {}, workdir)
        if reason:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}
        return {}

    opts = ClaudeAgentOptions(
        model=model,
        cwd=str(workdir),
        max_budget_usd=budget,
        max_turns=400,
        permission_mode="acceptEdits",
        allowed_tools=["Read", "Grep", "Glob", "Edit", "Write", "Bash", "WebSearch", "WebFetch", "TodoWrite"],
        system_prompt={"type": "preset", "preset": "claude_code", "append": COMMON},
        hooks={"PreToolUse": [HookMatcher(hooks=[guard])]},
    )
    cost = 0.0
    log = (WORK / f"{name}.log").open("a")
    print(f"[{name}] agent in {workdir}, budget ${budget:.2f}")
    try:
        async for msg in query(prompt=brief, options=opts):
            if isinstance(msg, SystemMessage) and getattr(msg, "subtype", "") == "init":
                src = (getattr(msg, "data", {}) or {}).get("apiKeySource")
                print(f"[{name}] auth: {src or 'unknown'} (should be the API key, not a claude.ai login)")
            if isinstance(msg, ResultMessage):
                cost = msg.total_cost_usd or 0.0
                print(f"[{name}] finished: {msg.subtype}, ${cost:.2f}")
            log.write(repr(msg)[:4000] + "\n")
    except ProcessError as e:  # includes ResultError, e.g. the budget stop
        print(f"[{name}] stopped: {e}")
        if not cost:
            cost = budget  # no figure reported: count the whole share, to stay on the safe side
    finally:
        log.close()
    return cost


# --------------------------------------------------------------------------- the fact-checker

def run_factcheck(repo: Path, budget: float, key_file: str | None) -> float:
    script = WORK / "factcheck.py"
    script.write_text(git("show", f"{FACTCHECK_REF}:banksim/saga/tools/factcheck.py", cwd=repo))
    spend = repo / "banksim" / "saga" / "factcheck" / "spend.json"
    before = json.loads(spend.read_text())["spent"] if spend.exists() else 0.0
    cmd = [sys.executable, str(script), "--budget", f"{before + budget:.2f}"]
    if key_file:
        cmd += ["--key-file", key_file]
    print(f"[ledger] fact-checker, budget ${budget:.2f}: {' '.join(shlex.quote(c) for c in cmd)}")
    subprocess.run(cmd, cwd=repo)
    after = json.loads(spend.read_text())["spent"] if spend.exists() else before
    return after - before


# --------------------------------------------------------------------------- main

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cap", type=float, default=74.0, help="total dollars for this run, across all jobs")
    ap.add_argument("--key-file", default=str(Path.home() / ".anthropic_key"))
    ap.add_argument("--lidar", help="path to the lidar project on this Mac")
    ap.add_argument("--only", choices=["energy", "lidar", "ledger"], action="append")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    key = Path(args.key_file).expanduser()
    if not args.dry_run:
        if not key.exists():
            sys.exit(f"No key file at {key}.")
        os.environ["ANTHROPIC_API_KEY"] = key.read_text().strip()  # this process and its children only
    repo = repo_root()
    led = load_ledger(args.cap)
    jobs = args.only or ["energy", "lidar", "ledger"]

    lidar_src = Path(args.lidar).expanduser() if args.lidar else None
    if "lidar" in jobs and not lidar_src:
        found = find_lidar()
        if len(found) == 1:
            lidar_src = found[0]
        else:
            print("No --lidar path given" + (f"; candidates: {', '.join(map(str, found))}" if found else
                                             " and none found under ~/Claude/Projects") + ". Skipping lidar.")
            jobs = [j for j in jobs if j != "lidar"]

    print(f"Cap ${led['cap']:.2f}; already spent ${led['spent']:.2f}; jobs: {', '.join(jobs)}")
    if args.dry_run:
        left = remaining(led)
        for j in jobs:
            share = left if j == "ledger" else min(SHARES[j], left)
            print(f"  {j}: up to ${share:.2f}" + (f" on {lidar_src}" if j == "lidar" else ""))
            left -= share
        return

    for j in jobs:
        left = remaining(led)
        if left < 1.0:
            print(f"Cap reached (${led['spent']:.2f} of ${led['cap']:.2f}); stopping.")
            break
        if led["jobs"].get(j, {}).get("done"):
            print(f"[{j}] already done in an earlier run; skipping.")
            continue
        share = left if j == "ledger" else min(SHARES[j], left)
        if j == "energy":
            cost = asyncio.run(run_agent("energy", energy_workspace(repo), ENERGY, share, args.model))
        elif j == "lidar":
            cost = asyncio.run(run_agent("lidar", lidar_workspace(lidar_src), LIDAR, share, args.model))
        else:
            cost = run_factcheck(repo, share, str(key))
        led["spent"] += cost
        led["jobs"][j] = {"spent": round(led["jobs"].get(j, {}).get("spent", 0.0) + cost, 4), "done": True}
        save_ledger(led)
        print(f"Ledger: ${led['spent']:.2f} of ${led['cap']:.2f}")

    print(f"\nDone. Spent ${led['spent']:.2f} of ${led['cap']:.2f} (estimates; the Console's Cost page is the bill).")
    print(f"Agent work is on local branches in {WORK}; each has an IMPROVEMENTS.md. Nothing was pushed.")


if __name__ == "__main__":
    main()
