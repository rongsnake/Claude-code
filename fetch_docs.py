"""
Document downloader + provenance manifest for the CDS DC dashboard.

Makes every data point cross-checkable: for each determination (and each
auction's Auction Settlement Terms / results), this follows the source URL,
discovers the linked source documents on the DC site and on creditfixings.com,
downloads them to ``data/docs/``, computes a SHA-256 of every file, and extracts
the text so the native AI search (``ask.py``) can quote and cite them.

Outputs
-------
    data/docs/<sha256-prefix>__<safe-name>            the raw source files
    data/doctext/<sha256-prefix>.txt                  extracted text (for RAG)
    data/documents.csv / data/documents.json          the provenance manifest

Manifest columns:
    reference_entity, determination_date, committee, doc_kind, doc_title,
    source_page, file_url, local_path, content_type, bytes, sha256,
    fetched_at, text_chars, text_path

Usage
-----
    python fetch_docs.py                 # docs for current rows + their ASTs
    python fetch_docs.py --no-text       # skip PDF text extraction (faster)
    python fetch_docs.py --limit 20      # cap pages crawled (debug)

Run after the scrapers (cds_dc_scraper.py, creditex_scraper.py) so the input
tables exist. Network policy / browser fallback is inherited from
cds_dc_scraper (a real headless Chromium is used when plain requests is blocked).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd

# Reuse the proven HTTP stack (session + 403→browser fallback) from the scraper.
from cds_dc_scraper import BASE_URL, USER_AGENT, REQUEST_TIMEOUT, _session, fetch_text, browser_fetch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_docs")

DATA_DIR = Path("data")
DOCS_DIR = DATA_DIR / "docs"
TEXT_DIR = DATA_DIR / "doctext"
MANIFEST_CSV = DATA_DIR / "documents.csv"
MANIFEST_JSON = DATA_DIR / "documents.json"

DETERMINATIONS_CSV = DATA_DIR / "determinations.csv"
AUCTIONS_CSV = DATA_DIR / "auctions.csv"

# File extensions we treat as downloadable source documents.
DOC_EXT_RE = re.compile(r"\.(pdf|xls|xlsx|csv|docx?|txt)(?:[?#].*)?$", re.I)

# Classify a document by its URL / link text into a stable "kind".
def classify_kind(url: str, link_text: str) -> str:
    hay = f"{url} {link_text}".lower()
    if "auction settlement terms" in hay or "settlement terms" in hay or re.search(r"\bast\b", hay):
        return "auction_settlement_terms"
    if "final list" in hay or "final price" in hay or "results" in hay:
        return "auction_results"
    if "initial market" in hay or "dealer" in hay or "bid" in hay or "offer" in hay:
        return "auction_market_data"
    if "notice" in hay:
        return "notice"
    if "statement" in hay:
        return "statement"
    if "decision" in hay or "determination" in hay or "resolution" in hay:
        return "decision"
    return "document"


def _safe_name(url: str) -> str:
    name = urlparse(url).path.rsplit("/", 1)[-1] or "document"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:120] or "document"


def fetch_bytes(session, url: str) -> tuple[str | None, bytes | None]:
    """Download a binary document. Returns (content_type, body) or (None, None)."""
    import requests

    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT, stream=False,
                         headers={"Accept": "*/*"})
        if r.status_code == 200 and r.content:
            return r.headers.get("Content-Type", ""), r.content
        log.debug("requests %s -> HTTP %s", url, r.status_code)
    except requests.RequestException as exc:
        log.debug("requests failed for %s: %s", url, exc)
    # Bot-protected? Re-fetch the bytes through the headless browser stack.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=USER_AGENT)
                resp = ctx.request.get(url, timeout=45000)
                if resp.ok:
                    return resp.headers.get("content-type", ""), resp.body()
                log.warning("browser_fetch_bytes %s -> HTTP %s", url, resp.status)
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - env dependent
        log.warning("browser_fetch_bytes failed for %s: %s", url, exc)
    return None, None


def discover_links(session, page_url: str) -> list[tuple[str, str]]:
    """Return [(absolute_doc_url, link_text)] for every document linked on a page.

    If ``page_url`` is itself a document, it is returned directly."""
    if DOC_EXT_RE.search(page_url):
        return [(page_url, "")]
    status, body = fetch_text(session, page_url, accept="text/html")
    if not body:
        log.warning("no body for %s (status %s)", page_url, status)
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, "html.parser")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "javascript:", "#")):
            continue
        absu = urljoin(page_url, href)
        if not DOC_EXT_RE.search(absu):
            continue
        if absu in seen:
            continue
        seen.add(absu)
        out.append((absu, a.get_text(" ", strip=True)))
    return out


def extract_text(local_path: Path, content_type: str) -> str:
    """Best-effort text extraction (PDF via pdfplumber, else decode)."""
    suffix = local_path.suffix.lower()
    try:
        if suffix == ".pdf" or "pdf" in (content_type or ""):
            import pdfplumber
            parts = []
            with pdfplumber.open(local_path) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts).strip()
        if suffix in (".txt", ".csv"):
            return local_path.read_text(errors="replace").strip()
    except Exception as exc:
        log.debug("text extraction failed for %s: %s", local_path.name, exc)
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Download DC docs + ASTs, build provenance manifest")
    ap.add_argument("--no-text", action="store_true", help="skip PDF text extraction")
    ap.add_argument("--limit", type=int, default=0, help="cap number of source pages crawled")
    args = ap.parse_args()

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    session = _session()

    # Build the work list: (reference_entity, date, committee, source_page, origin)
    pages: list[dict] = []
    if DETERMINATIONS_CSV.exists():
        det = pd.read_csv(DETERMINATIONS_CSV)
        for _, row in det.iterrows():
            url = str(row.get("url") or "").strip()
            if url and url.startswith("http"):
                pages.append({
                    "reference_entity": row.get("reference_entity"),
                    "determination_date": row.get("date"),
                    "committee": row.get("committee"),
                    "source_page": url,
                    "origin": "determination",
                })
    if AUCTIONS_CSV.exists():
        auc = pd.read_csv(AUCTIONS_CSV)
        for _, row in auc.iterrows():
            url = str(row.get("url") or "").strip()
            if url and url.startswith("http"):
                pages.append({
                    "reference_entity": row.get("reference_entity"),
                    "determination_date": row.get("auction_date"),
                    "committee": None,
                    "source_page": url,
                    "origin": "auction",  # these pages carry the ASTs / results
                })

    # Dedupe source pages (many auctions share one ticker page).
    seen_pages: dict[str, dict] = {}
    for p in pages:
        seen_pages.setdefault(p["source_page"], p)
    work = list(seen_pages.values())
    if args.limit:
        work = work[: args.limit]
    log.info("Crawling %d unique source pages for linked documents…", len(work))

    # Download every discovered document once (dedupe by file URL), keeping the
    # richest provenance context we saw it under.
    manifest: list[dict] = []
    downloaded: dict[str, str] = {}   # file_url -> local_path
    sha_by_path: dict[str, str] = {}

    for i, ctx in enumerate(work, 1):
        links = discover_links(session, ctx["source_page"])
        if not links:
            continue
        log.info("[%d/%d] %s → %d doc link(s)", i, len(work), ctx["source_page"], len(links))
        for file_url, link_text in links:
            if file_url in downloaded:
                # Already fetched under another row; still record this provenance.
                local_path = downloaded[file_url]
                sha = sha_by_path.get(local_path, "")
                content_type = ""
                size = Path(local_path).stat().st_size if Path(local_path).exists() else 0
                text_chars, text_path = _existing_text(sha)
            else:
                content_type, body = fetch_bytes(session, file_url)
                if not body:
                    log.warning("  ✗ could not download %s", file_url)
                    continue
                sha = hashlib.sha256(body).hexdigest()
                local_path_p = DOCS_DIR / f"{sha[:12]}__{_safe_name(file_url)}"
                local_path_p.write_bytes(body)
                local_path = str(local_path_p)
                size = len(body)
                downloaded[file_url] = local_path
                sha_by_path[local_path] = sha
                text_chars, text_path = 0, ""
                if not args.no_text:
                    text = extract_text(local_path_p, content_type)
                    if text:
                        tp = TEXT_DIR / f"{sha[:12]}.txt"
                        tp.write_text(text)
                        text_chars, text_path = len(text), str(tp)
                log.info("  ✓ %s (%d bytes, sha %s…)", Path(local_path).name, size, sha[:8])

            manifest.append({
                "reference_entity": ctx["reference_entity"],
                "determination_date": ctx["determination_date"],
                "committee": ctx["committee"],
                "origin": ctx["origin"],
                "doc_kind": classify_kind(file_url, link_text),
                "doc_title": link_text or Path(local_path).name,
                "source_page": ctx["source_page"],
                "file_url": file_url,
                "local_path": local_path,
                "content_type": content_type,
                "bytes": size,
                "sha256": sha,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "text_chars": text_chars,
                "text_path": text_path,
            })

    df = pd.DataFrame(manifest)
    df.to_csv(MANIFEST_CSV, index=False)
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2, default=str))
    n_files = len(downloaded)
    n_bytes = sum(sha_by_path and Path(p).stat().st_size for p in downloaded.values()) if downloaded else 0
    kinds = df["doc_kind"].value_counts().to_dict() if not df.empty else {}
    log.info("Done. %d unique documents downloaded, %d provenance rows. Kinds: %s",
             n_files, len(manifest), kinds)
    log.info("Manifest → %s / %s ; files in %s/", MANIFEST_CSV, MANIFEST_JSON, DOCS_DIR)


def _existing_text(sha: str) -> tuple[int, str]:
    if not sha:
        return 0, ""
    tp = TEXT_DIR / f"{sha[:12]}.txt"
    if tp.exists():
        return len(tp.read_text(errors="replace")), str(tp)
    return 0, ""


if __name__ == "__main__":
    main()
