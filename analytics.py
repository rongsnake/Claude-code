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
RECONCILED_CSV = DATA_DIR / "reconciled.csv"
ANALYTICS_JSON = DATA_DIR / "determinations_analytics.json"
TIDY_CSV = DATA_DIR / "determinations_tidy.csv"

RESTRUCTURING = "Restructuring"


def default_input() -> Path:
    """Prefer the reconciled (determinations + auctions) table when present."""
    return RECONCILED_CSV if RECONCILED_CSV.exists() else RAW_CSV


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
    df["final_price"] = (
        pd.to_numeric(df["final_price"], errors="coerce")
        if "final_price" in df.columns else float("nan")
    )
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


# Columns that only exist on an already-aggregated frame (one row per
# determination run / credit event) rather than the document-level table.
_AGGREGATED_MARKERS = ("n_documents", "credit_event_ref")


def collapse_source(df: pd.DataFrame) -> pd.DataFrame:
    """The document-level table to collapse into credit events.

    Callers may hand us a frame that is already one row per determination run
    (``build_dashboard``'s row set). Collapsing that a second time miscounts the
    events, so fall back to the canonical reconciled table — which is also what
    the ``credit_events.csv``/``.xlsx`` export reads, keeping every figure in
    agreement. A document-level frame (including a filtered one, as the Streamlit
    app passes) is used as given so filters are respected.
    """
    if any(c in df.columns for c in _AGGREGATED_MARKERS):
        canonical = default_input()
        if canonical.exists():
            return pd.read_csv(canonical)
    return df


def credit_event_view(df: pd.DataFrame) -> pd.DataFrame | None:
    """Collapse the document-level table to **one row per credit event**.

    The scraper emits one row per source document, so a single credit event is
    spread over many rows (decision, AST, bidder list, redlines…). Counting those
    rows as "determinations" overstates the dataset several-fold. ``credit_events``
    groups them on the DC reference number; this is the honest analytical unit.

    Returns ``None`` when the collapse is unavailable (e.g. the raw, unreconciled
    table), in which case callers fall back to document-level figures.
    """
    try:
        import credit_events
        ce, _drawer = credit_events.build_credit_events(collapse_source(df))
    except Exception:  # missing deps / columns — degrade to document level
        return None
    return ce if ce is not None and len(ce) else None


def _event_metrics(ce: pd.DataFrame) -> dict:
    """Metrics computed over the one-row-per-credit-event table."""
    ce = ce.copy()
    ce["date"] = pd.to_datetime(ce.get("date"), errors="coerce")
    fp = pd.to_numeric(ce.get("final_price"), errors="coerce").dropna()
    dta = pd.to_numeric(ce.get("days_to_auction"), errors="coerce").dropna()
    typed = ce["credit_event_type"].dropna() if "credit_event_type" in ce else pd.Series(dtype=object)
    n_typed = int(len(typed))
    held = ce.get("auction_held")
    n_auctions = int(held.fillna(False).astype(bool).sum()) if held is not None else int(len(fp))

    out = {
        "total_credit_events": int(len(ce)),
        "distinct_reference_entities": int(ce["reference_entity"].dropna().nunique()),
        "date_min": ce["date"].min().date().isoformat() if ce["date"].notna().any() else None,
        "date_max": ce["date"].max().date().isoformat() if ce["date"].notna().any() else None,
        "credit_events_typed": n_typed,
        "credit_events_untyped": int(len(ce) - n_typed),
        "auctions_held": n_auctions,
        "credit_event_type_counts": {str(k): int(v) for k, v in typed.value_counts().to_dict().items()},
        "credit_event_type_pct": {
            str(k): round(float(v) / n_typed * 100, 1)
            for k, v in typed.value_counts().to_dict().items()
        } if n_typed else {},
        "pct_restructuring_of_events": (
            round(float((typed == RESTRUCTURING).sum()) / n_typed * 100, 1) if n_typed else None
        ),
        "by_region_counts": {
            str(k): int(v)
            for k, v in ce["committee"].fillna("Unknown").value_counts().to_dict().items()
        },
        "by_year_counts": _int_keys(
            ce.groupby(ce["date"].dt.year.astype("Int64"), dropna=True).size().to_dict()
        ),
        "days_to_auction": {
            "count": int(dta.count()),
            "mean": round(float(dta.mean()), 1) if dta.count() else None,
            "median": float(dta.median()) if dta.count() else None,
            "min": int(dta.min()) if dta.count() else None,
            "max": int(dta.max()) if dta.count() else None,
        },
    }
    if len(fp):
        out["auction_final_price"] = {
            "count": int(fp.count()),
            "mean": round(float(fp.mean()), 2),
            "median": round(float(fp.median()), 2),
            "min": round(float(fp.min()), 2),
            "max": round(float(fp.max()), 2),
        }
        by_ev = (ce.assign(_fp=pd.to_numeric(ce.get("final_price"), errors="coerce"))
                   .dropna(subset=["_fp"]).groupby("credit_event_type")["_fp"].mean().round(2))
        out["avg_final_price_by_event"] = {str(k): float(v) for k, v in by_ev.to_dict().items()}
    # Honest reconciliation rate: of credit events that reached an auction, how
    # many carry a final price from Creditex. (The document-level rate divides by
    # every supporting document and is therefore meaningless.)
    out["reconciliation_rate_pct"] = (
        round(100 * int(fp.count()) / n_auctions, 1) if n_auctions else None
    )
    return out


