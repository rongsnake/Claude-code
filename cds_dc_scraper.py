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
from datetime import datetime, date
from pathlib import Path
from typing import Iterable

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cds_dc")

BASE_URL = "https://www.cdsdeterminationscommittees.org"
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
    if re.search(r"\bno\b.{0,20}credit event", text, re.I):
        rec.decision = rec.decision or "No credit event"
    elif re.search(r"credit event.{0,20}(occurred|has occurred)", text, re.I):
        rec.decision = rec.decision or "Credit event occurred"
    time.sleep(POLITE_DELAY)
    return rec


def scrape_live(parse_pdfs: bool = False) -> list[Determination]:
    """Run the full live scrape. Raises RuntimeError if the site is unreachable."""
    try:
        import requests  # noqa
        from bs4 import BeautifulSoup  # noqa
    except ImportError as exc:
        raise SystemExit(
            "Install deps first: pip install requests beautifulsoup4 lxml"
        ) from exc

    import requests

    session = _session()
    # connectivity probe
    try:
        probe = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"Cannot reach {BASE_URL}: {exc}") from exc
    if probe.status_code == 403:
        raise RuntimeError(
            f"{BASE_URL} returned 403 (bot protection). Run this scraper from a "
            "network/host that the DC site permits (e.g. your own machine)."
        )

    records: dict[str, Determination] = {}
    for fetcher in (fetch_via_rest, fetch_via_sitemap):
        try:
            for rec in fetcher(session):
                if rec.url:
                    records.setdefault(rec.url, rec)
        except Exception as exc:
            log.warning("%s failed: %s", fetcher.__name__, exc)

    recs = list(records.values())
    log.info("Discovered %d documents", len(recs))

    if parse_pdfs:
        decisions = [r for r in recs if r.doc_type == "decision"]
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
        region = str(rng.choice(regions, p=region_w))
        ev = events[int(rng.choice(len(events), p=event_w))]
        ent = f"{rng.choice(sectors)} Holdings {i + 1:03d} (demo)"
        out.append(
            Determination(
                date=date(yr, mo, dy).isoformat(),
                committee=region,
                reference_entity=ent,
                issue_number=f"{yr}{rng.integers(100000, 999999)}",
                credit_event_type=ev,
                decision=str(rng.choice(outcomes)),
                doc_type="decision",
                url=f"{BASE_URL}/documents/{yr}/{mo:02d}/demo-{i+1:03d}.pdf/",
                source="synthetic-demo",
                title=f"[DEMO] {ent}",
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
