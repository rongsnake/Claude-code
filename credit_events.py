"""
Collapse the document-level reconciled table into **one row per credit event**.

The scraper emits one row per source document, so a single credit event (e.g.
Ardagh Packaging Finance PLC, 2025) is fragmented across dozens of rows — many
with junk reference-entity names parsed out of document titles ("Ardagh Draft",
"Ardagh Er Of Facts", …). The Determinations Committees assign each credit-event
request a stable **reference number** in ``YYYYMMDDNN`` form (e.g. 2025100602)
which appears in the body text of every related document. We use that number as
the grouping key: all documents quoting the same number belong to one event.

Output: a tidy DataFrame, one row per credit event, with a canonical entity
name, committee/region (inferred when the column is blank), credit-event type,
dates, auction final price, the reference number, and the list of underlying
documents (for the dashboard's per-row drawer).

Rows that cannot be linked to a reference number (older auction-only rows, docs
with no extracted text) fall back to grouping by normalised entity + year.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
DOCUMENTS_CSV = DATA_DIR / "documents.csv"

# DC credit-event reference number: 8-digit date (YYYYMMDD) + 2-digit sequence.
REFNUM_RE = re.compile(r"\b(20\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{2})\b")

# Tokens that mark a reference_entity value as document-title noise rather than a
# real entity name — used to prefer a clean canonical name within a group.
_JUNK_TOKENS = re.compile(
    r"\b(draft|brief|exhibits?|position|facts|administrative|procedural|redline|"
    r"template|nops|challenge|response|compare|against|ast|final list|preliminary|"
    r"initial list|member|composite|isda|er|re )\b",
    re.I,
)

# Leading document-process words to strip when deriving an entity's grouping key,
# so "Procedural Ardagh Packaging Finance Plc" clusters with "Ardagh Packaging…".
_PREFIX = re.compile(
    r"^(?:dc administrative |dc |procedural |final list |initial list |preliminary |"
    r"draft |final |emea dc |americas dc |asia dc |japan dc )+",
    re.I,
)

# Trailing document-process descriptors to strip from a *display* name, so the real
# entity survives ("Altice France Dc Full Q1 Q4" → "Altice France", "New Fortress
# Energy Inc Credit Event" → "New Fortress Energy Inc"). Applied repeatedly.
_TRAILING_JUNK = re.compile(
    r"\s+(?:credit event|initial list|final list(?: of obligations)?|"
    r"preliminary(?: list)?|auction (?:timetable|checklist)|final auction checklist|"
    r"required information.*|submission of.*|asts?|latest revision|exposure draft|"
    r"dc full.*|timetable|checklist|obligations|bankruptcy|auction)$",
    re.I,
)

# Two determinations for the same entity within this many days belong to the same
# credit-event episode (covers the months-long request → auction → settlement arc).
_EPISODE_GAP_DAYS = 550


def _norm_url(u) -> str | None:
    return str(u).rstrip("/").lower() if isinstance(u, str) and u.strip() else None


def _norm_entity(name) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _region_from_text(*parts) -> str | None:
    s = " ".join(p for p in parts if p).lower()
    if "emea" in s:
        return "EMEA"
    if "americas" in s:
        return "Americas"
    if "asia ex" in s or "asia-ex" in s:
        return "Asia ex-Japan"
    if "japan" in s:
        return "Japan"
    if "australia" in s or "new zealand" in s:
        return "Australia-New Zealand"
    return None


def _doc_refnum(text_path) -> str | None:
    """The dominant (most frequent) reference number in a document's text."""
    if not (isinstance(text_path, str) and os.path.exists(text_path)):
        return None
    try:
        text = Path(text_path).read_text(errors="ignore")
    except OSError:
        return None
    nums = REFNUM_RE.findall(text)
    return Counter(nums).most_common(1)[0][0] if nums else None


