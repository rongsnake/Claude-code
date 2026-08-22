#!/usr/bin/env python3
"""
Track the ISDA-hosted source documents the automated fetch can't retrieve.

Background
----------
A handful of historical DC documents are hosted on ISDA's own servers
(isda.org / www2.isda.org / assets.isda.org) rather than on
cdsdeterminationscommittees.org. ISDA's edge returns HTTP 403 to our scraper,
so those files can only be obtained by a human clicking the link in a browser.
This module keeps those "manual-click candidates" honest and trackable:

    derive   (re)build data/isda_manual_files.csv from the provenance manifest
             (data/documents.csv) plus an optional seed list of URLs that 403'd
             and so never made it into the manifest. Existing download
             status/hashes are preserved across re-runs.
    list     print the still-pending items as a checklist and (re)write the
             human-facing data/isda_manual_files.md.
    ingest   register a file you downloaded by hand: hash it, copy it into
             data/docs/, best-effort extract text, mark the row done, and append
             a row to data/documents.csv so it flows into the search index.

Nothing here fabricates a determination: every candidate is a real URL already
referenced by the DC data (or one you explicitly seed). Files we have never
managed to fetch carry status=pending and no hash until a human supplies them.

Usage
-----
    python isda_manual.py derive                       # refresh tracker + checklist
    python isda_manual.py list                         # show what's still pending
    python isda_manual.py ingest <path> --url <url>    # register a manual download

The ISDA block status is unaffected by this tool — it only records what humans
manage to fetch by hand. See HANDOFF.md ("ISDA manual-click documents").
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("isda_manual")

DATA_DIR = Path("data")
DOCS_DIR = DATA_DIR / "docs"
TEXT_DIR = DATA_DIR / "doctext"
MANIFEST_CSV = DATA_DIR / "documents.csv"          # provenance manifest (read + append)
TRACK_CSV = DATA_DIR / "isda_manual_files.csv"     # this tool's tracking table
TRACK_MD = DATA_DIR / "isda_manual_files.md"       # human-facing checklist
SEED_TXT = DATA_DIR / "isda_manual_seed.txt"       # URLs that 403'd (never in manifest)

# Tracking-table columns. expected_* come from the last successful fetch (if any)
# and let `ingest` verify a hand-downloaded file is the right one; the bare
# columns (sha256/bytes/local_path/fetched_at) are filled in on ingest.
FIELDS = [
    "status",            # pending | downloaded | unavailable
    "reference_entity",
    "determination_date",
    "committee",
    "doc_kind",
    "doc_title",
    "source_page",       # the DC page the link was found on (where to click)
    "file_url",          # the ISDA URL to fetch by hand (primary key)
    "expected_bytes",    # size from last successful fetch, if known
    "expected_sha256",   # sha256 from last successful fetch, if known
    "local_path",        # filled on ingest
    "sha256",            # filled on ingest
    "bytes",             # filled on ingest
    "fetched_at",        # filled on ingest
    "notes",
]

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def host(url: str) -> str:
    try:
        return urlparse(str(url)).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return ""


def is_isda(url: str) -> bool:
    h = host(url)
    return h == "isda.org" or h.endswith(".isda.org")


def safe_name(url: str) -> str:
    name = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or "document"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:120] or "document"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# ── derive ────────────────────────────────────────────────────────────────────
def load_seed() -> list[dict]:
    """Parse data/isda_manual_seed.txt: one URL per line, '#'=comment.

    Optional pipe-delimited context after the URL:
        <url> | entity | date | committee | doc_kind | doc_title
    """
    out: list[dict] = []
    if not SEED_TXT.exists():
        return out
    for raw in SEED_TXT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        url = parts[0]
        if not url.lower().startswith("http"):
            log.warning("seed: skipping non-URL line: %s", line[:60])
            continue
        keys = ["file_url", "reference_entity", "determination_date",
                "committee", "doc_kind", "doc_title"]
        out.append({k: (parts[i] if i < len(parts) else "") for i, k in enumerate(keys)})
    return out


def derive_candidates() -> dict[str, dict]:
    """Build {file_url: candidate} from the manifest's ISDA-hosted docs + seed."""
    cand: dict[str, dict] = {}

    def consider(file_url, ctx, exp_bytes="", exp_sha="", man_local="", man_fetched=""):
        url = (file_url or "").strip()
        if not url:
            return
        c = cand.get(url)
        if c is None:
            c = {
                "status": "pending",
                "reference_entity": ctx.get("reference_entity", ""),
                "determination_date": ctx.get("determination_date", ""),
                "committee": ctx.get("committee", ""),
                "doc_kind": ctx.get("doc_kind", ""),
                "doc_title": ctx.get("doc_title", ""),
                "source_page": ctx.get("source_page", ""),
                "file_url": url,
                "expected_bytes": "",
                "expected_sha256": "",
                "local_path": "",
                "sha256": "",
                "bytes": "",
                "fetched_at": "",
                "notes": "",
                "_man_local": "",
                "_man_fetched": "",
            }
            cand[url] = c
        # Keep the earliest-dated context (most "historical" provenance).
        d_new, d_old = ctx.get("determination_date") or "", c["determination_date"] or ""
        if d_new and (not d_old or d_new < d_old):
            for k in ("reference_entity", "determination_date", "committee",
                      "doc_kind", "doc_title", "source_page"):
                if ctx.get(k):
                    c[k] = ctx[k]
        # expected_* = richest signal seen from a successful fetch.
        if _int(exp_bytes) > _int(c["expected_bytes"]):
            c["expected_bytes"] = str(_int(exp_bytes))
        if exp_sha and not c["expected_sha256"]:
            c["expected_sha256"] = exp_sha
        if man_local and not c["_man_local"]:
            c["_man_local"] = man_local
        if man_fetched and not c["_man_fetched"]:
            c["_man_fetched"] = man_fetched

    for r in read_csv(MANIFEST_CSV):
        if not is_isda(r.get("file_url", "")):
            continue
        consider(
            r.get("file_url"),
            {
                "reference_entity": r.get("reference_entity", ""),
                "determination_date": r.get("determination_date", ""),
                "committee": r.get("committee", ""),
                "doc_kind": r.get("doc_kind", ""),
                "doc_title": r.get("doc_title", ""),
                "source_page": r.get("source_page", ""),
            },
            exp_bytes=r.get("bytes", ""),
            exp_sha=r.get("sha256", ""),
            man_local=r.get("local_path", ""),
            man_fetched=r.get("fetched_at", ""),
        )

    for s in load_seed():
        consider(s.get("file_url"), s)
        cand[s["file_url"]]["notes"] = (cand[s["file_url"]]["notes"]
                                        or "seeded (403 — not in manifest)")

    return cand


