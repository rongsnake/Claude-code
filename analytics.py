"""
Analytics over the Credit Derivatives Determinations Committees dataset.

Turns the raw scraped table into:
  * derived/tidy columns (year, month, days_to_auction, is_restructuring, …)
  * a metrics dict that answers the common questions
    (avg days to auction, % of credit events that are restructuring, …)

Used by both dashboards and exportable to JSON/CSV for downstream graphing.

    python analytics.py            # prints a summary, writes
                                   # data/determinations_analytics.json
                                   # data/determinations_tidy.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
RAW_CSV = DATA_DIR / "determinations.csv"
ANALYTICS_JSON = DATA_DIR / "determinations_analytics.json"
TIDY_CSV = DATA_DIR / "determinations_tidy.csv"

RESTRUCTURING = "Restructuring"


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns used for analysis."""
    df = df.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    if "auction_date" in df.columns:
        df["auction_date"] = pd.to_datetime(df["auction_date"], errors="coerce")
    else:
        df["auction_date"] = pd.NaT

    df["year"] = df["date"].dt.year.astype("Int64")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["days_to_auction"] = (df["auction_date"] - df["date"]).dt.days
    df["is_restructuring"] = df.get("credit_event_type").eq(RESTRUCTURING)
    df["is_credit_event"] = df.get("credit_event_type").notna()

    decision = df.get("decision")
    if decision is None:
        decision = pd.Series("", index=df.index)
    decision = decision.fillna("").astype(str)
    df["credit_event_occurred"] = (
        decision.str.contains("credit event occurred", case=False)
        | decision.str.contains("auction", case=False)
        | df.get("auction_held", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    )
    return df


def _int_keys(series_dict: dict) -> dict:
    return {(int(k) if pd.notna(k) else "Unknown"): int(v) for k, v in series_dict.items()}


def compute(df: pd.DataFrame) -> dict:
    """Return a JSON-serialisable metrics dict answering the common questions."""
    d = enrich(df)
    n = len(d)
    events = d["credit_event_type"].dropna()
    n_events = int(len(events))
    by_event = events.value_counts()
    event_pct = (
        (by_event / n_events * 100).round(1).to_dict() if n_events else {}
    )
    dta = d["days_to_auction"].dropna()

    return {
        "total_determinations": int(n),
        "date_min": d["date"].min().date().isoformat() if n and d["date"].notna().any() else None,
        "date_max": d["date"].max().date().isoformat() if n and d["date"].notna().any() else None,
        "distinct_reference_entities": int(d["reference_entity"].dropna().nunique()),
        "credit_events_tagged": n_events,
        "pct_restructuring_of_events": (
            round(float(d["is_restructuring"].sum()) / n_events * 100, 1) if n_events else None
        ),
        "credit_event_occurred_count": int(d["credit_event_occurred"].sum()),
        "auctions_count": int(d["days_to_auction"].notna().sum()),
        "days_to_auction": {
            "count": int(dta.count()),
            "mean": round(float(dta.mean()), 1) if dta.count() else None,
            "median": float(dta.median()) if dta.count() else None,
            "min": int(dta.min()) if dta.count() else None,
            "max": int(dta.max()) if dta.count() else None,
        },
        "credit_event_type_counts": {str(k): int(v) for k, v in by_event.to_dict().items()},
        "credit_event_type_pct": {str(k): float(v) for k, v in event_pct.items()},
        "by_region_counts": {str(k): int(v) for k, v in d["committee"].fillna("Unknown").value_counts().to_dict().items()},
        "by_year_counts": _int_keys(d.groupby("year", dropna=True).size().to_dict()),
    }


def headline_answers(metrics: dict) -> list[tuple[str, str]]:
    """Human-readable answers to the example questions, for dashboards."""
    dta = metrics["days_to_auction"]
    out = [
        ("Total determinations", f"{metrics['total_determinations']:,}"),
        ("% of credit events that are Restructuring",
         "n/a" if metrics["pct_restructuring_of_events"] is None
         else f"{metrics['pct_restructuring_of_events']}%"),
        ("Avg days to auction",
         "n/a" if dta["mean"] is None else f"{dta['mean']} days  (median {dta['median']:.0f}, n={dta['count']})"),
        ("Distinct reference entities", f"{metrics['distinct_reference_entities']:,}"),
    ]
    return out


def export(input_csv: str | Path = RAW_CSV) -> dict:
    df = pd.read_csv(input_csv)
    metrics = compute(df)
    ANALYTICS_JSON.write_text(json.dumps(metrics, indent=2))
    enrich(df).to_csv(TIDY_CSV, index=False)
    return metrics


if __name__ == "__main__":
    m = export()
    print(json.dumps(m, indent=2))
    print(f"\nWrote {ANALYTICS_JSON} and {TIDY_CSV}")
    for label, value in headline_answers(m):
        print(f"  • {label}: {value}")