def _doc_record(d: pd.Series) -> dict:
    title = str(d.get("doc_title") or "").strip()
    lp = d.get("local_path")
    download = ("docs/" + os.path.basename(str(lp))) if isinstance(lp, str) and lp else None
    tl = title.lower()
    return {
        "doc_kind": d.get("doc_kind") or "document",
        "title": title or "document",
        "source_url": d.get("file_url") or d.get("source_page"),
        "download": download,
        "is_proforma": ("pro forma" in tl) or ("pro-forma" in tl) or ("proforma" in tl),
        "is_blackline": ("blackline" in tl) or ("redline" in tl),
        "committee": d.get("committee") if pd.notna(d.get("committee")) else None,
    }


def load_documents() -> pd.DataFrame:
    return pd.read_csv(DOCUMENTS_CSV) if DOCUMENTS_CSV.exists() else pd.DataFrame()


def _build_doc_index(docs: pd.DataFrame):
    """Return (url->refnum, refnum->[doc records], refnum->committee, url->doc record)."""
    url2ref: dict[str, str] = {}
    ref_docs: dict[str, list] = defaultdict(list)
    url2doc: dict[str, dict] = {}
    if docs.empty:
        return url2ref, ref_docs, {}, url2doc
    for _, d in docs.iterrows():
        rec = _doc_record(d)
        for u in (d.get("file_url"), d.get("source_page")):
            n = _norm_url(u)
            if n:
                url2doc.setdefault(n, rec)
        ref = _doc_refnum(d.get("text_path"))
        if not ref:
            continue
        ref_docs[ref].append(rec)
        for u in (d.get("file_url"), d.get("source_page")):
            n = _norm_url(u)
            if n:
                url2ref.setdefault(n, ref)
    ref_committee = {}
    for ref, dl in ref_docs.items():
        comms = [r["committee"] for r in dl if r.get("committee")]
        if comms:
            ref_committee[ref] = Counter(comms).most_common(1)[0][0]
    return url2ref, ref_docs, ref_committee, url2doc


def _clean_key(name) -> str:
    """Entity grouping key: lowercase, drop document-process prefixes/noise."""
    n = _norm_entity(name)
    n = _PREFIX.sub("", n)
    n = _JUNK_TOKENS.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def _canonical_entity(values: list[str]) -> str:
    """Pick the cleanest, most representative entity name from a group."""
    vals = [v for v in values if isinstance(v, str) and v.strip()]
    if not vals:
        return "Unknown entity"
    counts = Counter(_norm_entity(v) for v in vals)
    # Prefer the most frequent name that is not document-title noise; fall back to
    # plain most-frequent if every variant looks noisy.
    clean = [(n, c) for n, c in counts.items() if not _JUNK_TOKENS.search(n)]
    best_norm = max(clean or counts.items(), key=lambda kv: (kv[1], len(kv[0])))[0]
    # Display the longest original-casing variant of the chosen name, then peel off
    # any trailing document-process descriptors so the real entity name survives.
    display = max((v for v in vals if _norm_entity(v) == best_norm), key=len)
    prev = None
    while prev != display:
        prev = display
        display = _TRAILING_JUNK.sub("", display).strip()
    display = display or prev  # never strip the name away to nothing
    return re.sub(r"\bplc\b", "PLC", display, flags=re.I)


def _first(series: pd.Series):
    s = series.dropna()
    return s.iloc[0] if len(s) else None


def _mode(series: pd.Series):
    s = series.dropna()
    return s.mode().iloc[0] if len(s) else None