def dedupe_by_content(rows: list[dict]) -> list[dict]:
    """Collapse rows that share an expected_sha256 (same file, multiple URL forms,
    e.g. a WP permalink with/without a trailing slash). Keep the canonical URL and
    record the alternates in notes so the human clicks once, not N times."""
    groups: dict[str, list[dict]] = {}
    out: list[dict] = []
    for r in rows:
        sha = r.get("expected_sha256") or ""
        if sha:
            groups.setdefault(sha, []).append(r)
        else:
            out.append(r)
    for grp in groups.values():
        if len(grp) == 1:
            out.append(grp[0])
            continue
        grp.sort(key=lambda r: (r["file_url"].endswith("/"), len(r["file_url"])))
        keep, alts = grp[0], [g["file_url"] for g in grp[1:]]
        note = "same file as: " + "; ".join(alts)
        # Drop any note this function added on a previous run before re-adding it,
        # so repeated `derive` calls stay idempotent instead of accreting copies.
        kept_notes = [n for n in (keep.get("notes") or "").split(" | ")
                      if n and not n.startswith("same file as:")]
        keep["notes"] = " | ".join(kept_notes + [note])
        out.append(keep)
    return out


def cmd_derive(_args) -> int:
    cand = derive_candidates()
    if not cand:
        log.warning("No ISDA-hosted documents found in %s and no seed file. "
                    "Nothing to track.", MANIFEST_CSV)

    # Preserve human-entered status/hashes from a prior tracking file.
    prior = {r["file_url"]: r for r in read_csv(TRACK_CSV) if r.get("file_url")}

    rows: list[dict] = []
    for url, c in cand.items():
        p = prior.get(url)
        if p and p.get("status") == "downloaded" and p.get("sha256"):
            # A human already registered this one — keep their record.
            for k in ("status", "local_path", "sha256", "bytes", "fetched_at", "notes"):
                c[k] = p.get(k, c.get(k, ""))
        elif c["_man_local"] and Path(c["_man_local"]).is_file():
            # We already hold the bytes from a past successful fetch on this host.
            c["status"] = "downloaded"
            c["local_path"] = c["_man_local"]
            c["sha256"] = c["expected_sha256"]
            c["bytes"] = c["expected_bytes"]
            c["fetched_at"] = c["_man_fetched"]
        elif p:
            c["notes"] = c["notes"] or p.get("notes", "")
        c.pop("_man_local", None)
        c.pop("_man_fetched", None)
        rows.append(c)

    rows = dedupe_by_content(rows)
    rows.sort(key=lambda r: (r["determination_date"] or "9999", r["reference_entity"] or ""))
    write_csv(TRACK_CSV, rows, FIELDS)
    write_checklist(rows)

    pend = sum(1 for r in rows if r["status"] != "downloaded")
    done = len(rows) - pend
    log.info("Tracked %d ISDA document(s): %d pending, %d held. → %s / %s",
             len(rows), pend, done, TRACK_CSV, TRACK_MD)
    if pend:
        log.info("Run `python isda_manual.py list` for the click-list.")
    return 0


