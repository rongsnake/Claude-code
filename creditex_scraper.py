"""
Creditex / Markit "Credit Event Fixings" auction scraper.

Source: https://www.creditfixings.com/  (auctions run by Creditex + S&P Global;
formerly Markit). Each credit-event settlement auction has a results page:

    https://www.creditfixings.com/CreditEventAuctions/results.jsp?ticker=<TICKER>

exposing the Final Price (the recovery / cash-settlement price), the Initial
Market Midpoint, the Net Open Interest (size + direction), the auction date and
currency, plus dealer submissions and limit orders.

This scraper:
  1. discovers auction tickers from the site index (falling back to a known list)
  2. parses each results page into a tidy Auction record
  3. (via reconcile.py) joins auctions to the DC determinations by reference
     entity + date.

NETWORK NOTE — same as the DC site: creditfixings.com is behind bot protection
(403) and this build sandbox's egress is allowlisted, so the live scrape only
works from a permitted network (your machine / the gcburton.org host). When the
site is unreachable the scraper falls back to verified seed auctions and says so.

Usage
-----
    python creditex_scraper.py            # live -> data/auctions.csv
    python creditex_scraper.py --demo     # synthetic auctions derived from
                                          # data/determinations.csv (for dev)
    python creditex_scraper.py --seed-only
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from cds_dc_scraper import (
    USER_AGENT, REQUEST_TIMEOUT, POLITE_DELAY, _parse_date, DATA_DIR,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("creditex")

BASE_URL = "https://www.creditfixings.com"
RESULTS = BASE_URL + "/CreditEventAuctions/results.jsp?ticker={ticker}"

OUT_CSV = DATA_DIR / "auctions.csv"
OUT_JSON = DATA_DIR / "auctions.json"

# Fallback ticker list used if homepage discovery is blocked.
KNOWN_TICKERS = [
    "F-Hertz", "NRAMC", "BANKSA", "JCP", "SIFO", "MATAFIN", "GENP", "GREECE",
]


@dataclass
class Auction:
    reference_entity: str | None
    auction_date: str | None
    currency: str | None
    final_price: float | None
    initial_market_midpoint: float | None
    net_open_interest_amount: float | None
    net_open_interest_direction: str | None
    transaction_type: str | None
    ticker: str | None
    url: str
    source: str
    title: str = ""


# ── verified real auctions (citable references) ───────────────────────────────
SEED_AUCTIONS: list[Auction] = [
    Auction(
        reference_entity="The Hertz Corporation",
        auction_date="2020-06-24",
        currency="USD",
        final_price=26.375,
        initial_market_midpoint=None,
        net_open_interest_amount=None,
        net_open_interest_direction=None,
        transaction_type="Senior",
        ticker="F-Hertz",
        url=RESULTS.format(ticker="F-Hertz"),
        source="reference",
        title="The Hertz Corporation Credit Event Auction",
    ),
    Auction(
        reference_entity="Ardagh Packaging Finance plc",
        auction_date="2026-03-11",  # per public reporting of the settlement auction
        currency="EUR",
        final_price=33.9,
        initial_market_midpoint=None,
        net_open_interest_amount=None,
        net_open_interest_direction=None,
        transaction_type="Senior",
        ticker=None,
        url=BASE_URL + "/",
        source="reference",
        title="Ardagh Packaging Finance plc Credit Event Auction",
    ),
    Auction(
        reference_entity="Northern Rock (Asset Management) plc",
        auction_date="2012-02-02",
        currency="GBP",
        final_price=None,
        initial_market_midpoint=None,
        net_open_interest_amount=None,
        net_open_interest_direction=None,
        transaction_type="Senior",
        ticker="NRAMC",
        url=RESULTS.format(ticker="NRAMC"),
        source="reference",
        title="Northern Rock (Asset Management) plc auction results",
    ),
]


# ── parsing helpers ────────────────────────────────────────────────────────────
def _num(text: str, label: str) -> float | None:
    m = re.search(label + r"[^0-9]{0,30}(\d{1,3}(?:\.\d+)?)\s*%?", text, re.I)
    return float(m.group(1)) if m else None


def _currency(text: str) -> str | None:
    m = re.search(r"\b(USD|EUR|GBP|JPY|CHF|CAD|AUD)\b", text)
    return m.group(1) if m else None


def _net_open_interest(text: str) -> tuple[float | None, str | None]:
    m = re.search(
        r"(?:net\s+)?open\s+interest[^0-9]{0,40}([\d,]+)\s*(?:to\s+)?(buy|sell)?",
        text, re.I,
    )
    if not m:
        m2 = re.search(r"([\d,]{6,})\s+to\s+(buy|sell)", text, re.I)
        if m2:
            return float(m2.group(1).replace(",", "")), m2.group(2).lower()
        return None, None
    amount = float(m.group(1).replace(",", "")) if m.group(1) else None
    direction = m.group(2).lower() if m.group(2) else None
    return amount, direction


def parse_results(html: str, ticker: str, url: str) -> Auction:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    title = (soup.title.get_text(strip=True) if soup.title else "") or ticker
    entity = re.sub(r"\s*(credit event auction|auction results).*$", "", title, flags=re.I).strip()
    amount, direction = _net_open_interest(text)
    return Auction(
        reference_entity=entity or None,
        auction_date=_parse_date(text),
        currency=_currency(text),
        final_price=_num(text, r"final\s+price"),
        initial_market_midpoint=_num(text, r"initial\s+market\s+midpoint"),
        net_open_interest_amount=amount,
        net_open_interest_direction=direction,
        transaction_type=("Subordinated" if re.search(r"subordinat", text, re.I) else "Senior"),
        ticker=ticker,
        url=url,
        source="creditfixings",
        title=title,
    )


# ── live scrape (JSON/CSV API + browser fallback) ───────────────────────────────
# creditfixings.com is now a client-side Angular app: the homepage HTML is an
# empty <app-root> shell, so the old results.jsp HTML scrape returns nothing.
# The app is backed by a JSON/CSV API which we hit directly:
#   /api/history/download  → CSV of every settled auction WITH the final price
#   /api/auctions          → JSON list (legal name, ticker, region, currency,
#                            isdaLink to the DC determination, auction state)
# If a plain request is blocked (403 / empty), `fetch_text` transparently retries
# with a real headless Chromium via Playwright (see cds_dc_scraper.browser_fetch).
HISTORY_CSV_API = BASE_URL + "/api/history/download"
AUCTIONS_API = BASE_URL + "/api/auctions"

# CDS debt tiers → coarse transaction_type used by the dashboard.
_TIER_MAP = {"SENIOR": "Senior", "SNRFOR": "Senior", "SUBLT2": "Subordinated",
             "SUBORD": "Subordinated", "SECDOM": "Senior Secured", "LIEN2": "2nd Lien",
             "LIEN3": "3rd Lien", "PREFT1": "Preferred"}


def _session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


def _parse_history_date(s: str | None) -> str | None:
    """'13-May-26' → '2026-05-13'."""
    if not s:
        return None
    from datetime import datetime
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return _parse_date(s)


def scrape_live() -> list[Auction]:
    """Pull real auctions from the creditfixings JSON/CSV API.

    Uses cds_dc_scraper.fetch_text, which falls back to a headless browser when a
    plain HTTP request is blocked. Raises RuntimeError if nothing is reachable.
    """
    try:
        import requests  # noqa
    except ImportError as exc:
        raise SystemExit("pip install requests beautifulsoup4 lxml") from exc

    import csv
    import io
    from cds_dc_scraper import fetch_text

    session = _session()

    # 1) live index (region / currency / legal name / DC link) keyed by ticker
    meta: dict[str, dict] = {}
    status, body = fetch_text(session, AUCTIONS_API, accept="application/json")
    if body:
        try:
            for it in json.loads(body):
                tk = (it.get("ticker") or "").strip()
                if tk:
                    meta[tk] = it
        except json.JSONDecodeError:
            log.warning("auctions index was not valid JSON")
    log.info("Auction index: %d live entries", len(meta))

    # 2) authoritative history CSV with final prices
    status, body = fetch_text(session, HISTORY_CSV_API, accept="text/csv")
    if not body:
        raise RuntimeError(
            f"creditfixings API unreachable (status={status}). "
            "Run from a permitted network or install Playwright for the browser fallback."
        )

    out: list[Auction] = []
    reader = csv.DictReader(io.StringIO(body))
    for row in reader:
        ticker = (row.get("Ticker") or "").strip() or None
        m = meta.get(ticker or "", {})
        tier = (row.get("Tier") or m.get("tier") or "").strip().upper()
        fp = (row.get("Final Price") or "").strip()
        try:
            final_price = float(fp) if fp not in ("", "N/A", "-") else None
        except ValueError:
            final_price = None
        entity = (m.get("legalName") or m.get("shortName") or row.get("Name") or "").strip()
        link = (m.get("isdaLink") or "").strip()
        out.append(
            Auction(
                reference_entity=entity or None,
                auction_date=_parse_history_date(row.get("Auction Date")),
                currency=m.get("CCY") or None,
                final_price=final_price,
                initial_market_midpoint=None,
                net_open_interest_amount=None,
                net_open_interest_direction=None,
                transaction_type=_TIER_MAP.get(tier, tier.title() or "Senior"),
                ticker=ticker,
                url=link or (RESULTS.format(ticker=ticker) if ticker else BASE_URL + "/"),
                source="creditfixings",
                title=f"{entity or ticker} Credit Event Auction",
            )
        )
    log.info("Parsed %d auctions from history CSV (%d with final price)",
             len(out), sum(1 for a in out if a.final_price is not None))
    return out


# ── demo (derived from determinations so reconciliation is demonstrable) ───────
def make_demo() -> list[Auction]:
    import numpy as np

    det_path = DATA_DIR / "determinations.csv"
    if not det_path.exists():
        log.warning("No determinations.csv; run cds_dc_scraper.py --demo first.")
        return []
    det = pd.read_csv(det_path)
    rng = np.random.default_rng(99)
    ccy = {"Americas": "USD", "EMEA": "EUR", "Asia ex-Japan": "USD",
           "Japan": "JPY", "Australia-New Zealand": "AUD", "All DCs": "USD"}
    out: list[Auction] = []
    for _, row in det.iterrows():
        had_auction = bool(row.get("auction_held")) or pd.notna(row.get("auction_date"))
        if not had_auction:
            continue
        adate = row.get("auction_date")
        if pd.isna(adate):
            adate = (pd.to_datetime(row["date"]) + timedelta(days=int(rng.integers(18, 45)))).date().isoformat()
        final = round(float(rng.uniform(5, 95)), 3)
        imm = round(min(99.5, max(0.5, final + float(rng.normal(0, 1.5)))), 3)
        out.append(
            Auction(
                reference_entity=row.get("reference_entity"),
                auction_date=str(adate)[:10],
                currency=ccy.get(row.get("committee"), "USD"),
                final_price=final,
                initial_market_midpoint=imm,
                net_open_interest_amount=float(rng.integers(5, 500)) * 1_000_000,
                net_open_interest_direction=str(rng.choice(["buy", "sell"])),
                transaction_type=str(rng.choice(["Senior", "Subordinated"], p=[0.85, 0.15])),
                ticker=None,
                url=row.get("url", BASE_URL + "/"),
                source="synthetic-demo",
                title=f"[DEMO] {row.get('reference_entity')} auction",
            )
        )
    return out


# ── persistence ──────────────────────────────────────────────────────────────────
def save(auctions: list[Auction]) -> pd.DataFrame:
    df = pd.DataFrame([asdict(a) for a in auctions])
    if not df.empty:
        df = df.sort_values("auction_date", na_position="last").reset_index(drop=True)
    df.to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps([asdict(a) for a in auctions], indent=2, default=str))
    log.info("Wrote %d auctions -> %s and %s", len(df), OUT_CSV, OUT_JSON)
    return df


def run(mode: str = "live") -> pd.DataFrame:
    if mode == "demo":
        return save(make_demo())
    if mode == "seed-only":
        return save(SEED_AUCTIONS)
    try:
        aucs = scrape_live()
        if not aucs:
            raise RuntimeError("No auctions parsed.")
        # fold in any verified seed not already covered by live data (by entity)
        have = {(a.reference_entity or "").strip().lower() for a in aucs}
        aucs += [a for a in SEED_AUCTIONS
                 if (a.reference_entity or "").strip().lower() not in have]
        return save(aucs)
    except RuntimeError as exc:
        log.error("LIVE AUCTION SCRAPE FAILED: %s", exc)
        log.error("Falling back to %d verified seed auctions. No live data refreshed.",
                  len(SEED_AUCTIONS))
        return save(SEED_AUCTIONS)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Creditex / creditfixings.com auction scraper")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true")
    g.add_argument("--seed-only", action="store_true")
    args = p.parse_args()
    mode = "demo" if args.demo else "seed-only" if args.seed_only else "live"
    df = run(mode=mode)
    if not df.empty:
        priced = df["final_price"].notna().sum()
        log.info("Done. %d auctions (%d with final price).", len(df), int(priced))
