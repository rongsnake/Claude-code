"""
Build a self-contained static dashboard (dashboard.html) for the Credit
Derivatives Determinations Committees dataset.

The output is a single HTML file with the data embedded and Plotly.js from a CDN.
Deterministic presentation (filters, fields, charts, document drawers) runs fully
client-side, so the file works behind the Caddy basic_auth gate with no backend.
Two dynamic features call the companion API at ``/cds/api/`` when it is reachable:

  * a free-text **Ask** box (RAG over the document corpus via local Ollama), with a
    keyword fallback over the embedded document index when the API is offline;
  * an **Update** button that triggers a live refresh + re-index.

Inputs (built by build_index.py; falls back to the raw tables if absent):
    data/index/determinations_clean.csv   cleaned + enriched determinations
    data/index/documents.json             per-document records (kind, flags, …)
    data/index/index_meta.json            counts + build time

Usage:
    python build_dashboard.py
    python build_dashboard.py --output public/index.html
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import analytics
import credit_events

DEFAULT_OUTPUT = Path("dashboard.html")
INDEX_DIR = Path("data") / "index"

# Wider field set than the old dashboard — these populate the sortable table and
# the per-row filtering.
ROW_COLS = [
    "date", "year", "committee", "reference_entity", "issue_number",
    "credit_event_type", "decision", "auction_held", "auction_date",
    "days_to_auction", "final_price", "currency", "transaction_type",
    "net_open_interest_amount", "net_open_interest_direction", "match_status",
    "is_restructuring", "credit_event_occurred", "url",
]

# Lightweight per-document fields embedded for the drawer + offline search.
DOC_FIELDS = [
    "reference_entity", "committee", "doc_kind", "is_proforma", "is_blackline",
    "meeting_date", "issue_number", "vote_result", "title", "url", "snippet",
    "flag_list",
]


def _input_path() -> Path:
    clean = INDEX_DIR / "determinations_clean.csv"
    return clean if clean.exists() else analytics.default_input()


def _source_label(df: pd.DataFrame) -> tuple[str, str]:
    sources = set(df.get("source", pd.Series(dtype=str)).dropna().unique())
    if sources == {"synthetic-demo"}:
        return ("DEMO DATA — synthetic, illustrative only. "
                "Run cds_dc_scraper.py with network access to refresh live data.", "warn")
    if sources <= {"reference"}:
        return ("SEED DATA — a small set of verified reference determinations only. "
                "A full live refresh was not run in this environment.", "warn")
    if "synthetic-demo" in sources:
        return ("MIXED DATA — synthetic demo rows alongside scraped/seed rows.", "warn")
    return (f"Live scrape of cdsdeterminationscommittees.org ({len(df):,} determinations).", "ok")


def _clean_rows(df: pd.DataFrame) -> list[dict]:
    d = analytics.enrich(df)
    for col in ("date", "auction_date"):
        if col in d:
            d[col] = pd.to_datetime(d[col], errors="coerce").dt.strftime("%Y-%m-%d")
    keep = [c for c in ROW_COLS if c in d.columns]
    d = d[keep].astype(object).where(pd.notna(d[keep]), None)
    records = d.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
    return records


def _load_docs() -> list[dict]:
    p = INDEX_DIR / "documents.json"
    if not p.exists():
        return []
    docs = json.loads(p.read_text())
    out = []
    for d in docs:
        out.append({k: d.get(k) for k in DOC_FIELDS})
    return out


def _load_runs() -> list[dict]:
    p = INDEX_DIR / "runs.json"
    return json.loads(p.read_text()) if p.exists() else []


_ENTITY_SUFFIXES = re.compile(
    r"\b(inc|incorporated|ltd|limited|corp|corporation|co|company|plc|llc|lp|llp|"
    r"nv|n\.v|sa|s\.a|ag|spa|s\.p\.a|holdings?|group|the)\b", re.I)


def _norm_entity(name) -> str:
    """Normalise a reference-entity name so the reconciled table and the document/run
    corpus join despite punctuation, casing, and legal-suffix noise."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    s = _ENTITY_SUFFIXES.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _run_corpus_by_entity(runs: list[dict]) -> tuple[dict, dict]:
    """From the (possibly fragile/stale) determination runs, build two lookups keyed
    by normalised reference entity: deduped source documents (carrying the real
    download/source_url links the drawer needs) and the best extractive summary +
    DC question. Used to enrich the authoritative reconciled rows — which always
    carry correct dates — so the table stays current even when run grouping lags."""
    docs_by_entity: dict[str, dict] = {}
    detail_by_entity: dict[str, dict] = {}
    for r in runs:
        ent = _norm_entity(r.get("reference_entity"))
        if not ent:
            continue
        bucket = docs_by_entity.setdefault(ent, {})
        for d in (r.get("documents") or []):
            key = d.get("doc_id") or d.get("source_url") or d.get("title")
            if key and key not in bucket:
                bucket[key] = d
        det = detail_by_entity.setdefault(ent, {"summary": None, "question": None})
        if r.get("summary") and not det["summary"]:
            det["summary"] = r["summary"]
        if r.get("question") and not det["question"]:
            det["question"] = r["question"]
    return docs_by_entity, detail_by_entity