# ── list / checklist ────────────────────────────────────────────────────────--
def write_checklist(rows: list[dict]) -> None:
    pend = [r for r in rows if r["status"] != "downloaded"]
    done = [r for r in rows if r["status"] == "downloaded"]

    def item(r: str) -> str:
        return r

    lines = [
        "# ISDA manual-click documents",
        "",
        "These DC source documents are hosted on ISDA servers "
        "(`isda.org` / `assets.isda.org`) whose edge returns **HTTP 403** to the",
        "scraper, so they must be downloaded by hand and then registered:",
        "",
        "```bash",
        'python isda_manual.py ingest <downloaded-file> --url "<file_url>"',
        "```",
        "",
        f"_Generated by `isda_manual.py` — do not edit by hand._ "
        f"**{len(pend)} pending, {len(done)} held.**",
        "",
        f"## Pending ({len(pend)})",
        "",
    ]
    if not pend:
        lines.append("_None — every known ISDA document has been registered._")
    for r in pend:
        exp = f" · ≈{r['expected_bytes']} B" if r.get("expected_bytes") else ""
        ent = r["reference_entity"] or "(entity?)"
        dt = r["determination_date"] or "(date?)"
        kind = r["doc_kind"] or "document"
        title = r["doc_title"] or ""
        lines += [
            f"- [ ] **{ent}** — {dt} — _{kind}_{exp}",
            f"  - {title}".rstrip(),
            f"  - <{r['file_url']}>",
            f"  - `python isda_manual.py ingest <file> --url \"{r['file_url']}\"`",
        ]
        if r.get("notes"):
            lines.append(f"  - _{r['notes']}_")
    lines += ["", f"## Held ({len(done)})", ""]
    if not done:
        lines.append("_None yet._")
    for r in done:
        ent = r["reference_entity"] or "(entity?)"
        dt = r["determination_date"] or "(date?)"
        lines.append(f"- [x] **{ent}** — {dt} — `{r.get('local_path','')}` "
                     f"(sha {str(r.get('sha256',''))[:8]}…)")
    TRACK_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_list(_args) -> int:
    rows = read_csv(TRACK_CSV)
    if not rows:
        log.info("No tracking table yet — run `python isda_manual.py derive` first.")
        return 0
    write_checklist(rows)
    pend = [r for r in rows if r["status"] != "downloaded"]
    if not pend:
        print("All known ISDA documents are registered. ✔")
        return 0
    print(f"{len(pend)} ISDA document(s) awaiting a manual download:\n")
    for r in pend:
        print(f"  • [{r['determination_date'] or '????-??-??'}] "
              f"{r['reference_entity'] or '(entity?)'} — {r['doc_kind'] or 'document'}")
        print(f"      {r['file_url']}")
        print(f"      ingest: python isda_manual.py ingest <file> --url \"{r['file_url']}\"")
    print(f"\nChecklist written to {TRACK_MD}")
    return 0


# ── ingest ────────────────────────────────────────────────────────────────────
def extract_text(path: Path, content_type: str) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf" or "pdf" in (content_type or ""):
            import pdfplumber  # optional dependency
            parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts).strip()
        if suffix in (".txt", ".csv"):
            return path.read_text(errors="replace").strip()
    except Exception as exc:
        log.debug("text extraction failed for %s: %s", path.name, exc)
    return ""


