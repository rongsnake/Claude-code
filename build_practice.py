#!/usr/bin/env python3
"""Build the standalone Practice page (public/practice/index.html).

`practice/page.html` is the single source of truth for the page: it is a body
fragment, which is exactly what the Claude artifact publisher takes, so the
hosted page at claude.ai and the self-hosted one at gcburton.org stay the same
file. This script wraps that fragment in the document head the artifact
publisher would otherwise supply, so the result opens anywhere — over HTTP, or
straight off the disk as file://.

    python build_practice.py                 # → public/practice/index.html

The contents index (contents.js) is written separately by build_contents.py and
sits beside index.html; the page degrades to setup instructions without it.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date
from pathlib import Path

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="generator" content="build_practice.py {built}">
<style>
  :root{{
    color-scheme: light dark;
    padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }}
  body{{ margin:0; font:14px -apple-system, BlinkMacSystemFont, sans-serif; }}
  img{{ max-width:100%; }}
  [hidden]:not([hidden="until-found"]){{ display:none !important; }}
</style>
</head>
<body>
"""

TAIL = """
</body>
</html>
"""


def build(source: Path, out: Path, contents: Path | None) -> None:
    fragment = source.read_text(encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEAD.format(built=date.today().isoformat()) + fragment + TAIL,
                   encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"→ {out} · {size:.0f} KB")

    if contents and contents.exists() and contents.parent != out.parent:
        shutil.copy2(contents, out.parent / contents.name)
        print(f"→ {out.parent / contents.name}")

    beside = out.parent / "contents.js"
    if beside.exists():
        print(f"  contents index present: {beside.stat().st_size / 1024:.0f} KB")
    else:
        print("  no contents.js yet — run build_contents.py to fill the Contents view")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="practice/page.html")
    ap.add_argument("--output", default="public/practice/index.html")
    ap.add_argument("--contents", default=None,
                    help="optional contents.js to copy beside the page")
    args = ap.parse_args(argv)

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"{source} not found")
    build(source, Path(args.output), Path(args.contents) if args.contents else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
