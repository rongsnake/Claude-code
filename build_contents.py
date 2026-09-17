#!/usr/bin/env python3
"""Build the contents index for The Practice (public/practice/contents.js).

The page reads ``window.PRACTICE_CONTENTS`` from a ``contents.js`` sitting next
to it. This script writes that file from two kinds of input:

  --docs PATH     a documents.csv provenance manifest (the CDS scraper writes
                  one: reference_entity, doc_kind, file_url, bytes, ...).
  --root SPEC     a folder on this machine to walk, as "strand:label:path".
                  This is how the definitions sets, reports and diagrams that
                  live in the Claude projects get into the index — run it on
                  the machine that actually holds them.

Example (on the Pi or the Mac)::

    python build_contents.py \
      --docs data/documents.csv \
      --root "derivatives:Derivatives law:$HOME/Claude/Derivatives law" \
      --root "capital:Bank capital:$HOME/Claude/Bank capital RWA tracker"

Nothing is invented: a file appears in the index only because it was found on
disk or listed in a manifest.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote

STRANDS = ("derivatives", "restructuring", "capital", "insurance")

# Folder / file name keywords that place a scanned file in a strand, checked
# against the path before falling back to the root's own strand.
STRAND_HINTS = (
    ("restructuring", ("horizon", "thames", "stack", "ardagh", "restructur",
                       "playbook", "norske", "lme", "debtwire")),
    ("capital", ("crr", "bank capital", "rwa", "pillar", "bis-fsb", "leverage",
                 "basel", "credit suisse")),
    ("insurance", ("insur", "irrd", "solvency")),
    ("derivatives", ("fx definitions", "credit definitions", "interest rate",
                     "commodity", "clause library", "isda", "cleary", "gmra",
                     "cds", "firth")),
)

# Extensions worth indexing, mapped to the "kind" shown in the table.
EXT_KIND = {
    ".pdf": "PDF", ".docx": "Word", ".doc": "Word", ".dotx": "Word template",
    ".xlsx": "Excel", ".xls": "Excel", ".csv": "Data", ".json": "Data",
    ".md": "Markdown", ".txt": "Text", ".html": "Page", ".htm": "Page",
    ".pptx": "Deck", ".epub": "EPUB", ".m4a": "Audio", ".mp3": "Audio",
    ".svg": "Diagram", ".png": "Image", ".jpg": "Image", ".jpeg": "Image",
    ".mmd": "Diagram",
}

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache",
             ".DS_Store", ".ipynb_checkpoints", "site-packages"}

# 12-char hash prefixes the doc fetcher puts in front of local filenames.
def clean_title(name: str) -> str:
    name = unquote(name)
    if "__" in name:
        head, rest = name.split("__", 1)
        if len(head) >= 8 and all(c in "0123456789abcdef" for c in head.lower()):
            name = rest
    return name.replace("_", " ").strip()


def pretty_kind(raw: str) -> str:
    raw = (raw or "document").replace("_", " ").strip()
    return raw[:1].upper() + raw[1:]


def strand_for(path_text: str, default: str) -> str:
    low = path_text.lower()
    for strand, words in STRAND_HINTS:
        if any(w in low for w in words):
            return strand
    return default


class Index:
    """Collects rows and interns the repeated strings into dictionaries."""

    def __init__(self) -> None:
        self.dict: dict[str, list[str]] = {k: [] for k in
                                           ("kind", "entity", "ext", "src", "strand", "base")}
        self._seen: dict[str, dict[str, int]] = {k: {} for k in self.dict}
        self.rows: list[list] = []
        self.keys: set[str] = set()

    def intern(self, field: str, value: str) -> int:
        value = value or ""
        table = self._seen[field]
        if value not in table:
            table[value] = len(self.dict[field])
            self.dict[field].append(value)
        return table[value]

    def add(self, *, title, kind, entity, when, size, ext, source, strand, url, key):
        if key in self.keys:
            return False
        self.keys.add(key)
        if url:
            head, _, tail = url.rpartition("/")
            base_i, rest = self.intern("base", head + "/"), tail
        else:
            base_i, rest = -1, ""
        self.rows.append([
            title,
            self.intern("kind", kind),
            self.intern("entity", entity),
            when or "",
            int(size or 0),
            self.intern("ext", ext),
            self.intern("src", source),
            self.intern("strand", strand),
            base_i,
            rest,
        ])
        return True


def from_documents_csv(index: Index, path: Path, label: str, strand: str) -> int:
    added = 0
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            url = (row.get("file_url") or "").strip()
            local = (row.get("local_path") or "").strip()
            key = url or local
            if not key:
                continue
            name = os.path.basename(local or url)
            ext = os.path.splitext(name)[1].lower()
            added += index.add(
                title=clean_title(name) or key,
                kind=pretty_kind(row.get("doc_kind")),
                entity=(row.get("reference_entity") or "").strip(),
                when=(row.get("determination_date") or "").strip(),
                size=row.get("bytes") or 0,
                ext=EXT_KIND.get(ext, ext.lstrip(".").upper() or "File"),
                source=label,
                strand=strand,
                url=url,
                key=key,
            )
    return added


def from_root(index: Index, root: Path, label: str, strand: str) -> int:
    added = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in EXT_KIND:
                continue
            full = Path(dirpath) / name
            try:
                stat = full.stat()
            except OSError:
                continue
            rel = full.relative_to(root)
            folder = str(rel.parent) if str(rel.parent) != "." else label
            added += index.add(
                title=clean_title(name),
                kind=EXT_KIND[ext],
                entity=folder,
                when=date.fromtimestamp(stat.st_mtime).isoformat(),
                size=stat.st_size,
                ext=EXT_KIND[ext],
                source=label,
                strand=strand_for(str(rel), strand),
                url="",
                key=str(full),
            )
    return added


def parse_root(spec: str) -> tuple[str, str, str]:
    parts = spec.split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            'expected "strand:label:path", e.g. "capital:Bank capital:/Users/g/Claude/Bank capital"')
    strand, label, path = (p.strip() for p in parts)
    if strand not in STRANDS:
        raise argparse.ArgumentTypeError(f"strand must be one of {', '.join(STRANDS)}")
    return strand, label, os.path.expanduser(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", action="append", default=[],
                    help="a documents.csv manifest (repeatable)")
    ap.add_argument("--docs-label", default="DC determinations",
                    help="collection name for --docs rows")
    ap.add_argument("--docs-strand", default="derivatives", choices=STRANDS)
    ap.add_argument("--root", action="append", default=[], type=parse_root, metavar="SPEC",
                    help='folder to walk, as "strand:label:path" (repeatable)')
    ap.add_argument("--out", default="public/practice/contents.js")
    args = ap.parse_args(argv)

    index = Index()
    sources: list[str] = []

    for docs in args.docs:
        path = Path(docs)
        if not path.exists():
            print(f"  ! {path} not found — skipped", file=sys.stderr)
            continue
        n = from_documents_csv(index, path, args.docs_label, args.docs_strand)
        sources.append(f"{args.docs_label} ({n:,})")
        print(f"  · {path}: {n:,} documents")

    for strand, label, root in args.root:
        rp = Path(root)
        if not rp.is_dir():
            print(f"  ! {root} not found — skipped", file=sys.stderr)
            continue
        n = from_root(index, rp, label, strand)
        sources.append(f"{label} ({n:,})")
        print(f"  · {root}: {n:,} files")

    if not index.rows:
        print("Nothing indexed — pass --docs and/or --root.", file=sys.stderr)
        return 1

    payload = {
        "generated": datetime.now().strftime("%d %B %Y"),
        "sources": sources,
        "dict": index.dict,
        "rows": index.rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "window.PRACTICE_CONTENTS = " + json.dumps(payload, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"→ {out} · {len(index.rows):,} files · {out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