def append_provenance(row: dict) -> bool:
    """Append one row to data/documents.csv (matching its schema). Idempotent."""
    existing = read_csv(MANIFEST_CSV)
    if existing:
        fields = list(existing[0].keys())
        for r in existing:
            if r.get("sha256") == row.get("sha256") and r.get("file_url") == row.get("file_url"):
                log.info("provenance row already present for sha %s — not duplicating",
                         str(row.get("sha256"))[:8])
                return False
    else:
        fields = ["reference_entity", "determination_date", "committee", "origin",
                  "doc_kind", "doc_title", "source_page", "file_url", "local_path",
                  "content_type", "bytes", "sha256", "fetched_at", "text_chars", "text_path"]
    with MANIFEST_CSV.open("a", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=fields).writerow({k: row.get(k, "") for k in fields})
    return True


def cmd_ingest(args) -> int:
    src = Path(args.path)
    if not src.is_file():
        log.error("No such file: %s", src)
        return 2

    rows = read_csv(TRACK_CSV)
    if not rows:
        log.error("No tracking table — run `python isda_manual.py derive` first.")
        return 2

    # Match the target tracking row by --url, else by filename heuristic.
    target = None
    if args.url:
        for r in rows:
            if r.get("file_url") == args.url:
                target = r
                break
        if target is None:
            log.warning("--url not in tracker; ingesting as an ad-hoc ISDA doc.")
    else:
        stem = src.name.lower()
        guesses = [r for r in rows if r["status"] != "downloaded"
                   and safe_name(r["file_url"]).lower() in stem]
        if len(guesses) == 1:
            target = guesses[0]
            log.info("Matched by filename → %s", target["file_url"])
        else:
            log.error("Could not unambiguously match by filename "
                      "(%d candidates). Pass --url \"<file_url>\".", len(guesses))
            return 2

    body = src.read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    size = len(body)
    url = args.url or (target["file_url"] if target else "")

    # Integrity check against the last successful fetch, if we have one.
    if target and target.get("expected_sha256") and target["expected_sha256"] != sha:
        log.warning("sha256 differs from the expected (last-fetched) value:\n"
                    "  expected %s\n  got      %s\n"
                    "Recording anyway; note added.", target["expected_sha256"], sha)
        target["notes"] = (target.get("notes", "") + " | sha differs from prior fetch").strip(" |")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    name = safe_name(url) if url else re.sub(r"[^A-Za-z0-9._-]", "_", src.name)
    dest = DOCS_DIR / f"{sha[:12]}__{name}"
    dest.write_bytes(body)

    content_type = CONTENT_TYPES.get(src.suffix.lower(), "")
    text_chars, text_path = 0, ""
    if not args.no_text:
        text = extract_text(dest, content_type)
        if text:
            tp = TEXT_DIR / f"{sha[:12]}.txt"
            tp.write_text(text, encoding="utf-8")
            text_chars, text_path = len(text), str(tp)

    fetched = now_iso()
    if target is None:
        target = {k: "" for k in FIELDS}
        target["file_url"] = url
        target["doc_kind"] = "document"
        target["notes"] = "ad-hoc ingest (not previously tracked)"
        rows.append(target)
    target.update(status="downloaded", local_path=str(dest), sha256=sha,
                  bytes=str(size), fetched_at=fetched)

    appended = append_provenance({
        "reference_entity": target.get("reference_entity", ""),
        "determination_date": target.get("determination_date", ""),
        "committee": target.get("committee", ""),
        "origin": "determination",
        "doc_kind": target.get("doc_kind", "document"),
        "doc_title": target.get("doc_title", "") or name,
        "source_page": target.get("source_page", ""),
        "file_url": url,
        "local_path": str(dest),
        "content_type": content_type,
        "bytes": str(size),
        "sha256": sha,
        "fetched_at": fetched,
        "text_chars": str(text_chars),
        "text_path": text_path,
    })

    write_csv(TRACK_CSV, rows, FIELDS)
    write_checklist(rows)
    log.info("✓ Registered %s (%d bytes, sha %s…)", dest.name, size, sha[:8])
    log.info("  tracker updated%s. Rebuild the index to surface it: "
             "python build_index.py", "" if appended else "; provenance already present")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("derive", help="(re)build the tracker from the manifest + seed")
    sub.add_parser("list", help="show pending manual-click documents")
    pi = sub.add_parser("ingest", help="register a hand-downloaded file")
    pi.add_argument("path", help="the file you downloaded by hand")
    pi.add_argument("--url", help="the ISDA file_url it corresponds to")
    pi.add_argument("--no-text", action="store_true", help="skip text extraction")

    args = ap.parse_args(argv)
    cmd = args.cmd or "derive"   # default action
    return {"derive": cmd_derive, "list": cmd_list, "ingest": cmd_ingest}[cmd](args)


if __name__ == "__main__":
    sys.exit(main())
