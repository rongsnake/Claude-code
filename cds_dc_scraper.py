"""
Credit Derivatives Determinations Committees (DC) scraper.

Source: https://www.cdsdeterminationscommittees.org/

The DCs publish their decisions ("determinations") as PDF documents on a
WordPress site. There is no official JSON/CSV feed, so this scraper tries,
in order:

    1. The WordPress REST API   (/wp-json/wp/v2/...)
    2. The XML sitemap          (/sitemap_index.xml, /wp-sitemap.xml)
    3. (optional) Each decision PDF, parsed for region / credit-event / outcome

and normalises everything into a tidy table of determinations.

NETWORK NOTE
------------
The site sits behind bot protection (Cloudflare-style). Run this from an
environment whose outbound network can reach cdsdeterminationscommittees.org
(e.g. your own machine / the gcburton.org host). If the site is unreachable,
the scraper falls back to writing a small seed dataset of verified references
so downstream tooling still has something to render, and tells you clearly
that no live refresh happened.

Usage
-----
    python cds_dc_scraper.py                 # live refresh -> data/determinations.csv
    python cds_dc_scraper.py --pdf           # also download+parse decision PDFs
    python cds_dc_scraper.py --demo          # write synthetic demo data (no network)
    python cds_dc_scraper.py --seed-only     # write only verified reference rows
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cds_dc")

BASE_URL = "https://www.cdsdeterminationscommittees.org"
# ISDA's official auction administrator (creditfixings.com) exposes a JSON index
# of every credit-event auction, each linking back to its DC determination on the
# DC site (field `isdaLink`). It is the most reliable index of recent
# determinations, so we use it to discover real, cleanly-named determinations
# (the DC WordPress site stores its decision PDFs under MD5-hashed filenames,
# which carry no entity/date signal).
CREDITFIXINGS_AUCTIONS_API = "https://www.creditfixings.com/api/auctions"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

OUT_CSV = DATA_DIR / "determinations.csv"
OUT_JSON = DATA_DIR / "determinations.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
POLITE_DELAY = 0.5  # seconds between requests

# ── canonical vocabularies ────────────────────────────────────────────────────
REGIONS = {
    "americas": "Americas",
    "emea": "EMEA",
    "asia-ex-japan": "Asia ex-Japan",
    "asia_ex_japan": "Asia ex-Japan",
    "aej": "Asia ex-Japan",
    "japan": "Japan",
    "australia-new-zealand": "Australia-New Zealand",
    "australia_new_zealand": "Australia-New Zealand",
    "anz": "Australia-New Zealand",
    "all-dcs": "All DCs",
    "alldcs": "All DCs",
}

CREDIT_EVENTS = {
    "bankruptcy": "Bankruptcy",
    "failure to pay": "Failure to Pay",
    "failure-to-pay": "Failure to Pay",
    "restructuring": "Restructuring",
    "governmental intervention": "Governmental Intervention",
    "governmental-intervention": "Governmental Intervention",
    "obligation acceleration": "Obligation Acceleration",
    "repudiation": "Repudiation/Moratorium",
    "moratorium": "Repudiation/Moratorium",
}

DATE_PATTERNS = [
    re.compile(r"(\d{4})[-_/](\d{2})[-_/](\d{2})"),          # 2025-10-21
    re.compile(r"(\d{2})[-_/](\d{2})[-_/](\d{4})"),          # 21-10-2025
]


@dataclass
class Determination:
    date: str | None
    committee: str | None
    reference_entity: str | None
    issue_number: str | None
    credit_event_type: str | None
    decision: str | None
    doc_type: str
    url: str
    source: str
    title: str = ""
    tags: list[str] = field(default_factory=list)
    auction_date: str | None = None
    auction_held: bool = False


# ── verified seed references (real documents found via public search) ──────────
# These are genuine DC documents; used as a fallback when the live site is
# unreachable so the dashboard has real anchor points. Not a complete dataset.
SEED_REFERENCES: list[Determination] = [
    Determination(
        date="2025-10-21",
        committee="EMEA",
        reference_entity="Ardagh Packaging Finance plc",
        issue_number=None,
        credit_event_type=None,
        decision="DC decision published",
        doc_type="decision",
        url=f"{BASE_URL}/documents/2025/10/dc-decision-ardagh-packaging-finance-plc-21-10-2025.pdf/",
        source="reference",
        title="DC Decision - Ardagh Packaging Finance plc",
    ),
    Determination(
        date="2025-07-22",
        committee="All DCs",
        reference_entity=None,
        issue_number=None,
        credit_event_type=None,
        decision="All DCs statement published",
        doc_type="statement",
        url=f"{BASE_URL}/wp-content/files_mf/1753213406AllDCsStatement.pdf",
        source="reference",
        title="All Credit Derivatives Determinations Committees Statement",
    ),
    Determination(
        date="2020-06-22",
        committee="Americas",
        reference_entity="The Hertz Corporation",
        issue_number="2020052502",
        credit_event_type="Bankruptcy",
        decision="Resolution published",
        doc_type="decision",
        url=f"{BASE_URL}/documents/2020/06/americas-dc-statement-issue-number-2020052502-the-hertz-corporation-06-22-2020.pdf/",
        source="reference",
        title="Americas DC Statement - The Hertz Corporation",
    ),
    Determination(
        date="2012-03-20",
        committee="EMEA",
        reference_entity="ERC Ireland Finance Limited",
        issue_number=None,
        credit_event_type="Restructuring",
        decision="Determination published",
        doc_type="decision",
        url=f"{BASE_URL}/docs/EMEA_Determinations_Committee_Decisions_20032012ERC.pdf",
        source="reference",
        title="EMEA Determinations Committee Decisions - ERC Ireland",
    ),
    Determination(
        date="2010-05-07",
        committee="Americas",
        reference_entity="Ambac Assurance Corporation",
        issue_number="0325201001",
        credit_event_type=None,
        decision="Determination published",
        doc_type="decision",
        url=f"{BASE_URL}/docs/050710DeterminationsCommitteeDecision0325201001.pdf",
        source="reference",
        title="Determinations Committee Decision - Ambac",
    ),
    Determination(
        date="2009-12-09",
        committee="EMEA",
        reference_entity="Hellas Telecommunications",
        issue_number=None,
        credit_event_type="Bankruptcy",
        decision="Determination published",
        doc_type="decision",
        url=f"{BASE_URL}/docs/EMEA_Determinations_Committee_Decision_2009091203.pdf",
        source="reference",
        title="EMEA Determinations Committee Decision - Hellas",
    ),
]


# ── helpers ────────────────────────────────────────────────────────────────────
def _classify(text: str, mapping: dict[str, str]) -> str | None:
    low = text.lower()
    for key, val in mapping.items():
        if key in low:
            return val
    return None


def _parse_date(text: str) -> str | None:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        a, b, c = m.groups()
        try:
            if len(a) == 4:  # YYYY-MM-DD
                return date(int(a), int(b), int(c)).isoformat()
            return date(int(c), int(b), int(a)).isoformat()  # DD-MM-YYYY
        except ValueError:
            continue
    return None


def _slug_to_entity(slug: str) -> str | None:
    """Best-effort reference-entity name from a document slug."""
    s = re.sub(r"\.(pdf|html?)/?$", "", slug, flags=re.I)
    s = re.sub(r"\d{2}[-_]\d{2}[-_]\d{4}|\d{4}[-_]\d{2}[-_]\d{2}", "", s)
    for token in ("dc-decision", "dc-statement", "determinations-committee",
                  "determination", "meeting-statement", "americas", "emea",
                  "asia-ex-japan", "japan", "issue-number", "statement",
                  "decision"):
        s = s.replace(token, " ")
    s = re.sub(r"[-_]+", " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s.title() if s and len(s) > 2 else None


def _record_from_url(url: str, source: str) -> Determination:
    slug = url.rstrip("/").split("/")[-1]
    return Determination(
        date=_parse_date(url),
        committee=_classify(url, REGIONS),
        reference_entity=_slug_to_entity(slug),
        issue_number=(re.search(r"issue[-_ ]?number[-_ ]?(\d+)", url, re.I) or [None, None])[1]
        if re.search(r"issue[-_ ]?number", url, re.I) else None,
        credit_event_type=_classify(url, CREDIT_EVENTS),
        decision=None,
        doc_type="statement" if "statement" in url.lower() else "decision",
        url=url,
        source=source,
        title=slug,
    )


# ── live fetchers ──────────────────────────────────────────────────────────────
def _session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


# ── browser fetch fallback ──────────────────────────────────────────────────────
# Some networks (and some sites' bot protection) return 403 to plain `requests`,
# and creditfixings.com is a client-side Angular app whose data only loads via
# JS/XHR. When a plain fetch is blocked or empty, fall back to a real headless
# Chromium via Playwright, which uses a genuine browser network stack/TLS.
_PLAYWRIGHT_OK: bool | None = None


def _playwright_available() -> bool:
    global _PLAYWRIGHT_OK
    if _PLAYWRIGHT_OK is None:
        try:
            import playwright  # noqa: F401
            _PLAYWRIGHT_OK = True
        except ImportError:
            _PLAYWRIGHT_OK = False
            log.warning("playwright not installed; browser fallback disabled "
                        "(pip install playwright && python -m playwright install chromium)")
    return _PLAYWRIGHT_OK


def browser_fetch(url: str, *, timeout_ms: int = 45000) -> str | None:
    """Fetch `url` with a real headless Chromium and return the response body
    (text). Returns None if Playwright is unavailable or the fetch fails."""
    if not _playwright_available():
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=USER_AGENT)
                # APIRequestContext uses the browser's network stack — ideal for
                # JSON/CSV endpoints and for slipping past basic bot protection.
                resp = ctx.request.get(url, timeout=timeout_ms)
                if resp.ok:
                    return resp.text()
                log.warning("browser_fetch %s -> HTTP %s", url, resp.status)
                return None
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("browser_fetch failed for %s: %s", url, exc)
        return None


def fetch_text(session, url: str, *, accept: str = "*/*") -> tuple[int, str | None]:
    """GET `url` via requests; on 403/empty/error, retry with headless browser.
    Returns (status_code, body or None). status_code 0 means transport error."""
    import requests

    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": accept})
        status, body = r.status_code, r.text
    except requests.RequestException as exc:
        log.debug("requests failed for %s: %s", url, exc)
        status, body = 0, None
    if status == 200 and body and body.strip():
        return status, body
    # blocked, empty, or errored -> try a real browser
    log.info("Falling back to headless browser for %s (requests status=%s)", url, status)
    body = browser_fetch(url)
    return (200 if body else status), body


# ── determinations discovery via the official auction index ─────────────────────
_REGION_ALIASES = {"america": "Americas", "americas": "Americas", "us": "Americas",
                   "europe": "EMEA", "emea": "EMEA"}


def _region_to_committee(region: str | None) -> str | None:
    if not region:
        return None
    key = region.strip().lower()
    if key in _REGION_ALIASES:
        return _REGION_ALIASES[key]
    return REGIONS.get(key.replace(" ", "-"), region.strip())


_MONTH_DATE_RE = re.compile(
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+20\d{2}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s*20\d{2}|20\d{2}-\d{2}-\d{2})\b",
    re.I,
)


def enrich_from_dc_page(session, rec: Determination) -> Determination:
    """Fetch the determination's page on the DC site and extract a real
    determination date (earliest dated step, on/before the auction) plus the
    credit-event type. Honest no-op if the page can't be read/parsed."""
    from bs4 import BeautifulSoup
    from datetime import date as _date

    if not rec.url or "cdsdeterminationscommittees.org" not in rec.url:
        return rec
    status, body = fetch_text(session, rec.url, accept="text/html")
    if not body:
        return rec
    try:
        text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
    except Exception:
        return rec

    rec.credit_event_type = rec.credit_event_type or _classify(text, CREDIT_EVENTS)
    issue = re.search(r"Issue Number\s*(\d{6,})", text)
    if issue:
        rec.issue_number = rec.issue_number or issue.group(1)

    # parse every date on the page; the determination precedes its auction
    parsed: list[str] = []
    for tok in _MONTH_DATE_RE.findall(text):
        iso = _to_iso(tok)
        if iso:
            parsed.append(iso)
    if parsed:
        auc = rec.auction_date
        if auc:
            # the credit-event determination precedes its auction, but not by
            # years — older dates on the page are stale references. Take the
            # earliest determination date within ~18 months before the auction.
            from datetime import date as _d
            ay, am, ad = (int(x) for x in auc.split("-"))
            lo = (_d(ay, am, ad) - timedelta(days=548)).isoformat()
            window = sorted(d for d in parsed if lo <= d <= auc)
            if window:
                rec.date = window[0]
            else:
                before = sorted(d for d in parsed if d <= auc)
                rec.date = before[-1] if before else min(parsed)
        else:
            rec.date = min(parsed)
    time.sleep(POLITE_DELAY)
    return rec