def _aggregate(g: pd.DataFrame, refs: list[str], ref_docs, ref_committee,
               url2doc, docs_attached) -> tuple[dict, list]:
    """Build one credit-event record + its document list from a group of rows."""
    entity = _canonical_entity(list(g["reference_entity"]))
    primary_ref = (max(refs, key=lambda r: len(ref_docs.get(r, []))) if refs else None)

    committee = _mode(g["committee"])
    if not committee:
        for r in refs:
            if ref_committee.get(r):
                committee = ref_committee[r]
                break
    if not committee:
        committee = _region_from_text(
            " ".join(str(u) for u in g["url"].dropna()),
            " ".join(str(t) for t in g.get("title", pd.Series(dtype=str)).dropna()),
            entity,
        )
    committee = committee or "Unspecified"

    cet = _mode(g["credit_event_type"])
    decisions = g["decision"].dropna().astype(str)
    decision = next((d for d in decisions if "credit event" in d.lower()),
                    decisions.iloc[0] if len(decisions) else None)
    final_price = _first(g["final_price"].dropna())
    auction_date = g["auction_date"].dropna().max() if "auction_date" in g else pd.NaT
    auction_held = bool(g.get("auction_held", pd.Series(dtype=bool)).fillna(False).any()) \
        or pd.notna(final_price)
    ce_rows = g[g["credit_event_type"].notna()]
    event_date = (ce_rows["date"].min() if len(ce_rows) else g["date"].min())
    occurred = (
        bool(decision and re.search(r"credit event occurred|auction", decision, re.I))
        or auction_held or pd.notna(final_price)
    )
    url = _first(ce_rows["url"]) if len(ce_rows) else _first(g["url"])

    # Documents: those quoting any of the episode's reference numbers, plus any
    # number-less rows attached to this episode, matched back to the manifest.
    docs_out, seen = [], set()
    for r in refs:
        for rec in ref_docs.get(r, []):
            kdoc = rec.get("download") or rec.get("source_url")
            if kdoc and kdoc not in seen:
                seen.add(kdoc); docs_out.append(rec)
    for u in list(g["url"].dropna()) + docs_attached:
        rec = url2doc.get(_norm_url(u))
        if rec:
            kdoc = rec.get("download") or rec.get("source_url")
            if kdoc and kdoc not in seen:
                seen.add(kdoc); docs_out.append(rec)

    record = {
        "credit_event_ref": primary_ref,
        "date": event_date,
        "year": int(event_date.year) if pd.notna(event_date) else None,
        "reference_entity": entity,
        "committee": committee,
        "credit_event_type": cet,
        "decision": decision,
        "credit_event_occurred": occurred,
        "issue_number": _mode(g["issue_number"]),
        "auction_held": auction_held,
        "auction_date": auction_date,
        "final_price": round(float(final_price), 3) if pd.notna(final_price) else None,
        "currency": _first(g.get("currency", pd.Series(dtype=str))),
        "transaction_type": _first(g.get("transaction_type", pd.Series(dtype=str))),
        "ticker": _first(g.get("ticker", pd.Series(dtype=str))),
        "days_to_auction": (
            int((auction_date - event_date).days)
            if pd.notna(auction_date) and pd.notna(event_date) else None
        ),
        "source": _first(g.get("source", pd.Series(dtype=str))),
        "url": url,
        "auction_url": _first(g.get("auction_url", pd.Series(dtype=str))),
        "n_requests": len(refs),
        "n_documents": len(docs_out),
    }
    return record, docs_out


