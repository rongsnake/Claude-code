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

# The regional DCs and auction-hardwiring framework began with the 2009 ISDA
# "Big Bang" Protocol (effective 2009-04-08). Before that there were no DC
# determinations, so any earlier auction cannot be mapped to one — we floor the
# determination↔auction reconciliation at this date.
DC_START = pd.Timestamp("2009-04-08")

# Phrases in a determination's decision text that mean NO auction will be held,
# so the determination must never be matched to an auction.
_NO_AUCTION = re.compile(
    r"no credit event|not occur|did not occur|no auction|auction.*not.*held", re.I)

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


def _seniority_rank(tx_type) -> tuple[int, int, str]:
    """Sort key that makes a multi-tranche auction day resolve to the *canonical*
    CDS recovery instead of whichever row the scraper emitted first.

    A single credit event can settle several auctions on the same day — senior,
    subordinated, first-lien (LCDS), and the 2009-style maturity buckets
    (``Senior - B2``). They price very differently: Anglo Irish settled senior at
    74.5-76.0 but subordinated at 18.0. Standard single-name CDS references
    *senior unsecured* obligations, so the senior auction carries the headline
    recovery; the rest are separate instruments.

    Returns (seniority, bucket, label) — lower sorts first."""
    s = str(tx_type or "").strip().lower()
    has_sub = "sub" in s                      # covers "subordinated" and "sublt2"
    has_snr = s.startswith(("senior", "snr"))
    if has_snr and not has_sub:
        rank = 0                              # Senior / Snrfor  → canonical
    elif has_snr and has_sub:
        rank = 1                              # combined "Senior/Subordinated"
    elif "lien" in s or "secured" in s:
        rank = 2                              # loan CDS (LCDS)
    elif has_sub:
        rank = 3                              # subordinated CDS
    else:
        rank = 4                              # unlabelled / unknown
    m = re.search(r"\bb(\d+)\b", s)           # maturity bucket B1/B2/B3
    return (rank, int(m.group(1)) if m else 0, s)


def _is_positive(d: dict) -> bool:
    """A determination is 'positive' — i.e. an auction is expected — only when a
    credit event occurred and an auction will be held. No auction is ever run for a
    'no credit event' or 'no auction' decision, so those must not match an auction.
    Signals: the auction tag, an 'auction held' decision, or a classified credit
    event type without a no-auction phrase in the decision text."""
    decision = str(d.get("decision") or "")
    if _NO_AUCTION.search(decision):
        return False
    if str(d.get("tags") or "").strip().lower() == "auction":
        return True
    if re.search(r"auction held", decision, re.I):
        return True
    cet = d.get("credit_event_type")
    return isinstance(cet, str) and cet.strip() != ""