def _to_iso(token: str) -> str | None:
    from datetime import datetime
    token = token.strip()
    for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _event_from_slug(url: str) -> str | None:
    return _classify(url.replace("-", " ").replace("_", " "), CREDIT_EVENTS)


def fetch_via_isda_index(session) -> list[Determination]:
    """Discover real, cleanly-named DC determinations from the official ISDA
    auction index (creditfixings /api/auctions). Each entry carries the legal
    entity name, DC region, ticker, and a link (`isdaLink`) to the actual DC
    determination document on the DC site."""
    status, body = fetch_text(session, CREDITFIXINGS_AUCTIONS_API, accept="application/json")
    if not body:
        log.warning("ISDA auction index unreachable (status=%s)", status)
        return []
    try:
        items = json.loads(body)
    except json.JSONDecodeError as exc:
        log.warning("ISDA auction index not JSON: %s", exc)
        return []

    out: list[Determination] = []
    for it in items:
        link = (it.get("isdaLink") or "").strip()
        entity = (it.get("legalName") or it.get("shortName") or "").strip()
        if not entity:
            continue
        adate = (it.get("auctionDate") or "")[:10] or None
        # the DC determination precedes the auction; if the document slug encodes
        # an explicit date/event use it, else leave date None (don't fabricate).
        det_date = _parse_date(link) if link else None
        out.append(
            Determination(
                date=det_date,
                committee=_region_to_committee(it.get("dcRegion")),
                reference_entity=entity,
                issue_number=str(it.get("auctionID")) if it.get("auctionID") else None,
                credit_event_type=_event_from_slug(link) if link else None,
                decision="DC credit event determination (auction held)",
                doc_type="decision",
                url=link or BASE_URL,
                source="dc-isda",
                title=entity,
                tags=["auction"],
                auction_date=adate,
                auction_held=True,
            )
        )
    log.info("ISDA index: %d determinations with clean entity names", len(out))
    return out