def _attach_run_details(rows: list[dict], runs: list[dict]) -> None:
    """Graft per-entity documents + summaries from `runs` onto the determination rows."""
    docs_by_entity, detail_by_entity = _run_corpus_by_entity(runs)
    for row in rows:
        ent = _norm_entity(row.get("reference_entity"))
        docs = list(docs_by_entity.get(ent, {}).values())
        row["documents"] = docs
        row["n_documents"] = max(len(docs), int(row.get("n_documents") or 0))
        det = detail_by_entity.get(ent)
        if det:
            row["summary"] = det.get("summary")
            row["question"] = det.get("question")


# Every DC determination is made by one of the five regional committees (or the
# joint "All DCs"), a structure that has existed since the 2009 Big Bang Protocol —
# so a real determination is always attributable to a region. The raw scrape only
# tags ~40% directly, so we also recover the committee from the document URL/title
# and then propagate it across all rows of the same reference entity.
_COMMITTEE_PATTERNS = [
    ("All DCs", re.compile(r"all[\s_-]?dcs|alldcs|all determinations", re.I)),
    ("Asia ex-Japan", re.compile(r"asia.?ex.?japan|asia ex japan|asia-ex|\baej\b", re.I)),
    ("Australia-New Zealand", re.compile(r"australia|new[\s_-]?zealand|\banz\b", re.I)),
    ("Japan", re.compile(r"\bjapan\b", re.I)),
    ("EMEA", re.compile(r"\bemea\b", re.I)),
    ("Americas", re.compile(r"\bamericas?\b", re.I)),
]


def _parse_committee(url, title) -> "str | None":
    hay = f"{url or ''} {title or ''}"
    for name, pat in _COMMITTEE_PATTERNS:
        if pat.search(hay):
            return name
    return None


def _committee_series(df: pd.DataFrame) -> pd.Series:
    """Best-effort committee for every row: the scraped value, else parsed from the
    URL/title, else propagated from other rows of the same reference entity."""
    cc = df["committee"].where(df["committee"].notna(), None)
    parsed = [
        _parse_committee(u, t)
        for u, t in zip(df.get("url", ""), df.get("title", ""))
    ]
    cc = cc.fillna(pd.Series(parsed, index=df.index))
    ek = df["reference_entity"].map(_norm_entity)
    known = pd.DataFrame({"ek": ek, "cc": cc})
    by_entity = (known[known.cc.notna() & known.ek.ne("")]
                 .groupby("ek")["cc"].agg(lambda s: s.mode().iloc[0]))
    fill = ek.map(by_entity)
    return cc.fillna(fill)


def _build_determinations(df: pd.DataFrame, runs: list[dict]) -> list[dict]:
    """Collapse the reconciled, document-level table into one row per DC
    determination, with a committee on every row.

    The full-depth scrape mixes genuine DC decisions with supporting documents
    (offering memoranda, transcripts, bidder lists) whose 'reference entity' is
    really a document title — those have no committee and are not determinations.
    We keep only rows that (a) resolve to a committee and (b) carry a determination
    signal (structured source, credit-event type, decision, issue number, or a
    decision/determination/statement title), then group them by DC issue number
    (falling back to entity+year) so the table and charts count determinations, not
    documents. Supporting documents still reach the per-entity drawer via
    _attach_run_details."""
    df = df.copy()
    df["committee"] = _committee_series(df)
    title = df.get("title", pd.Series("", index=df.index)).fillna("")
    looks_like_decision = title.str.contains(r"decision|determination|statement", case=False)
    is_det = df["committee"].notna() & (
        df.get("source", pd.Series(index=df.index)).isin(["dc-isda", "rest-api", "reference"])
        | df["credit_event_type"].notna()
        | df["decision"].notna()
        | df["issue_number"].notna()
        | looks_like_decision
    )
    sub = df[is_det].copy()
    sub["_d"] = pd.to_datetime(sub["date"], errors="coerce")
    sub["_year"] = sub["_d"].dt.year
    ek = sub["reference_entity"].map(_norm_entity)
    issue = sub["issue_number"].astype("string").str.replace(r"\.0$", "", regex=True)
    gk = issue.where(sub["issue_number"].notna(), ek + "|" + sub["_year"].astype("string"))
    sub["_gk"] = gk.fillna(ek)

    def _first(grp, col):
        if col not in grp:
            return None
        s = grp[col].dropna()
        return s.iloc[0] if not s.empty else None

    rows: list[dict] = []
    for _, grp in sub.groupby("_gk", sort=False):
        # Prefer the richest row (one that carries a credit-event type / final price).
        grp = grp.sort_values(["credit_event_type", "final_price"], na_position="last")
        date = grp["_d"].min()
        year = int(date.year) if pd.notna(date) else None
        rec = {
            "date": date.strftime("%Y-%m-%d") if pd.notna(date) else None,
            "year": year,
            "committee": _first(grp, "committee"),
            "reference_entity": _first(grp, "reference_entity"),
            "issue_number": _first(grp, "issue_number"),
            "credit_event_type": _first(grp, "credit_event_type"),
            "decision": _first(grp, "decision"),
            "credit_event_occurred": bool(grp.get("credit_event_occurred", pd.Series(dtype=bool)).fillna(False).any()),
            "auction_date": _first(grp, "auction_date"),
            "final_price": _first(grp, "final_price"),
            "currency": _first(grp, "currency"),
            "transaction_type": _first(grp, "transaction_type"),
            "is_restructuring": str(_first(grp, "credit_event_type") or "").lower() == "restructuring",
            "url": _first(grp, "url"),
            "n_documents": int(len(grp)),
        }
        rec["auction_held"] = rec["final_price"] is not None or rec["auction_date"] is not None
        rec["match_status"] = "matched" if rec["final_price"] is not None else "determination_only"
        rows.append(rec)

    _attach_run_details(rows, runs)
    rows.sort(key=lambda r: (r.get("date") or ""), reverse=True)
    return rows


