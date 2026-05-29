"""
Reconcile Creditex auctions (creditfixings.com) with DC determinations
(cdsdeterminationscommittees.org).

The DC declares a credit event; Creditex/Markit then run the settlement auction
that fixes the final price (recovery). This joins the two by normalised
reference-entity name within a date window, producing one unified table:

    data/reconciled.csv / .json

with a `match_status` of:
    * matched            — determination linked to its auction
    * determination_only — determination with no auction found
    * auction_only       — auction with no determination in our data

Downstream (analytics.py, dashboards) prefer this reconciled table when present.

    python reconcile.py
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reconcile")

DATA_DIR = Path("data")
DET_CSV = DATA_DIR / "determinations.csv"
AUC_CSV = DATA_DIR / "auctions.csv"
OUT_CSV = DATA_DIR / "reconciled.csv"
OUT_JSON = DATA_DIR / "reconciled.json"

# auction must occur on/after the determination, within this many days
MAX_GAP_DAYS = 540

AUCTION_COLS = [
    "ticker", "currency", "final_price", "initial_market_midpoint",
    "net_open_interest_amount", "net_open_interest_direction",
    "transaction_type", "auction_date", "auction_url",
]

_SUFFIXES = re.compile(
    r"\b(the|plc|inc|incorporated|corp|corporation|s\.?a|n\.?v|ag|ltd|limited|"
    r"llc|co|company|holdings?|group|finance|se)\b", re.I,
)


def norm_entity(name) -> str:
    if not isinstance(name, str):
        return ""
    s = name.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = _SUFFIXES.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def reconcile(det: pd.DataFrame, auc: pd.DataFrame) -> pd.DataFrame:
    det = det.copy()
    auc = auc.copy()
    det["_key"] = det["reference_entity"].map(norm_entity)
    auc["_key"] = auc["reference_entity"].map(norm_entity)
    det["_d"] = pd.to_datetime(det.get("date"), errors="coerce")
    auc["_a"] = pd.to_datetime(auc.get("auction_date"), errors="coerce")
    auc = auc.rename(columns={"url": "auction_url"})

    used_auctions: set[int] = set()
    rows: list[dict] = []

    for _, d in det.iterrows():
        row = d.to_dict()
        cand = auc[(auc["_key"] == d["_key"]) & (d["_key"] != "")]
        if not cand.empty:
            # prefer an auction on/after the determination within the window,
            # otherwise the nearest by absolute date gap
            gap = (cand["_a"] - d["_d"]).dt.days
            forward = cand[(gap >= -7) & (gap <= MAX_GAP_DAYS)]
            pick = (forward if not forward.empty else cand).copy()
            pick["_absgap"] = (pick["_a"] - d["_d"]).abs()
            best = pick.sort_values("_absgap").iloc[0]
            used_auctions.add(int(best.name))
            for col in AUCTION_COLS:
                if col in best:
                    row[col] = best[col]
            row["match_status"] = "matched"
        else:
            row["match_status"] = "determination_only"
        rows.append(row)

    # auctions with no matched determination
    for idx, a in auc.iterrows():
        if int(idx) in used_auctions:
            continue
        rows.append({
            "reference_entity": a.get("reference_entity"),
            "committee": None,
            "credit_event_type": None,
            "decision": None,
            "date": None,
            "doc_type": "auction",
            "url": a.get("auction_url"),
            "source": a.get("source"),
            "ticker": a.get("ticker"),
            "currency": a.get("currency"),
            "final_price": a.get("final_price"),
            "initial_market_midpoint": a.get("initial_market_midpoint"),
            "net_open_interest_amount": a.get("net_open_interest_amount"),
            "net_open_interest_direction": a.get("net_open_interest_direction"),
            "transaction_type": a.get("transaction_type"),
            "auction_date": a.get("auction_date"),
            "auction_url": a.get("auction_url"),
            "match_status": "auction_only",
        })

    out = pd.DataFrame(rows)
    out = out.drop(columns=[c for c in ("_key", "_d", "_a", "_absgap") if c in out], errors="ignore")
    # mark that a real auction is attached
    out["auction_held"] = out["final_price"].notna() | out.get("auction_date").notna()
    return out


def run() -> pd.DataFrame:
    if not DET_CSV.exists():
        raise SystemExit("Run cds_dc_scraper.py first (no determinations.csv).")
    det = pd.read_csv(DET_CSV)
    auc = pd.read_csv(AUC_CSV) if AUC_CSV.exists() else pd.DataFrame(
        columns=["reference_entity", "auction_date", "url"]
    )
    out = reconcile(det, auc)
    out.to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(out.to_json(orient="records", indent=2))

    counts = out["match_status"].value_counts().to_dict()
    log.info("Reconciled %d rows -> %s", len(out), OUT_CSV)
    log.info("  %s", counts)
    matched = counts.get("matched", 0)
    dets = matched + counts.get("determination_only", 0)
    if dets:
        log.info("  reconciliation rate: %.0f%% of determinations have an auction",
                 100 * matched / dets)
    return out


if __name__ == "__main__":
    df = run()
    cols = ["date", "reference_entity", "credit_event_type", "auction_date",
            "final_price", "match_status"]
    print(df[[c for c in cols if c in df]].to_string(index=False))