def fetch_via_rest(session, max_pages: int = 20) -> list[Determination]:
    """Pull documents/posts from the WordPress REST API."""
    out: list[Determination] = []
    for endpoint in ("wp/v2/documents", "wp/v2/posts", "wp/v2/media"):
        page = 1
        while page <= max_pages:
            url = f"{BASE_URL}/wp-json/{endpoint}?per_page=100&page={page}"
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                break
            items = resp.json()
            if not items:
                break
            for it in items:
                link = it.get("source_url") or it.get("link") or ""
                title = (it.get("title") or {}).get("rendered", "") if isinstance(
                    it.get("title"), dict
                ) else (it.get("title") or "")
                rec = _record_from_url(link, source="rest-api")
                if it.get("date"):
                    rec.date = rec.date or it["date"][:10]
                rec.title = title or rec.title
                rec.reference_entity = rec.reference_entity or _slug_to_entity(title)
                rec.committee = rec.committee or _classify(title, REGIONS)
                rec.credit_event_type = rec.credit_event_type or _classify(title, CREDIT_EVENTS)
                out.append(rec)
            page += 1
            time.sleep(POLITE_DELAY)
    return out


def fetch_via_sitemap(session) -> list[Determination]:
    """Collect document URLs from the XML sitemap(s)."""
    from bs4 import BeautifulSoup

    out: list[Determination] = []
    seen: set[str] = set()
    candidates = [f"{BASE_URL}/sitemap_index.xml", f"{BASE_URL}/wp-sitemap.xml"]
    queue = list(candidates)
    while queue:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        resp = session.get(sm, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, "xml")
        for loc in soup.find_all("loc"):
            link = loc.get_text(strip=True)
            if link.endswith(".xml") and link not in seen:
                queue.append(link)  # nested sitemap
            elif "/documents/" in link or "/docs/" in link or link.endswith(".pdf"):
                out.append(_record_from_url(link, source="sitemap"))
        time.sleep(POLITE_DELAY)
    return out