def _load_meta() -> dict:
    p = INDEX_DIR / "index_meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


# Columns exported in the "all Credit Events" download, in a sensible reading order.
_CE_EXPORT_COLS = [
    "date", "reference_entity", "committee", "credit_event_type",
    "credit_event_occurred", "decision", "issue_number", "credit_event_ref",
    "n_requests", "n_documents", "auction_date",
    "auction_held", "final_price", "currency", "days_to_auction",
    "transaction_type", "ticker", "source", "url", "auction_url",
]


def _credit_events_rowlevel(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback (pre-grouping) export: every document-level row where a credit event
    occurred OR a credit-event type was classified. Kept for when the reconciled
    table or the per-event grouping is unavailable."""
    d = analytics.enrich(df)
    occurred = d.get("credit_event_occurred")
    has_type = d.get("credit_event_type")
    mask = pd.Series(False, index=d.index)
    if occurred is not None:
        mask = mask | occurred.fillna(False).astype(bool)
    if has_type is not None:
        mask = mask | has_type.fillna("").astype(str).str.strip().ne("")
    return d[mask].copy()


def _write_credit_events_export(df: pd.DataFrame, output_path: Path) -> int:
    """Write credit_events.csv (+ .xlsx) next to the dashboard: one row per real
    credit event, collapsed from the document-level reconciled table by DC reference
    number (see credit_events.py). Returns the row count. Falls back to the
    document-level union if the reconciled table or grouping is unavailable."""
    try:
        rec = pd.read_csv(analytics.default_input())
        ce, _drawer = credit_events.build_credit_events(rec)
    except Exception as e:
        print(f"  (credit-event grouping failed, falling back to row-level: {e})")
        ce = _credit_events_rowlevel(df)
    for col in ("date", "auction_date"):
        if col in ce:
            ce[col] = pd.to_datetime(ce[col], errors="coerce").dt.strftime("%Y-%m-%d")
    if "date" in ce:
        ce = ce.sort_values("date", ascending=False, na_position="last")
    cols = [c for c in _CE_EXPORT_COLS if c in ce.columns]
    ce = ce[cols]

    csv_path = output_path.parent / "credit_events.csv"
    ce.to_csv(csv_path, index=False)
    try:
        ce.to_excel(output_path.parent / "credit_events.xlsx", index=False, sheet_name="Credit Events")
    except Exception as e:  # openpyxl missing or write failure — CSV still produced
        print(f"  (xlsx export skipped: {e})")
    print(f"Wrote {csv_path} ({len(ce)} credit events)")
    return len(ce)


def build(input_path: Path, output_path: Path) -> Path:
    if not input_path.exists():
        raise SystemExit(
            f"{input_path} not found. Run `python cds_dc_scraper.py` then `python build_index.py`."
        )
    df = pd.read_csv(input_path)
    _, banner_class = _source_label(df)

    # Collapse the document-level reconciled table into one row per DC determination,
    # with a committee on every row (see _build_determinations). This is what makes
    # the charts meaningful: counting determinations rather than the supporting
    # documents that otherwise swamp them and leave committee/event/recovery blank.
    rows = _build_determinations(df, _load_runs())
    # Metrics + headline cards are computed over the determination set (not the raw
    # document table) so the KPIs, charts, and answer cards all agree.
    metrics = analytics.compute(pd.DataFrame(rows))
    answers = analytics.headline_answers(metrics)
    banner_text = (f"Live scrape of cdsdeterminationscommittees.org — {len(rows):,} DC "
                   f"determinations across {len(df):,} indexed documents."
                   if banner_class == "ok" else _source_label(df)[0])
    years = [r["year"] for r in rows if r.get("year")]
    typed = [r for r in rows if r.get("credit_event_type")]
    kpis = {
        "total": len(rows),
        "entities": len({r["reference_entity"] for r in rows if r.get("reference_entity")}),
        "credit_events": len(typed),
        "date_min": (min(years) if years else None),
        "date_max": (max(years) if years else None),
    }

    ce_count = _write_credit_events_export(df, output_path)

    payload = {
        "kpis": kpis,
        "credit_events_count": ce_count,
        "answers": [{"label": l, "value": v} for l, v in answers],
        "rows": rows,
        "docs": _load_docs(),
        "meta": _load_meta(),
        "analytics": metrics,
        "banner": {"text": banner_text, "cls": banner_class},
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(payload))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {output_path} ({output_path.stat().st_size // 1024} KB, "
          f"{kpis['total']} runs/determinations, {len(payload['rows'])} rows, "
          f"{len(payload['docs'])} docs)")
    return output_path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>CDS Determinations Committees — Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root { --bg:#0f1620; --card:#172230; --ink:#e8eef5; --muted:#8aa0b6; --accent:#3aa0ff;
          --green:#37c98b; --amber:#f5a623; --line:#243245; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  header { padding:24px 32px 4px; }
  h1 { margin:0; font-size:23px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  .wrap { padding:14px 32px 56px; max-width:1280px; margin:0 auto; }
  .banner { padding:10px 14px; border-radius:8px; font-size:13px; margin:12px 0 14px; }
  .banner.warn { background:#3a2e12; color:#ffd58a; border:1px solid #6b531f; }
  .banner.ok { background:#143524; color:#8af0b8; border:1px solid #1f6b46; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin-bottom:16px; }
  .kpi { background:var(--card); border-radius:12px; padding:14px 16px; }
  .kpi .v { font-size:22px; font-weight:650; } .kpi .l { color:var(--muted); font-size:11px;
    margin-top:4px; text-transform:uppercase; letter-spacing:.5px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  .card { background:var(--card); border-radius:12px; padding:14px 16px 10px; margin-bottom:16px; }
  .card h3 { margin:4px 6px 10px; font-size:14px; font-weight:600; color:#cdd8e4; }
  .full { grid-column:1 / -1; }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th,td { text-align:left; padding:7px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--card);
       cursor:pointer; user-select:none; }
  th:hover { color:var(--ink); }
  td a { color:var(--accent); text-decoration:none; }
  .tablewrap { max-height:560px; overflow:auto; border-radius:8px; }
  tr.det { cursor:pointer; } tr.det:hover td { background:#1c2a3b; }
  tr.drawer td { white-space:normal; background:#0f1a26; padding:0; }
  .drawer-inner { padding:12px 16px; }
  .docgroup { margin:6px 0 10px; } .docgroup h4 { margin:6px 0 4px; font-size:12px;
    color:var(--accent); text-transform:uppercase; letter-spacing:.4px; }
  .docrow { font-size:12.5px; padding:3px 0; border-bottom:1px dotted #223; }
  .runsum { background:#0f2a1e; border:1px solid #1f6b46; color:#cdeede; border-radius:8px;
            padding:10px 12px; font-size:13px; line-height:1.55; margin-bottom:10px; }
  .dllinks a { margin-left:12px; font-size:12px; }
  .pill { display:inline-block; font-size:10px; padding:1px 7px; border-radius:10px; margin-left:6px;
          background:#23364a; color:#9fc4ea; } .pill.warn{ background:#4a3a12; color:#ffd58a; }
  .pill.flag{ background:#2a1f3a; color:#c9a7ff; }
  select,button,input,textarea { background:#0f1620; color:var(--ink); border:1px solid #2c3c50;
                  border-radius:8px; padding:8px 10px; font-size:13px; font-family:inherit; }
  button { cursor:pointer; } button:hover { border-color:var(--accent); }
  a.btn { display:inline-block; background:#0f1620; color:var(--ink); border:1px solid #2c3c50;
          border-radius:8px; padding:8px 10px; font-size:13px; text-decoration:none; cursor:pointer; }
  a.btn:hover { border-color:var(--accent); }
  a.btn#dlCredit { background:var(--accent); color:#04243f; border-color:var(--accent); font-weight:600; }
  button.primary { background:var(--accent); color:#04243f; border-color:var(--accent); font-weight:600; }
  .controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:0 6px 12px; }
  .controls label { color:var(--muted); font-size:12px; margin-right:2px; }
  .answers { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; margin:0 6px 10px; }
  .ans { background:#0f1a26; border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
  .ans .q { color:var(--muted); font-size:11.5px; } .ans .a { font-size:16px; font-weight:600; margin-top:3px; }
  .chips { display:flex; gap:8px; flex-wrap:wrap; margin:6px 6px 10px; }
  .chip { font-size:12px; padding:4px 10px; border-radius:14px; background:#13202e;
          border:1px solid #2c3c50; cursor:pointer; } .chip:hover{ border-color:var(--accent); }
  #askBox { width:100%; min-height:56px; resize:vertical; }
  #answer { white-space:pre-wrap; line-height:1.5; font-size:14px; margin:10px 6px;
            background:#0f1a26; border:1px solid var(--line); border-radius:10px; padding:14px; min-height:20px; }
  .cite { font-size:12px; color:var(--muted); margin:4px 6px; }
  .cite a{ color:var(--accent); }
  mark { background:#5a4a14; color:#ffe9a8; padding:0 2px; border-radius:3px; }
  .meta { color:var(--muted); font-size:12px; }
  footer { color:var(--muted); font-size:12px; padding:0 32px 32px; max-width:1280px; margin:0 auto; }
  @media (max-width:820px){ .grid{grid-template-columns:1fr;} th,td{white-space:normal;} }
</style>
</head>
<body>
<header>
  <h1>Credit Derivatives Determinations Committees</h1>
  <div class="sub">Determinations tracker · source: cdsdeterminationscommittees.org · auctions: creditfixings.com</div>
</header>
<div class="wrap">
  <div id="banner" class="banner"></div>
  <div class="kpis" id="kpis"></div>

  <!-- ── Ask the data (free-text, unlimited) ─────────────────────────────── -->
  <div class="card full">
    <h3>💬 Ask the data</h3>
    <div class="answers" id="answers"></div>
    <div class="controls">
      <textarea id="askBox" placeholder="Ask anything about the determinations and the underlying documents — e.g. &quot;When did the EMEA DC exercise discretion under the Rules?&quot;, &quot;Which entities involved lock-up agreements?&quot;, &quot;Show external review cases&quot;"></textarea>
    </div>
    <div class="chips" id="chips"></div>
    <div class="controls">
      <button class="primary" id="askBtn">Ask</button>
      <span class="meta" id="askMeta"></span>
    </div>
    <div id="answer"></div>
    <div id="cites"></div>
  </div>

  <!-- ── Filters ──────────────────────────────────────────────────────────── -->
  <div class="card full">
    <h3>Filter determinations</h3>
    <div class="controls">
      <span><label>Committee</label><select id="fCommittee"></select></span>
      <span><label>Credit event</label><select id="fEvent"></select></span>
      <span><label>Decision</label><select id="fDecision"></select></span>
      <span><label>From year</label><select id="fYearLo"></select></span>
      <span><label>To year</label><select id="fYearHi"></select></span>
      <span><label>Entity</label><input id="fEntity" placeholder="name contains…" size="18"></span>
      <span><label>Notable</label><select id="fFlag"></select></span>
      <button id="resetBtn">Reset</button>
      <span class="meta" id="filterCount"></span>
    </div>
  </div>

  <!-- ── Charts (react to filters) ────────────────────────────────────────── -->
  <div class="grid">
    <div class="card"><h3>Determinations per year</h3><div id="byYear" style="height:300px"></div></div>
    <div class="card"><h3>By committee region</h3><div id="byRegion" style="height:300px"></div></div>
  </div>
  <div class="grid">
    <div class="card"><h3>By credit-event type</h3><div id="byEvent" style="height:300px"></div></div>
    <div class="card"><h3>Avg auction final price (recovery) by event</h3><div id="byRecovery" style="height:300px"></div></div>
  </div>

  <!-- ── Determinations table + document drawers ─────────────────────────── -->
  <div class="card full">
    <h3>Determinations <span class="meta">— click a row for its documents (decisions, explanatory statements, pro-forma ASTs, final lists…)</span></h3>
    <div class="controls"><a id="dlCredit" class="btn" href="credit_events.csv" download>⬇ All Credit Events (CSV)</a><a id="dlCreditX" class="btn" href="credit_events.xlsx" download>⬇ All Credit Events (XLSX)</a><button id="dlCsv">⬇ Filtered CSV</button><button id="dlJson">⬇ Analytics JSON</button></div>
    <div class="tablewrap"><table id="tbl"><thead><tr id="thead"></tr></thead><tbody id="tbody"></tbody></table></div>
  </div>
</div>
<footer>
  <span id="status"></span> · Generated <span id="gen"></span> ·
  <button id="updateBtn">↻ Update data</button> <span class="meta" id="updateMeta"></span>
</footer>

<script>
const DATA = /*__DATA__*/;
const API = "api/";  // served at /cds/api/ behind the same Caddy gate
const fmtNum = n => (n==null?'—':Number(n).toLocaleString());
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// ── header / KPIs / answers ──────────────────────────────────────────────────
const b=document.getElementById('banner'); b.textContent=DATA.banner.text; b.classList.add(DATA.banner.cls);
document.getElementById('gen').textContent=DATA.generated;
const k=DATA.kpis;
document.getElementById('kpis').innerHTML=[
  ['Determinations',fmtNum(k.total)],['Reference entities',fmtNum(k.entities)],
  ['Credit events',fmtNum(k.credit_events)],['Documents',fmtNum((DATA.meta||{}).n_documents)],
  ['Earliest',k.date_min||'—'],['Latest',k.date_max||'—'],
].map(([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
document.getElementById('answers').innerHTML=DATA.answers.map(a=>
  `<div class="ans"><div class="q">${esc(a.label)}</div><div class="a">${esc(a.value)}</div></div>`).join('');

// ── filter controls ──────────────────────────────────────────────────────────
const ROWS=DATA.rows;
const uniq=(arr)=>[...new Set(arr.filter(v=>v!=null&&v!==''))];
const years=uniq(ROWS.map(r=>r.year)).map(Number).sort((a,b)=>a-b);
function fill(sel,vals,all='All'){ const e=document.getElementById(sel);
  e.innerHTML=`<option value="">${all}</option>`+vals.map(v=>`<option>${esc(v)}</option>`).join(''); }
fill('fCommittee',uniq(ROWS.map(r=>r.committee)).sort());
fill('fEvent',uniq(ROWS.map(r=>r.credit_event_type)).sort());
fill('fDecision',uniq(ROWS.map(r=>r.decision)).sort());
const FLAG_LABELS={discretion_under_rules:'Discretion under the Rules',external_review:'External review',
  lock_up:'Lock-up',restructuring:'Restructuring',deliverable_obligations:'Deliverable obligations',
  collective_action:'Collective action clause',succession:'Succession'};
fill('fFlag',Object.keys(FLAG_LABELS).map(f=>f));
document.querySelectorAll('#fFlag option').forEach(o=>{ if(o.value) o.textContent=FLAG_LABELS[o.value]||o.value; });
const yl=document.getElementById('fYearLo'), yh=document.getElementById('fYearHi');
yl.innerHTML='<option value="">earliest</option>'+years.map(y=>`<option>${y}</option>`).join('');
yh.innerHTML='<option value="">latest</option>'+years.map(y=>`<option>${y}</option>`).join('');

// entities that carry at least one doc with a given flag → for the Notable filter
const entityFlags={};
for(const d of DATA.docs){ const e=d.reference_entity; if(!e) continue;
  (d.flag_list||[]).forEach(f=>{ (entityFlags[f]=entityFlags[f]||new Set()).add(e); }); }

function currentFilters(){ return {
  committee:document.getElementById('fCommittee').value,
  event:document.getElementById('fEvent').value,
  decision:document.getElementById('fDecision').value,
  ylo:document.getElementById('fYearLo').value, yhi:document.getElementById('fYearHi').value,
  entity:document.getElementById('fEntity').value.trim().toLowerCase(),
  flag:document.getElementById('fFlag').value };
}
function applyFilters(){ const f=currentFilters();
  return ROWS.filter(r=>{
    if(f.committee && r.committee!==f.committee) return false;
    if(f.event && r.credit_event_type!==f.event) return false;
    if(f.decision && r.decision!==f.decision) return false;
    if(f.ylo && (r.year==null||r.year<+f.ylo)) return false;
    if(f.yhi && (r.year==null||r.year>+f.yhi)) return false;
    if(f.entity && !String(r.reference_entity||'').toLowerCase().includes(f.entity)) return false;
    if(f.flag){ const set=entityFlags[f.flag]; if(!set||!set.has(r.reference_entity)) return false; }
    return true; });
}

// ── charts ────────────────────────────────────────────────────────────────────
const layout={paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:'#cdd8e4'},
  margin:{t:10,r:14,b:50,l:46},showlegend:false};
const conf={displayModeBar:false,responsive:true};
function counts(rows,key,fallback){ const m={}; for(const r of rows){ const v=(r[key]==null||r[key]==='')?fallback:r[key];
  m[v]=(m[v]||0)+1;} return m; }
function drawCharts(rows){
  const yc=counts(rows.filter(r=>r.year!=null),'year',''); const yk=Object.keys(yc).map(Number).sort((a,b)=>a-b);
  Plotly.react('byYear',[{type:'bar',x:yk,y:yk.map(y=>yc[y]),marker:{color:'#3aa0ff'}}],layout,conf);
  // Committee: every real determination is made by a regional DC, so count only
  // attributed rows rather than showing a meaningless "Unknown" slice.
  const rc=counts(rows.filter(r=>r.committee),'committee','Unknown'); const rk=Object.keys(rc);
  Plotly.react('byRegion',[{type:'pie',labels:rk,values:rk.map(x=>rc[x]),hole:.55,textinfo:'label+percent',
    marker:{colors:['#3aa0ff','#37c98b','#f5a623','#c86bff','#ff6b6b','#888']}}],
    {...layout,margin:{t:10,r:10,b:10,l:10}},conf);
  // Credit-event type only applies to determinations where a credit event occurred.
  const ec=counts(rows.filter(r=>r.credit_event_type),'credit_event_type',''); const ek=Object.keys(ec).sort((a,b)=>ec[b]-ec[a]);
  Plotly.react('byEvent',[{type:'bar',x:ek,y:ek.map(x=>ec[x]),marker:{color:'#37c98b'}}],layout,conf);
  // avg recovery by event among filtered rows with a final_price
  const sums={},n={}; for(const r of rows){ if(r.final_price!=null&&r.credit_event_type){
    sums[r.credit_event_type]=(sums[r.credit_event_type]||0)+Number(r.final_price); n[r.credit_event_type]=(n[r.credit_event_type]||0)+1; } }
  const pk=Object.keys(sums);
  if(pk.length) Plotly.react('byRecovery',[{type:'bar',x:pk,y:pk.map(x=>+(sums[x]/n[x]).toFixed(2)),
    marker:{color:'#c86bff'},text:pk.map(x=>(sums[x]/n[x]).toFixed(2)),textposition:'auto'}],
    {...layout,yaxis:{range:[0,100]}},conf);
  else Plotly.react('byRecovery',[{type:'bar',x:[],y:[]}],{...layout,
    annotations:[{text:'No auction final-price data in this filter',showarrow:false,font:{color:'#8aa0b6'}}]},conf);
}

// ── table + per-row document drawer ───────────────────────────────────────────
const COLS=[['date','Date'],['committee','Committee'],['reference_entity','Reference entity'],
  ['issue_number','Issue #'],['credit_event_type','Credit event'],['decision','Outcome'],
  ['auction_held','Auction'],['auction_date','Auction date'],['final_price','Final price']];
document.getElementById('thead').innerHTML=COLS.map(([c,l])=>`<th data-c="${c}">${l}</th>`).join('')+'<th>Docs</th>';
let sortCol='date', sortDir=-1;
const KINDS=[['decision','Decisions / meeting statements'],['meeting_statement','Decisions / meeting statements'],
  ['explanatory_statement','Explanatory statements'],['auction_settlement_terms','Auction Settlement Terms'],
  ['final_list','Final lists / maturity buckets'],['participating_bidders','Participating bidders'],
  ['notice','Notices'],['auction_results','Auction results'],['auction_market_data','Auction market data'],
  ['document','Other documents']];
const GROUP_ORDER=['Decisions / meeting statements','Explanatory statements','Auction Settlement Terms',
  'Final lists / maturity buckets','Participating bidders','Notices','Auction results','Auction market data','Other documents'];
const kindGroup={}; KINDS.forEach(([k,g])=>kindGroup[k]=g);

function drawerHtml(r){
  const docs=r.documents||[];
  let html='<div class="drawer-inner">';
  if(r.summary){ html+=`<div class="runsum">📝 ${esc(r.summary)}</div>`; }
  if(r.question){ html+=`<div class="meta" style="margin:0 0 8px">DC question: ${esc(r.question)}</div>`; }
  (r.flag_list||[]).forEach(()=>{});
  if(!docs.length) return html+'<div class="meta">No source documents linked to this determination.</div></div>';
  const groups={}; for(const d of docs){ const g=kindGroup[d.doc_kind]||'Other documents'; (groups[g]=groups[g]||[]).push(d); }
  html+='<div class="meta" style="margin:2px 0 6px">Documents (download behind login):</div>';
  for(const g of GROUP_ORDER){ if(!groups[g]) continue;
    html+=`<div class="docgroup"><h4>${g}</h4>`;
    for(const d of groups[g]){
      const badges=[]; if(d.is_proforma) badges.push('<span class="pill warn">pro-forma</span>');
      if(d.is_blackline) badges.push('<span class="pill warn">blackline</span>');
      const dl=d.download?`<a href="${esc(d.download)}" download>⬇ download</a>`:'<span class="meta">not cached</span>';
      const src=d.source_url?`<a href="${esc(d.source_url)}" target="_blank" rel="noopener">source ↗</a>`:'';
      html+=`<div class="docrow">${esc(d.title||'document')} ${badges.join(' ')}`
           +`<span class="dllinks">${dl} ${src}</span></div>`;
    }
    html+='</div>';
  }
  return html+'</div>';
}
function cell(r,c){ if(c==='url') return r.url?`<a href="${esc(r.url)}" target="_blank" rel="noopener">↗</a>`:'';
  if(c==='auction_held') return r.auction_held?'✓':'';
  if(c==='final_price') return r.final_price==null?'—':Number(r.final_price).toFixed(3);
  return esc(r[c]==null?'':r[c]); }
function renderTable(rows){
  rows=[...rows].sort((a,b)=>{ let x=a[sortCol],y=b[sortCol]; if(x==null)return 1; if(y==null)return -1;
    if(typeof x==='number'&&typeof y==='number') return (x-y)*sortDir;
    return String(x).localeCompare(String(y))*sortDir; });
  const tb=document.getElementById('tbody'); tb.innerHTML='';
  rows.forEach((r,i)=>{
    const tr=document.createElement('tr'); tr.className='det';
    tr.innerHTML=COLS.map(([c])=>`<td>${cell(r,c)}</td>`).join('')
      +`<td>${r.n_documents||''}</td>`;
    tr.onclick=()=>{ const nx=tr.nextElementSibling;
      if(nx&&nx.classList.contains('drawer')){ nx.remove(); return; }
      const dr=document.createElement('tr'); dr.className='drawer';
      dr.innerHTML=`<td colspan="${COLS.length+1}">${drawerHtml(r)}</td>`;
      tr.after(dr); };
    tb.appendChild(tr);
  });
}
document.getElementById('thead').addEventListener('click',e=>{ const c=e.target.dataset.c; if(!c) return;
  if(sortCol===c) sortDir*=-1; else { sortCol=c; sortDir=1; } refresh(); });

let lastFiltered=ROWS;
function refresh(){ const rows=applyFilters(); lastFiltered=rows;
  document.getElementById('filterCount').textContent=`${rows.length} of ${ROWS.length} determinations`;
  drawCharts(rows); renderTable(rows); }
['fCommittee','fEvent','fDecision','fYearLo','fYearHi','fFlag'].forEach(id=>
  document.getElementById(id).addEventListener('change',refresh));
document.getElementById('fEntity').addEventListener('input',refresh);
document.getElementById('resetBtn').onclick=()=>{ ['fCommittee','fEvent','fDecision','fYearLo','fYearHi','fFlag'].forEach(id=>
  document.getElementById(id).value=''); document.getElementById('fEntity').value=''; refresh(); };

// ── downloads ──────────────────────────────────────────────────────────────────
function download(name,text,type){ const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([text],{type})); a.download=name; a.click(); URL.revokeObjectURL(a.href); }
function toCsv(rows){ if(!rows.length) return ''; const cols=Object.keys(rows[0]);
  const e=v=>(v==null)?'':/[",\n]/.test(String(v))?'"'+String(v).replace(/"/g,'""')+'"':String(v);
  return [cols.join(','),...rows.map(r=>cols.map(c=>e(r[c])).join(','))].join('\n'); }
document.getElementById('dlCsv').onclick=()=>download('determinations_filtered.csv',toCsv(lastFiltered),'text/csv');
document.getElementById('dlJson').onclick=()=>download('determinations_analytics.json',JSON.stringify(DATA.analytics,null,2),'application/json');

// ── Ask box: stream from the API, fall back to keyword search if offline ───────
const CHIPS=['When did the EMEA DC exercise discretion under the Rules?','Which entities involved lock-up agreements?',
  'Show any external review cases','How were Restructuring credit events handled?','What did the Hellenic Republic auction settle at?'];
document.getElementById('chips').innerHTML=CHIPS.map(c=>`<span class="chip">${esc(c)}</span>`).join('');
document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{ document.getElementById('askBox').value=c.textContent; ask(); });

function keywordFallback(q){
  const terms=q.toLowerCase().split(/\s+/).filter(t=>t.length>2);
  const scored=DATA.docs.map(d=>{ const hay=((d.title||'')+' '+(d.snippet||'')+' '+(d.reference_entity||'')+' '+(d.flag_list||[]).join(' ')).toLowerCase();
    let s=0; terms.forEach(t=>{ if(hay.includes(t)) s++; }); return {d,s}; }).filter(x=>x.s>0)
    .sort((a,b)=>b.s-a.s).slice(0,8);
  if(!scored.length) return {answer:'No matching documents found in the local index for that query.',citations:[]};
  return { answer:'**API offline — showing keyword matches from the embedded index.** The relevant documents are listed below; click through for the full text.',
    citations:scored.map((x,i)=>({n:i+1,reference_entity:x.d.reference_entity,committee:x.d.committee,
      doc_kind:x.d.doc_kind,meeting_date:x.d.meeting_date,title:x.d.title,url:x.d.url,excerpt:x.d.snippet})) };
}
function renderCites(cites){ document.getElementById('cites').innerHTML=cites.map(c=>
  `<div class="cite">[${c.n}] ${esc(c.reference_entity||'?')} · ${esc(c.committee||'?')} · ${esc(c.doc_kind||'')}${c.meeting_date?' · '+esc(c.meeting_date):''}
   ${c.url?`<a href="${esc(c.url)}" target="_blank" rel="noopener">source ↗</a>`:''}<br><span class="meta">${esc(c.excerpt||'')}</span></div>`).join(''); }

async function ask(){
  const q=document.getElementById('askBox').value.trim(); if(!q) return;
  const ans=document.getElementById('answer'), meta=document.getElementById('askMeta');
  document.getElementById('cites').innerHTML=''; ans.textContent=''; meta.textContent='thinking… (local model on the Pi — first answer can take ~30–60s)';
  try{
    const r=await fetch(API+'ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
    if(!r.ok||!r.body) throw new Error('api '+r.status);
    const reader=r.body.getReader(), dec=new TextDecoder(); let buf='';
    for(;;){ const {value,done}=await reader.read(); if(done) break; buf+=dec.decode(value,{stream:true});
      let nl; while((nl=buf.indexOf('\n'))>=0){ const line=buf.slice(0,nl); buf=buf.slice(nl+1); if(!line.trim()) continue;
        const o=JSON.parse(line);
        if(o.type==='citations') renderCites(o.citations||[]);
        else if(o.type==='token'){ ans.textContent+=o.t; }
        else if(o.type==='done'){ meta.textContent=o.model?('answered by '+o.model+' · local RAG'):''; }
      } }
  }catch(e){ const fb=keywordFallback(q); ans.innerHTML=fb.answer.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>');
    renderCites(fb.citations); meta.textContent='offline fallback'; }
}
document.getElementById('askBtn').onclick=ask;

// ── status + Update button ─────────────────────────────────────────────────────
async function loadStatus(){ try{ const r=await fetch(API+'status'); if(!r.ok) throw 0; const s=await r.json();
  document.getElementById('status').textContent=
    `Index: ${fmtNum(s.n_documents)} docs · ${fmtNum(s.n_chunks)} chunks · built ${s.index_built_at||'—'}`
    +(s.last_refresh_finished?` · last refresh ${s.last_refresh_finished}${s.last_refresh_ok===false?' (failed)':''}`:'');
  document.getElementById('updateBtn').disabled=!!s.busy;
  if(s.busy) document.getElementById('updateMeta').textContent='refresh running…';
  return s; }catch(e){ document.getElementById('status').textContent='Index status unavailable (API offline) — static view.';
  document.getElementById('updateBtn').disabled=true; return null; } }
let pollTimer=null;
document.getElementById('updateBtn').onclick=async()=>{ const m=document.getElementById('updateMeta');
  m.textContent='starting…'; try{ const r=await fetch(API+'refresh',{method:'POST'}); const j=await r.json();
    m.textContent=j.message||j.status;
    if(!pollTimer) pollTimer=setInterval(async()=>{ const s=await loadStatus(); if(s&&!s.busy){ clearInterval(pollTimer); pollTimer=null;
      m.textContent='refresh complete — reload the page to see new data.'; } },15000);
  }catch(e){ m.textContent='update unavailable (API offline)'; } };

// ── go ──────────────────────────────────────────────────────────────────────────
refresh(); loadStatus();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build static CDS dashboard")
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    build(args.input or _input_path(), args.output)
