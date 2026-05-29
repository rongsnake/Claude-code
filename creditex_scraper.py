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


# ── live scrape ────────────────────────────────────────────────────────────────
def _session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


def discover_tickers(session) -> list[str]:
    """Parse the homepage for results.jsp?ticker=… links; fall back to known list."""
    from bs4 import BeautifulSoup

    found: list[str] = []
    try:
        resp = session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                m = re.search(r"ticker=([^&\"']+)", a["href"])
                if m:
                    found.append(m.group(1))
    except Exception as exc:
        log.warning("ticker discovery failed: %s", exc)
    tickers = sorted(set(found) | set(KNOWN_TICKERS))
    log.info("Discovered %d tickers (%d from site)", len(tickers), len(set(found)))
    return tickers


def scrape_live() -> list[Auction]:
    try:
        import requests  # noqa
        from bs4 import BeautifulSoup  # noqa
    except ImportError as exc:
        raise SystemExit("pip install requests beautifulsoup4 lxml") from exc

    import requests

    session = _session()
    try:
        probe = session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"Cannot reach {BASE_URL}: {exc}") from exc
    if probe.status_code == 403:
        raise RuntimeError(
            f"{BASE_URL} returned 403 (bot protection). Run from a permitted network."
        )

    out: list[Auction] = []
    for ticker in discover_tickers(session):
        url = RESULTS.format(ticker=ticker)
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                out.append(parse_results(r.text, ticker, url))
        except Exception as exc:
            log.debug("ticker %s failed: %s", ticker, exc)
        time.sleep(POLITE_DELAY)
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
        urls = {a.url for a in aucs}
        aucs += [a for a in SEED_AUCTIONS if a.url not in urls]
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