def enrich_with_pdf(session, rec: Determination) -> Determination:
    """Download a decision PDF and extract region / credit-event / outcome."""
    try:
        import pdfplumber  # noqa
    except ImportError:
        log.warning("pdfplumber not installed; skipping PDF parsing")
        return rec
    import io
    import pdfplumber

    try:
        resp = session.get(rec.url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200 or "pdf" not in resp.headers.get("content-type", ""):
            return rec
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[:4])
    except Exception as exc:  # network / parse errors are non-fatal
        log.debug("PDF parse failed for %s: %s", rec.url, exc)
        return rec

    rec.committee = rec.committee or _classify(text, REGIONS)
    rec.credit_event_type = rec.credit_event_type or _classify(text, CREDIT_EVENTS)
    rec.date = rec.date or _parse_date(text)
    if re.search(r"\bauction\b", text, re.I):
        rec.tags.append("auction")
        rec.auction_held = True
        m = re.search(r"auction.{0,40}?(\d{1,2}[-/ ]\w+[-/ ]\d{4}|\d{4}-\d{2}-\d{2})", text, re.I)
        if m:
            rec.auction_date = _parse_date(m.group(1)) or rec.auction_date
    if re.search(r"\bno\b.{0,20}credit event", text, re.I):
        rec.decision = rec.decision or "No credit event"
    elif re.search(r"credit event.{0,20}(occurred|has occurred)", text, re.I):
        rec.decision = rec.decision or "Credit event occurred"
    time.sleep(POLITE_DELAY)
    return rec