def reconcile(det: pd.DataFrame, auc: pd.DataFrame) -> pd.DataFrame:
    det = det.copy()
    auc = auc.copy()
    det["_key"] = det["reference_entity"].map(norm_entity)
    auc["_key"] = auc["reference_entity"].map(norm_entity)
    det["_d"] = pd.to_datetime(det.get("date"), errors="coerce")
    auc["_a"] = pd.to_datetime(auc.get("auction_date"), errors="coerce")
    auc = auc.rename(columns={"url": "auction_url"})
    if "transaction_type" not in auc.columns:
        auc["transaction_type"] = None
    # Floor at the DC era: auctions before the framework existed cannot map to a
    # determination, so they take no part in *matching*. They are still real
    # auctions though (Delphi, Calpine, Fannie/Freddie, Landsbanki…), so they are
    # emitted as `auction_only` rather than silently dropped from the dataset.
    auc["_pre_dc"] = auc["_a"] < DC_START
    matchable = auc[~auc["_pre_dc"]]

    used_auctions: set[int] = set()
    rows: list[dict] = []

    for _, d in det.iterrows():
        row = d.to_dict()
        # Only positive determinations (credit event + auction to be held), dated in
        # the DC era, are eligible to match an auction.
        eligible = _is_positive(row) and (pd.isna(d["_d"]) or d["_d"] >= DC_START)
        cand = (matchable[(matchable["_key"] == d["_key"]) & (d["_key"] != "")]
                if eligible else matchable.iloc[0:0])
        if not cand.empty:
            if pd.isna(d["_d"]):
                # Determination date unknown (the scraper leaves it blank rather
                # than fabricating one) — fall back to matching on entity alone.
                pick = cand.copy()
            else:
                # An auction settles a credit event *after* it is determined, so
                # only auctions inside the forward window may match. Without this
                # a dated determination could bind to an unrelated earlier auction
                # for the same entity.
                gap = (cand["_a"] - d["_d"]).dt.days
                pick = cand[(gap >= -7) & (gap <= MAX_GAP_DAYS)].copy()
            if not pick.empty:
                pick["_absgap"] = (pick["_a"] - d["_d"]).abs()
                # A tranche with no recorded final price carries no recovery at
                # all, so it never outranks a priced one (Northern Rock's senior
                # bucket has no price; its senior/sub bucket settled at 99.125).
                pick["_nopx"] = pd.to_numeric(
                    pick.get("final_price"), errors="coerce").isna().astype(int)
                ranks = [_seniority_rank(t) for t in pick["transaction_type"]]
                pick["_snr"] = [r[0] for r in ranks]
                pick["_bkt"] = [r[1] for r in ranks]
                pick["_tt"] = [r[2] for r in ranks]
                best = (pick.sort_values(["_absgap", "_nopx", "_snr", "_bkt", "_tt"],
                                         kind="mergesort").iloc[0])
                used_auctions.add(int(best.name))
                for col in AUCTION_COLS:
                    if col in best:
                        row[col] = best[col]
                # Keep the auction's own provenance distinct from the
                # determination's: a live determination can carry a price from a
                # `synthetic-demo` auction, and the dashboard banner must be able
                # to see that rather than reporting the row as fully live.
                row["auction_source"] = best.get("source")
                # Disclose the other tranches that settled the same day, so the
                # headline recovery is never silently one of several prices.
                sibs = pick[pick["_a"] == best["_a"]]
                row["auction_tranche_count"] = int(len(sibs))
                if len(sibs) > 1:
                    row["auction_tranches"] = " | ".join(
                        f"{s['transaction_type'] or '?'}:{s['final_price']}"
                        for _, s in sibs.sort_values(["_snr", "_bkt", "_tt"]).iterrows())
                row["match_status"] = "matched"
            else:
                row["match_status"] = "determination_only"
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
            # True for auctions that predate the DC framework (2009 Big Bang), which
            # therefore have no determination to reconcile to by construction.
            "pre_dc_era": bool(a.get("_pre_dc")),
        })

    out = pd.DataFrame(rows)
    out = out.drop(columns=[c for c in ("_key", "_d", "_a", "_absgap", "_nopx",
                                        "_pre_dc", "_snr", "_bkt", "_tt") if c in out],
                   errors="ignore")
    # mark that a real auction is attached (tolerate a run with no auction data)
    def _col(name):
        return out[name] if name in out.columns else pd.Series(pd.NA, index=out.index)

    out["auction_held"] = _col("final_price").notna() | _col("auction_date").notna()
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
    if "pre_dc_era" in out.columns:
        n_pre = int(out["pre_dc_era"].fillna(False).astype(bool).sum())
        if n_pre:
            log.info("  %d auction(s) predate the DC framework (%s) and are emitted "
                     "as auction_only", n_pre, DC_START.date())
    if "auction_tranche_count" in out.columns:
        n_multi = int((pd.to_numeric(out["auction_tranche_count"], errors="coerce") > 1).sum())
        if n_multi:
            log.info("  %d matched determination(s) settled several tranches the same "
                     "day; the senior/priced one is used (see auction_tranches)", n_multi)
    return out


if __name__ == "__main__":
    df = run()
    cols = ["date", "reference_entity", "credit_event_type", "auction_date",
            "final_price", "match_status"]
    print(df[[c for c in cols if c in df]].to_string(index=False))