def build_credit_events(rec: pd.DataFrame, docs: pd.DataFrame | None = None):
    """Collapse reconciled rows into one row per credit event.

    A credit event is an entity's determination *episode*: all DC request numbers
    for that entity within ~18 months, plus the matched auction, plus the loose
    supporting documents that name it. Returns (events_df, drawer) where drawer
    maps an event's reference number (or synthetic key) to its document list.
    """
    if docs is None:
        docs = load_documents()
    url2ref, ref_docs, ref_committee, url2doc = _build_doc_index(docs)

    rec = rec.copy()
    rec["date"] = pd.to_datetime(rec.get("date"), errors="coerce")
    if "auction_date" in rec.columns:
        rec["auction_date"] = pd.to_datetime(rec["auction_date"], errors="coerce")
    rec["final_price"] = pd.to_numeric(rec.get("final_price"), errors="coerce")
    rec["_ref"] = rec["url"].map(lambda u: url2ref.get(_norm_url(u)))

    # Canonical clean entity per reference number (from the rows that carry it).
    ref_entity = {}
    for ref, g in rec[rec["_ref"].notna()].groupby("_ref"):
        ref_entity[ref] = _clean_key(_canonical_entity(list(g["reference_entity"])))

    # A row has substance (is part of a credit event) if it has a reference
    # number, a credit-event type, or an auction price. Everything else is a
    # loose supporting document, attached to an episode afterwards.
    def has_event(r):
        return isinstance(r["_ref"], str) or pd.notna(r["credit_event_type"]) \
            or pd.notna(r["final_price"])

    rec["_has_event"] = rec.apply(has_event, axis=1)

    # Fold a number-less row (an auction-only or loose row, e.g. "Nfe Financing")
    # into a reference-numbered entity whose key it is a prefix of, so it doesn't
    # spawn a near-duplicate episode beside "NFE Financing LLC".
    ref_keys = set(ref_entity.values())

    def _resolve_key(r):
        if isinstance(r["_ref"], str):
            return ref_entity.get(r["_ref"])
        k = _clean_key(r["reference_entity"])
        if k and k not in ref_keys:
            cand = [rk for rk in ref_keys
                    if rk.startswith(k + " ") or k.startswith(rk + " ")]
            if len(cand) == 1:
                return cand[0]
        return k

    rec["_ekey"] = rec.apply(_resolve_key, axis=1)

    core = rec[rec["_has_event"] & rec["_ekey"].astype(bool)].copy()
    loose = rec[~rec.index.isin(core.index)].copy()

    # Episode clustering: within an entity, split where the gap between successive
    # determinations exceeds the episode window.
    episodes = []  # list of (ekey, [row indices])
    for ekey, g in core.groupby("_ekey"):
        g = g.sort_values("date")
        cur, last = [], None
        for idx, row in g.iterrows():
            d = row["date"]
            if last is not None and pd.notna(d) and pd.notna(last) \
                    and (d - last).days > _EPISODE_GAP_DAYS:
                episodes.append((ekey, cur)); cur = []
            cur.append(idx)
            if pd.notna(d):
                last = d
        if cur:
            episodes.append((ekey, cur))

    # Index episodes by ekey with their date span, to attach loose docs.
    ep_spans = []
    for i, (ekey, idxs) in enumerate(episodes):
        dts = core.loc[idxs, "date"].dropna()
        ep_spans.append((ekey, dts.min() if len(dts) else None,
                         dts.max() if len(dts) else None, i))

    attach = defaultdict(list)  # episode index -> [urls of loose docs]
    for _, lr in loose.iterrows():
        ek, d, u = lr["_ekey"], lr["date"], lr["url"]
        if not ek or not isinstance(u, str):
            continue
        best = None
        for (sek, lo, hi, i) in ep_spans:
            if sek != ek:
                continue
            if pd.notna(d) and lo is not None and hi is not None:
                if lo - pd.Timedelta(days=120) <= d <= hi + pd.Timedelta(days=120):
                    best = i; break
            else:
                best = i
        if best is not None:
            attach[best].append(u)

    events, drawer = [], {}
    for i, (ekey, idxs) in enumerate(episodes):
        g = core.loc[idxs]
        refs = sorted(set(g["_ref"].dropna()))
        record, docs_out = _aggregate(
            g, refs, ref_docs, ref_committee, url2doc, attach.get(i, []))
        dkey = record["credit_event_ref"] or f"ev::{i}"
        record["_key"] = dkey
        events.append(record)
        drawer[dkey] = docs_out

    ev = pd.DataFrame(events)
    if not ev.empty:
        # A credit *event* requires a determined outcome: the DC found a credit
        # event occurred, classified an event type, or an auction settled (a
        # final price exists). This mirrors the dashboard's own credit-event mask
        # and drops process-document phantoms (orphaned exposure-draft / SRO-rules
        # titles parsed as if they were reference entities) that carry no outcome.
        is_event = (
            ev["credit_event_occurred"].fillna(False).astype(bool)
            | ev["credit_event_type"].notna()
            | ev["final_price"].notna()
        )
        ev = ev[is_event]
        ev = ev.sort_values("date", ascending=False, na_position="last").reset_index(drop=True)
    return ev, drawer


if __name__ == "__main__":
    import analytics
    rec = pd.read_csv(analytics.default_input())
    ev, drawer = build_credit_events(rec)
    print(f"{len(rec)} reconciled rows -> {len(ev)} credit events")
    print("committee:", dict(ev["committee"].value_counts()))
    print("with ref number:", int(ev["credit_event_ref"].notna().sum()))
    print("credit_event_type set:", int(ev["credit_event_type"].notna().sum()))
    print("final_price set:", int(ev["final_price"].notna().sum()))
    print("year range:", int(ev["year"].min()), "-", int(ev["year"].max()))
