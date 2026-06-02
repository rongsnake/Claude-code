"""
Group the downloaded DC documents into **determination runs** and build a concise
**extractive** (no-LLM) summary of each run from its meeting statement / decision.

A "run" is one determination episode for a reference entity: the decision /
meeting statement plus its supporting documents (auction settlement terms, final
list of deliverable obligations, list of participating bidders, results, …). We
key runs on the DC `Issue Number` when present (the canonical identifier), else on
(normalised entity, year).

This module is offline. It consumes the per-document records that
`build_index.build_manifest()` already produces (entity / committee / meeting date
/ issue / vote / qualitative flags parsed from each doc's text) and re-reads the
full extracted text of each run's canonical document for a few extra fields. It is
imported by `build_index.py`; nothing here scrapes or calls an LLM.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from cds_dc_scraper import CREDIT_EVENTS, _classify

DATA_DIR = Path("data")
TEXT_DIR = DATA_DIR / "doctext"

# Order of preference for the doc we read to summarise a run.
_CANONICAL_KIND_ORDER = [
    "meeting_statement", "explanatory_statement", "statement", "decision",
    "final_list", "participating_bidders", "auction_results", "auction_settlement_terms",
]

# Resolution / outcome cues, most specific first.
_RESOLUTION_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bno\b[^.]{0,40}\bcredit event\b[^.]{0,40}(occurr|has occurr)", re.I),
     "No credit event occurred"),
    (re.compile(r"credit event[^.]{0,40}(has occurred|occurred|did occur)", re.I),
     "Credit event occurred"),
    (re.compile(r"\bdetermined\b[^.]{0,60}\bauction\b", re.I), "Auction to be held"),
    (re.compile(r"question[^.]{0,40}(dismiss|reject|not[^.]{0,10}accept)", re.I),
     "Question dismissed"),
    (re.compile(r"\b(succession|successor)\b", re.I), "Succession determined"),
    (re.compile(r"substitute[^.]{0,30}reference obligation", re.I),
     "Substitute reference obligation"),
    (re.compile(r"\bresolved\b", re.I), "Resolved"),
]

_QUESTION_RE = re.compile(r"(whether[^?]{10,260}\?)", re.I)
_REQUEST_DATE_RE = re.compile(
    r"(?:request(?:ed)?|submitted)[^.]{0,40}?(\d{1,2}\s+[A-Za-z]+\s+20\d{2}|"
    r"[A-Za-z]+\s+\d{1,2},\s*20\d{2}|20\d{2}-\d{2}-\d{2})", re.I)
_AUCTION_DATE_RE = re.compile(
    r"auction[^.]{0,40}?(\d{1,2}\s+[A-Za-z]+\s+20\d{2}|[A-Za-z]+\s+\d{1,2},\s*20\d{2}|"
    r"20\d{2}-\d{2}-\d{2})", re.I)

_FLAG_LABELS = {
    "discretion_under_rules": "DC exercised discretion under the Rules",
    "external_review": "external review",
    "lock_up": "lock-up",
    "restructuring": "restructuring credit event",
    "deliverable_obligations": "deliverable-obligations list",
    "collective_action": "collective action clause",
    "succession": "succession",
}


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(the|inc|llc|ltd|plc|corp|corporation|company|co|sa|nv|ag|group|limited|holdings?)\b",
               " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _full_text(doc_id: str) -> str:
    tp = TEXT_DIR / f"{doc_id}.txt"
    return tp.read_text(errors="replace") if doc_id and tp.exists() else ""


def _year_of(*vals: str | None) -> str:
    for v in vals:
        if v:
            m = re.search(r"20\d{2}", str(v))
            if m:
                return m.group(0)
    return ""


def _run_key(doc: dict) -> tuple[str, str]:
    """(kind, key): prefer the DC issue number, else (normalised entity, year)."""
    issue = str(doc.get("issue_number") or "").strip()
    if issue and len(issue) >= 6:
        return ("issue", issue)
    ent = _norm(doc.get("reference_entity") or "")
    yr = _year_of(doc.get("meeting_date"))
    return ("entity", f"{ent}|{yr}") if ent else ("orphan", doc.get("doc_id", ""))


def _resolution(text: str) -> str | None:
    for pat, label in _RESOLUTION_RULES:
        if pat.search(text):
            return label
    return None


def _recovery_for(entity: str, recon: pd.DataFrame | None) -> dict:
    """Auction final price / date for the entity from the reconciled table."""
    if recon is None or recon.empty or not entity:
        return {}
    ne = _norm(entity)
    for _, r in recon.iterrows():
        if _norm(str(r.get("reference_entity") or "")) == ne:
            fp = r.get("final_price")
            ad = r.get("auction_date")
            out = {}
            if pd.notna(fp) and str(fp).strip():
                try:
                    out["final_price"] = float(fp)
                except (TypeError, ValueError):
                    pass
            if pd.notna(ad) and str(ad).strip():
                out["auction_date"] = str(ad)[:10]
            if out:
                return out
    return {}


def _doc_link(doc: dict) -> dict:
    """A download entry for the dropdown: gated local copy if we have the file,
    else the source URL."""
    local = doc.get("local_path") or ""
    name = Path(local).name if local else ""
    return {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "doc_kind": doc.get("doc_kind"),
        "is_proforma": doc.get("is_proforma"),
        "is_blackline": doc.get("is_blackline"),
        "download": f"/cds/docs/{name}" if name else None,
        "source_url": doc.get("url"),
    }


def _summarise(entity: str, committee: str | None, docs: list[dict],
               recon: pd.DataFrame | None) -> dict:
    # canonical doc = best available kind for narrative detail
    by_kind = {d.get("doc_kind"): d for d in docs}
    canonical = next((by_kind[k] for k in _CANONICAL_KIND_ORDER if k in by_kind), docs[0])
    text = _full_text(canonical.get("doc_id", ""))

    credit_event = (_classify(text[:6000], CREDIT_EVENTS)
                    or next((d.get("doc_kind") and _classify(d.get("title", ""), CREDIT_EVENTS)
                             for d in docs if _classify(d.get("title", ""), CREDIT_EVENTS)), None))
    resolution = _resolution(text)
    meeting_date = next((d.get("meeting_date") for d in docs if d.get("meeting_date")), None)
    issue_number = next((d.get("issue_number") for d in docs if d.get("issue_number")), None)
    vote = next((d.get("vote_result") for d in docs if d.get("vote_result")), None)
    qm = _QUESTION_RE.search(text)
    question = re.sub(r"\s+", " ", qm.group(1)).strip()[:300] if qm else None
    rq = _REQUEST_DATE_RE.search(text)
    request_date = rq.group(1) if rq else None
    aq = _AUCTION_DATE_RE.search(text)
    auction_date_txt = aq.group(1) if aq else None

    flags = sorted({f for d in docs for f in (d.get("flag_list") or [])})
    recovery = _recovery_for(entity, recon)

    # ── extractive narrative ──
    parts: list[str] = []
    head = entity or "Unattributed determination"
    if committee:
        head += f" — {committee} Determinations Committee"
    parts.append(head + ".")
    if credit_event:
        parts.append(f"Credit event type: {credit_event}.")
    if meeting_date:
        parts.append(f"Meeting date {meeting_date}.")
    if request_date:
        parts.append(f"Request {request_date}.")
    if resolution:
        parts.append(f"Outcome: {resolution}.")
    if vote:
        parts.append(f"Vote: {vote.strip()}.")
    if recovery.get("final_price") is not None:
        ad = recovery.get("auction_date")
        parts.append(f"Settlement auction final price {recovery['final_price']:.3f}"
                     + (f" ({ad})." if ad else "."))
    elif auction_date_txt:
        parts.append(f"Auction referenced {auction_date_txt}.")
    if flags:
        parts.append("Notable: " + ", ".join(_FLAG_LABELS.get(f, f) for f in flags) + ".")
    parts.append(f"{len(docs)} document(s) on file.")

    return {
        "reference_entity": entity or None,
        "committee": committee,
        "credit_event_type": credit_event,
        "issue_number": issue_number,
        "meeting_date": meeting_date,
        "request_date": request_date,
        "auction_date": recovery.get("auction_date") or (
            _to_iso_loose(auction_date_txt) if auction_date_txt else None),
        "final_price": recovery.get("final_price"),
        "resolution": resolution,
        "vote_result": vote.strip() if vote else None,
        "question": question,
        "flags": flags,
        "summary": " ".join(parts),
        "summary_kind": "extractive",
        "based_on": {"doc_id": canonical.get("doc_id"), "doc_kind": canonical.get("doc_kind"),
                     "title": canonical.get("title")},
        "documents": [_doc_link(d) for d in sorted(
            docs, key=lambda d: _CANONICAL_KIND_ORDER.index(d.get("doc_kind"))
            if d.get("doc_kind") in _CANONICAL_KIND_ORDER else 99)],
        "n_documents": len(docs),
    }


def _to_iso_loose(token: str | None) -> str | None:
    if not token:
        return None
    from datetime import datetime
    for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(token.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def build_runs(docs: list[dict], recon: pd.DataFrame | None = None) -> list[dict]:
    """Group `docs` (from build_index.build_manifest) into determination runs and
    attach an extractive summary + download list to each. Sorted newest first."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for d in docs:
        groups.setdefault(_run_key(d), []).append(d)

    runs: list[dict] = []
    for (ktype, key), ds in groups.items():
        entity = next((d.get("reference_entity") for d in ds if d.get("reference_entity")), None)
        committee = next((d.get("committee") for d in ds if d.get("committee")), None)
        run = _summarise(entity or "", committee, ds, recon)
        run["run_id"] = f"{ktype}:{key}"
        runs.append(run)

    runs.sort(key=lambda r: (r.get("meeting_date") or r.get("auction_date") or ""), reverse=True)
    return runs