_HASH_RE = re.compile(r"^[0-9a-f]{16,}$", re.I)


def _is_garbage_entity(name: str | None) -> bool:
    """Reject MD5-style hashed filenames masquerading as entity names."""
    if not name:
        return False
    compact = re.sub(r"[^0-9a-zA-Z]", "", name)
    return bool(_HASH_RE.match(compact)) or (
        sum(c.isdigit() for c in compact) > len(compact) * 0.5 and len(compact) > 12
    )


def scrape_live(parse_pdfs: bool = False) -> list[Determination]:
    """Run the full live scrape. Raises RuntimeError if no source is reachable.

    Primary source is the official ISDA auction index (clean entity names +
    links to DC determinations); the DC WordPress REST/sitemap are kept only as
    a supplementary fallback and are filtered for hash-garbage filenames.
    """
    try:
        import requests  # noqa
        from bs4 import BeautifulSoup  # noqa
    except ImportError as exc:
        raise SystemExit(
            "Install deps first: pip install requests beautifulsoup4 lxml"
        ) from exc

    session = _session()

    records: dict[str, Determination] = {}

    # 1) primary: official auction index → real, cleanly-named determinations
    try:
        for rec in fetch_via_isda_index(session):
            if rec.url:
                records.setdefault(rec.url, rec)
    except Exception as exc:
        log.warning("fetch_via_isda_index failed: %s", exc)

    # 2) supplementary: DC WordPress REST/sitemap. The DC site stores its decision
    #    PDFs under MD5-hashed filenames, so only keep rows that carry a real,
    #    human-readable entity name (clean slugs); never emit a hash as data.
    for fetcher in (fetch_via_rest, fetch_via_sitemap):
        try:
            for rec in fetcher(session):
                if not rec.url or rec.url in records:
                    continue
                if not rec.reference_entity or _is_garbage_entity(rec.reference_entity):
                    continue
                records.setdefault(rec.url, rec)
        except Exception as exc:
            log.warning("%s failed: %s", fetcher.__name__, exc)

    recs = list(records.values())
    if not recs:
        raise RuntimeError(
            "No determinations discoverable (auction index + DC site both empty/"
            "blocked). Run from a permitted network."
        )
    log.info("Discovered %d documents (%d with a known entity)",
             len(recs), sum(1 for r in recs if r.reference_entity))

    # enrich the auction-linked determinations by scraping their DC-site page for
    # a real determination date + credit event (skip rows that already have both)
    to_enrich = [r for r in recs if r.source == "dc-isda"
                 and "cdsdeterminationscommittees.org" in (r.url or "")]
    if to_enrich:
        log.info("Enriching %d determinations from their DC-site pages…", len(to_enrich))
        for rec in to_enrich:
            try:
                enrich_from_dc_page(session, rec)
            except Exception as exc:
                log.debug("page enrich failed for %s: %s", rec.url, exc)

    if parse_pdfs:
        # enrich only real DC-site PDFs (skip the clean isda-index rows)
        decisions = [r for r in recs if r.doc_type == "decision"
                     and r.url.lower().endswith(".pdf") and r.source != "dc-isda"]
        log.info("Parsing %d decision PDFs…", len(decisions))
        for rec in decisions:
            enrich_with_pdf(session, rec)

    return recs


