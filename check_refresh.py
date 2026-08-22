"""
Sanity-gate a freshly-scraped dataset before it is published or committed.

The scrapers are best-effort: `cds_refresh.sh` runs them with `|| true` so a
transient 403, a network blip or a changed selector does not abort the weekly
timer. That resilience has a sharp edge — a *partial* scrape still overwrites
`data/*.csv`, and the pipeline would happily deploy it to the gated site and
push it to git. That is exactly what happened on 2026-06-22:

    determinations 2574 -> 2452   (the 122 `dc-isda` enrichment rows vanished)
    auctions        245 ->   15   (creditfixings yielded 12 instead of 245)
    matched         120 ->    0   (reconciliation fell to 0.0%)

Nothing failed loudly, so the degraded data was committed and served for a week.

This gate compares the working tree against the last known-good baseline (by
default the committed `HEAD`) and exits non-zero when the new data looks like a
collapsed scrape rather than a real change. Run it *after* reconcile/analytics
and *before* build/deploy/commit:

    python check_refresh.py || { git checkout -- data; exit 1; }

Deliberately stdlib-only: this is the check that has to work even when the venv
is half-installed or pandas is missing.

    python check_refresh.py                     # gate the working tree vs HEAD
    python check_refresh.py --baseline 0ec12a4  # compare against a known-good commit
    python check_refresh.py --tolerance 0.35    # allow a bigger legitimate drop
    python check_refresh.py --allow-demo        # permit synthetic-demo rows
"""

from __future__ import annotations

import argparse
import csv
import io
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path("data")

# Files to gate, and the column (if any) whose value counts we track.
TRACKED = (
    (DATA_DIR / "determinations.csv", "source"),
    (DATA_DIR / "auctions.csv", "source"),
    (DATA_DIR / "reconciled.csv", "match_status"),
)

# Below this many baseline rows a table is too small for a percentage drop to
# mean anything (e.g. the 4-row verified seed) — only hard invariants apply.
MIN_BASELINE_ROWS = 20

# Fraction of rows that may disappear before we call it a collapsed scrape.
DEFAULT_TOLERANCE = 0.20


def read_rows(text: str | None) -> list[dict[str, str]]:
    """Parse CSV text into rows; empty/missing content is an empty table."""
    if not text:
        return []
    return list(csv.DictReader(io.StringIO(text)))


def baseline_text(ref: str, path: Path) -> str | None:
    """The committed contents of `path` at `ref`, or None if absent there."""
    try:
        return subprocess.run(
            ["git", "show", f"{ref}:{path.as_posix()}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def counts(rows: list[dict[str, str]], column: str | None) -> dict[str, int]:
    """Value counts for `column`, or {} when the column is absent."""
    if not rows or not column or column not in rows[0]:
        return {}
    tally: dict[str, int] = {}
    for row in rows:
        tally[row.get(column) or ""] = tally.get(row.get(column) or "", 0) + 1
    return dict(sorted(tally.items()))


def describe(before: int, after: int) -> str:
    """Render a row-count delta, e.g. '2574 -> 2452 (-4.7%)'."""
    if before == 0:
        return f"{before} -> {after}"
    pct = (after - before) / before * 100
    return f"{before} -> {after} ({pct:+.1f}%)"


def check(baseline_ref: str, tolerance: float, allow_demo: bool) -> list[str]:
    """Compare working tree against `baseline_ref`; return a list of failures."""
    failures: list[str] = []

    for path, column in TRACKED:
        new = read_rows(path.read_text() if path.exists() else None)
        old = read_rows(baseline_text(baseline_ref, path))

        new_counts, old_counts = counts(new, column), counts(old, column)
        print(f"  {path}: {describe(len(old), len(new))}")
        if old_counts or new_counts:
            print(f"      {column}: {old_counts or '{}'} -> {new_counts or '{}'}")

        # 1. A table that had data must not empty out.
        if old and not new:
            failures.append(f"{path}: had {len(old)} rows, now empty")
            continue

        # 2. Row counts must not collapse beyond the tolerance.
        if len(old) >= MIN_BASELINE_ROWS:
            floor = len(old) * (1 - tolerance)
            if len(new) < floor:
                failures.append(
                    f"{path}: {describe(len(old), len(new))} — below the "
                    f"{tolerance:.0%} drop tolerance (floor {floor:.0f} rows)"
                )

        # 3. Per-source collapse: a source that was substantial must not vanish.
        for value, was in old_counts.items():
            now = new_counts.get(value, 0)
            if was >= MIN_BASELINE_ROWS and now == 0:
                failures.append(
                    f"{path}: {column}='{value}' disappeared entirely ({was} -> 0)"
                )

        # 4. Honesty invariant — synthetic rows must never reach a live refresh.
        if not allow_demo:
            synthetic = sum(1 for r in new if r.get("source") == "synthetic-demo")
            if synthetic:
                failures.append(
                    f"{path}: {synthetic} synthetic-demo rows in a live refresh "
                    "(use --allow-demo if this is deliberately a demo build)"
                )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--baseline",
        default="HEAD",
        help="git ref holding the last known-good data (default: HEAD)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"fraction of rows that may vanish (default: {DEFAULT_TOLERANCE:.0%})",
    )
    parser.add_argument(
        "--allow-demo",
        action="store_true",
        help="permit synthetic-demo rows (for --demo builds)",
    )
    args = parser.parse_args()

    print(f"Checking working tree against {args.baseline}:")
    failures = check(args.baseline, args.tolerance, args.allow_demo)

    if failures:
        print("\nREFRESH REJECTED — this looks like a partial scrape, not real change:")
        for failure in failures:
            print(f"  ✗ {failure}")
        print(
            "\nThe previous data is still committed. To discard this run:\n"
            "    git checkout -- data\n"
            "Then investigate the scrape (403? changed selectors?) and re-run.\n"
            "If the drop is genuine, re-run with a higher --tolerance."
        )
        return 1

    print("\nRefresh looks sane — no collapsed tables or vanished sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