def compute(df: pd.DataFrame) -> dict:
    """Return a JSON-serialisable metrics dict answering the common questions."""
    d = enrich(df)
    # determination-centric metrics exclude auction-only rows (auctions with no
    # matched determination); auction metrics below use the full table.
    det = d[d["match_status"] != "auction_only"] if "match_status" in d.columns else d
    n = len(det)
    events = det["credit_event_type"].dropna()
    n_events = int(len(events))
    by_event = events.value_counts()
    event_pct = (
        (by_event / n_events * 100).round(1).to_dict() if n_events else {}
    )
    dta = det["days_to_auction"].dropna()
    if "match_status" in d.columns:
        n_auctions = int(d["match_status"].isin(["matched", "auction_only"]).sum())
    else:
        n_auctions = int(d["auction_date"].notna().sum())

    metrics = {
        "total_determinations": int(n),
        "total_auctions": n_auctions,
        "date_min": det["date"].min().date().isoformat() if n and det["date"].notna().any() else None,
        "date_max": det["date"].max().date().isoformat() if n and det["date"].notna().any() else None,
        "distinct_reference_entities": int(det["reference_entity"].dropna().nunique()),
        "credit_events_tagged": n_events,
        "pct_restructuring_of_events": (
            round(float(det["is_restructuring"].sum()) / n_events * 100, 1) if n_events else None
        ),
        "credit_event_occurred_count": int(det["credit_event_occurred"].sum()),
        "auctions_count": int(det["days_to_auction"].notna().sum()),
        "days_to_auction": {
            "count": int(dta.count()),
            "mean": round(float(dta.mean()), 1) if dta.count() else None,
            "median": float(dta.median()) if dta.count() else None,
            "min": int(dta.min()) if dta.count() else None,
            "max": int(dta.max()) if dta.count() else None,
        },
        "credit_event_type_counts": {str(k): int(v) for k, v in by_event.to_dict().items()},
        "credit_event_type_pct": {str(k): float(v) for k, v in event_pct.items()},
        "by_region_counts": {str(k): int(v) for k, v in det["committee"].fillna("Unknown").value_counts().to_dict().items()},
        "by_year_counts": _int_keys(det.groupby("year", dropna=True).size().to_dict()),
    }

    # ── auction / reconciliation metrics (present when reconciled data is used) ──
    fp = d["final_price"].dropna() if "final_price" in d else pd.Series(dtype=float)
    if len(fp):
        metrics["auction_final_price"] = {
            "count": int(fp.count()),
            "mean": round(float(fp.mean()), 2),
            "median": round(float(fp.median()), 2),
            "min": round(float(fp.min()), 2),
            "max": round(float(fp.max()), 2),
        }
        rec = (d.dropna(subset=["final_price"])
                .groupby("credit_event_type")["final_price"].mean().round(2))
        metrics["avg_final_price_by_event"] = {str(k): float(v) for k, v in rec.to_dict().items()}
    if "match_status" in d.columns:
        ms = d["match_status"].value_counts().to_dict()
        metrics["match_status_counts"] = {str(k): int(v) for k, v in ms.items()}
        dets = int(ms.get("matched", 0)) + int(ms.get("determination_only", 0))
        metrics["doc_level_match_rate_pct"] = (
            round(100 * ms.get("matched", 0) / dets, 1) if dets else None
        )

    # ── credit-event layer (the honest analytical unit) ──────────────────────
    # One scraped row = one source document, so document counts overstate the
    # number of determinations several-fold. Where the collapse is available,
    # credit-event figures take precedence for every headline metric.
    src = collapse_source(df)
    metrics["total_documents"] = int(len(src))
    ce = credit_event_view(src)
    if ce is not None:
        metrics.update(_event_metrics(ce))
        metrics["unit"] = "credit_event"
    else:
        metrics.setdefault("total_credit_events", None)
        metrics["unit"] = "document"
        metrics["reconciliation_rate_pct"] = metrics.get("doc_level_match_rate_pct")
    metrics["schema_note"] = (
        "total_documents counts source documents (decisions, ASTs, bidder lists, "
        "redlines…). total_credit_events counts distinct credit events — the "
        "honest unit for rates and averages. total_determinations is retained as "
        "a document-level alias for backwards compatibility."
    )

    return metrics


def headline_answers(metrics: dict) -> list[tuple[str, str]]:
    """Human-readable answers to the example questions, for dashboards."""
    dta = metrics["days_to_auction"]
    n_ce = metrics.get("total_credit_events")
    out = []
    if n_ce:
        out.append(("Credit events", f"{n_ce:,}"))
        out.append(("Source documents behind them",
                    f"{metrics.get('total_documents', metrics['total_determinations']):,}"))
    else:
        out.append(("Source documents", f"{metrics['total_determinations']:,}"))
    out += [
        ("% of credit events that are Restructuring",
         "n/a" if metrics["pct_restructuring_of_events"] is None
         else f"{metrics['pct_restructuring_of_events']}%"),
        ("Avg days to auction",
         "n/a" if dta["mean"] is None else f"{dta['mean']} days  (median {dta['median']:.0f}, n={dta['count']})"),
        ("Distinct reference entities", f"{metrics['distinct_reference_entities']:,}"),
    ]
    fp = metrics.get("auction_final_price")
    if fp:
        out.append(("Avg auction final price (recovery)",
                    f"{fp['mean']:.2f}  (median {fp['median']:.2f}, n={fp['count']})"))
    if metrics.get("reconciliation_rate_pct") is not None:
        out.append(("Auctions with a Creditex final price",
                    f"{metrics['reconciliation_rate_pct']}%"))
    return out


def export(input_csv: str | Path | None = None) -> dict:
    input_csv = input_csv or default_input()
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