# ── demo / seed data ────────────────────────────────────────────────────────────
def make_demo(n: int = 140) -> list[Determination]:
    """Synthetic, clearly-labelled determinations for offline dashboard dev."""
    import numpy as np

    rng = np.random.default_rng(2024)
    regions = ["Americas", "EMEA", "Asia ex-Japan", "Japan", "Australia-New Zealand"]
    region_w = [0.42, 0.40, 0.10, 0.05, 0.03]
    events = list(dict.fromkeys(CREDIT_EVENTS.values())) + [None]
    event_w = [0.30, 0.34, 0.20, 0.06, 0.03, 0.02, 0.05]
    outcomes = ["Credit event occurred", "No credit event", "Question dismissed",
                "Auction held", "Determination published"]
    sectors = ["Retail", "Energy", "Telecom", "Auto", "Airline", "Property",
               "Bank", "Media", "Utilities", "Healthcare"]
    out: list[Determination] = []
    for i in range(n):
        yr = int(rng.integers(2010, 2027))
        mo = int(rng.integers(1, 13))
        dy = int(rng.integers(1, 28))
        d = date(yr, mo, dy)
        region = str(rng.choice(regions, p=region_w))
        ev = events[int(rng.choice(len(events), p=event_w))]
        ent = f"{rng.choice(sectors)} Holdings {i + 1:03d} (demo)"
        decision = str(rng.choice(outcomes))
        # a credit event sometimes proceeds to a settlement auction ~3-6 weeks later
        auction_date = None
        auction_held = False
        if ev is not None and decision in ("Credit event occurred", "Auction held") \
                and rng.random() < 0.75:
            auction_held = True
            auction_date = (d + timedelta(days=int(rng.integers(18, 45)))).isoformat()
        out.append(
            Determination(
                date=d.isoformat(),
                committee=region,
                reference_entity=ent,
                issue_number=f"{yr}{rng.integers(100000, 999999)}",
                credit_event_type=ev,
                decision=decision,
                doc_type="decision",
                url=f"{BASE_URL}/documents/{yr}/{mo:02d}/demo-{i+1:03d}.pdf/",
                source="synthetic-demo",
                title=f"[DEMO] {ent}",
                auction_held=auction_held,
                auction_date=auction_date,
            )
        )
    return out


# ── persistence ──────────────────────────────────────────────────────────────────
def save(records: Iterable[Determination]) -> pd.DataFrame:
    rows = [asdict(r) for r in records]
    df = pd.DataFrame(rows)
    if not df.empty:
        df["tags"] = df["tags"].apply(lambda t: ",".join(t) if isinstance(t, list) else "")
        df = df.sort_values("date", na_position="last").reset_index(drop=True)
    df.to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps(rows, indent=2, default=str))
    log.info("Wrote %d rows -> %s and %s", len(df), OUT_CSV, OUT_JSON)
    return df


def run(mode: str = "live", parse_pdfs: bool = False) -> pd.DataFrame:
    if mode == "demo":
        return save(make_demo())
    if mode == "seed-only":
        log.info("Writing %d verified seed references only.", len(SEED_REFERENCES))
        return save(SEED_REFERENCES)

    # live
    try:
        recs = scrape_live(parse_pdfs=parse_pdfs)
        if not recs:
            raise RuntimeError("No documents discovered.")
        # always fold in verified references so anchor points survive
        urls = {r.url for r in recs}
        recs += [r for r in SEED_REFERENCES if r.url not in urls]
        return save(recs)
    except RuntimeError as exc:
        log.error("LIVE REFRESH FAILED: %s", exc)
        log.error(
            "Falling back to %d verified seed references. "
            "No live data was refreshed in this environment.",
            len(SEED_REFERENCES),
        )
        return save(SEED_REFERENCES)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="CDS Determinations Committees scraper")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true", help="write synthetic demo data")
    g.add_argument("--seed-only", action="store_true", help="write verified seed refs only")
    p.add_argument("--pdf", action="store_true", help="download & parse decision PDFs")
    args = p.parse_args()

    mode = "demo" if args.demo else "seed-only" if args.seed_only else "live"
    df = run(mode=mode, parse_pdfs=args.pdf)
    if not df.empty:
        log.info(
            "Done. %d determinations | %s -> %s | regions: %s",
            len(df),
            df["date"].min(),
            df["date"].max(),
            ", ".join(sorted(df["committee"].dropna().unique())),
        )
