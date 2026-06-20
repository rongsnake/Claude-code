"""
Build the data/index/ artifacts that power the richer dashboard and the local
Q&A API.

This is an **offline** builder (no scraping) — run it after the scrapers +
fetch_docs.py + analytics.py. It turns the scraped tables and the downloaded
document corpus (data/docs/ + extracted text in data/doctext/) into:

    data/index/determinations_clean.csv   enriched + cleaned determinations table
    data/index/documents.json             one record per source document, with
                                           doc_kind, the entity/committee/meeting
                                           date/issue/vote parsed from its text,
                                           qualitative flags (discretion under the
                                           Rules, external review, lock-up, …), a
                                           snippet, and a click-through URL
    data/index/entity_docs.json            documents grouped by reference entity
                                           (drives the per-row document drawer)
    data/index/chunks.json                 retrieval chunks for RAG
    data/index/embeddings.npy              float32 matrix of chunk embeddings
    data/index/index_meta.json             counts + build timestamp (for /status)

Document provenance: if data/documents.csv exists (written by fetch_docs.py after
a live crawl) it is used as the source of truth — it carries the real file_url and
reference_entity per document. Otherwise we fall back to scanning data/docs/ +
data/doctext/ locally and reconstruct as much as we can (linking each document to
the source page of its matched determination).

Usage:
    python build_index.py                 # full build incl. embeddings
    python build_index.py --no-embed       # skip Ollama embeddings (fast, for tests)
    python build_index.py --limit-embed 200  # cap chunks embedded (debug)
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import analytics
import summaries
from fetch_docs import classify_kind  # reuse the proven URL/text kind classifier

DATA_DIR = Path("data")
DOCS_DIR = DATA_DIR / "docs"
TEXT_DIR = DATA_DIR / "doctext"
MANIFEST_CSV = DATA_DIR / "documents.csv"
INDEX_DIR = DATA_DIR / "index"

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
CHUNK_CHARS = 900
CHUNK_OVERLAP = 150
# The full archive is thousands of docs; embedding every chunk on a Pi takes hours.
# Summaries are extractive (no embeddings), so cap RAG embedding by default — the
# Ask box still works over the most recent subset. Override with --limit-embed.
MAX_EMBED_CHUNKS = 6000
DC_DOCS_BASE = "https://www.cdsdeterminationscommittees.org/docs/"

# Committee canonicalisation — the raw table has a few header-artefact rows
# (a literal "committee", blanks) we drop, and we normalise spellings.
VALID_COMMITTEES = {
    "americas": "Americas", "emea": "EMEA", "asia ex-japan": "Asia ex-Japan",
    "asia ex japan": "Asia ex-Japan", "aej": "Asia ex-Japan", "japan": "Japan",
    "australia-new zealand": "Australia-New Zealand",
    "australia new zealand": "Australia-New Zealand", "anz": "Australia-New Zealand",
    "all dcs": "All DCs", "all dc": "All DCs",
}


# ── qualitative flag detectors ────────────────────────────────────────────────
# Each flag is (label, compiled regex). The search box queries the live text too,
# but these precomputed flags drive the quick-filter chips and the doc drawer.
FLAG_PATTERNS: dict[str, re.Pattern] = {
    "discretion_under_rules": re.compile(
        r"exercis\w+\s+(?:its\s+)?discretion|discretion\s+(?:under|pursuant)|"
        r"\bDC\s+Rules\b|determinations?\s+committee\s+rules", re.I),
    "external_review": re.compile(r"external\s+review(?:er)?|review\s+panel", re.I),
    "lock_up": re.compile(r"lock[\s-]?up|locked[\s-]?up", re.I),
    "restructuring": re.compile(r"restructuring\s+credit\s+event|\brestructuring\b", re.I),
    "deliverable_obligations": re.compile(r"deliverable\s+obligation|list\s+of\s+deliverable", re.I),
    "collective_action": re.compile(r"collective\s+action\s+clause|\bCAC\b", re.I),
    "succession": re.compile(r"succession\s+event|successor", re.I),
}

# Header fields the DC writes at the top of decision/statement docs.
RE_COMMITTEE = re.compile(r"Determinations Committee:\s*([A-Za-z][\w \-/]+)", re.I)
RE_MEETING = re.compile(r"Meeting Date:\s*([A-Za-z0-9 ,/]+)", re.I)
RE_ISSUE = re.compile(r"Issue Number:\s*([0-9A-Za-z]+)", re.I)
RE_VOTE = re.compile(r"Vote result:\s*([A-Za-z/ ]+)", re.I)


def _norm(s: str) -> str:
    """Normalise an entity name for fuzzy matching."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(the|inc|llc|ltd|plc|corp|corporation|company|co|sa|nv|ag|group|limited|holdings?)\b",
               " ", s)
    return re.sub(r"\s+", " ", s).strip()


def refine_kind(url: str, title: str, text: str) -> tuple[str, bool, bool]:
    """Return (doc_kind, is_proforma, is_blackline). Builds on classify_kind."""
    hay = f"{url} {title}".lower()
    base = classify_kind(url, title)
    is_blackline = bool(re.search(r"redline|blackline|comparison|black-?line|dvcomparison", hay))
    is_proforma = is_blackline or bool(re.search(r"form of|proposed|pro[\s-]?forma|draft", hay))
    if "explanatory" in hay or "explanatory statement" in (text or "").lower()[:400]:
        return "explanatory_statement", is_proforma, is_blackline
    if re.search(r"participating[\s_]*bidder", hay):
        return "participating_bidders", is_proforma, is_blackline
    if re.search(r"final[\s_]*list|preliminary[\s_]*list|supplemental[\s_]*list|maturity[\s_]*bucket", hay):
        return "final_list", is_proforma, is_blackline
    if base == "statement":
        return "meeting_statement", is_proforma, is_blackline
    return base, is_proforma, is_blackline


def _read_text_for(sha: str, text_path: object = None) -> str:
    # text_path comes from a CSV cell, so an empty value arrives as NaN (a float),
    # not None/"". Coerce to a real path string before touching the filesystem.
    tp_str = str(text_path).strip() if isinstance(text_path, str) else ""
    if tp_str and Path(tp_str).exists():
        return Path(tp_str).read_text(errors="replace")
    tp = TEXT_DIR / f"{sha[:12]}.txt"
    return tp.read_text(errors="replace") if tp.exists() else ""


def _snippet(text: str, max_len: int = 320) -> str:
    """A short, flag-aware excerpt for the card view."""
    if not text:
        return ""
    for pat in FLAG_PATTERNS.values():
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 120)
            end = min(len(text), m.end() + 200)
            return re.sub(r"\s+", " ", text[start:end]).strip()[:max_len]
    return re.sub(r"\s+", " ", text[:max_len]).strip()


def load_determinations() -> pd.DataFrame:
    """Enriched + cleaned determinations (drops header-artefact rows)."""
    df = pd.read_csv(analytics.default_input())
    df = analytics.enrich(df)
    if "committee" in df:
        c = df["committee"].astype(str).str.strip()
        df["committee"] = c.str.lower().map(VALID_COMMITTEES).fillna(
            c.where(c.str.lower().isin(VALID_COMMITTEES), other=pd.NA))
        # drop rows whose committee is the literal header word or empty noise
        bad = c.str.lower().isin({"committee", "", "nan"})
        df = df[~bad].copy()
    return df


def build_manifest(det: pd.DataFrame) -> list[dict]:
    """Per-document records, preferring data/documents.csv when present."""
    entities = [(e, _norm(e)) for e in det["reference_entity"].dropna().unique() if _norm(e)]
    # map normalised entity -> source page url (for fallback click-through)
    ent_url = {}
    for _, r in det.iterrows():
        ne = _norm(str(r.get("reference_entity") or ""))
        if ne and ne not in ent_url and isinstance(r.get("url"), str):
            ent_url[ne] = r["url"]

    # issue-number -> (entity, url): links date-named decision PDFs to determinations
    issue_map: dict[str, tuple[str, str | None]] = {}
    for _, r in det.iterrows():
        iss = str(r.get("issue_number") or "").strip()
        ent = r.get("reference_entity")
        if iss and len(iss) >= 6 and isinstance(ent, str):
            issue_map.setdefault(iss, (ent, r.get("url") if isinstance(r.get("url"), str) else None))

    def match_entity(*haystacks: str) -> tuple[str | None, str | None]:
        joined = " ".join(h for h in haystacks if h)
        # 1) try issue-number match (precise for date-named DC decision PDFs)
        for tok in re.findall(r"\d{6,}", joined):
            if tok in issue_map:
                return issue_map[tok]
        # 2) fall back to longest entity-name substring match
        hay = _norm(joined)
        best, best_len = None, 0
        for name, ne in entities:
            if ne and ne in hay and len(ne) > best_len:
                best, best_len = name, len(ne)
        return best, ent_url.get(_norm(best or ""))

    records: list[dict] = []

    if MANIFEST_CSV.exists():
        man = pd.read_csv(MANIFEST_CSV)
        for _, row in man.iterrows():
            sha = str(row.get("sha256") or "")
            title = str(row.get("doc_title") or "")
            file_url = str(row.get("file_url") or "")
            text = _read_text_for(sha, row.get("text_path"))
            kind, pf, bl = refine_kind(file_url, title, text)
            ent = row.get("reference_entity")
            if not isinstance(ent, str) or not ent.strip():
                ent, _ = match_entity(title, file_url, text[:4000])
            records.append(_make_record(
                sha, title, file_url, ent, row.get("committee"), text, kind, pf, bl))
        return _dedupe(records)

    # ── fallback: scan local docs/doctext ──
    for p in sorted(DOCS_DIR.glob("*")):
        if "__" not in p.name:
            continue
        sha, safename = p.name.split("__", 1)
        text = _read_text_for(sha, None)
        title = safename.replace("_", " ")
        kind, pf, bl = refine_kind(safename, title, text)
        ent, url = match_entity(title, text[:4000])
        # best available link: matched determination page, else a DC docs guess
        link = url or (DC_DOCS_BASE + safename)
        records.append(_make_record(sha, title, link, ent, None, text, kind, pf, bl,
                                     local_path=str(p)))
    return _dedupe(records)


def _make_record(sha, title, url, entity, committee, text, kind, pf, bl, local_path="") -> dict:
    head = text[:1500]
    mc = RE_COMMITTEE.search(head)
    committee = (committee if isinstance(committee, str) and committee.strip()
                 else (mc.group(1).strip() if mc else None))
    if isinstance(committee, str):
        committee = VALID_COMMITTEES.get(committee.lower().strip(), committee.strip())
    mm = RE_MEETING.search(head)
    mi = RE_ISSUE.search(head)
    mv = RE_VOTE.search(head)
    flags = {k: bool(p.search(text)) for k, p in FLAG_PATTERNS.items()}
    return {
        "doc_id": sha[:12],
        "title": title.strip()[:200],
        "url": url,
        "local_path": local_path,
        "reference_entity": entity,
        "committee": committee,
        "doc_kind": kind,
        "is_proforma": pf,
        "is_blackline": bl,
        "meeting_date": mm.group(1).strip() if mm else None,
        "issue_number": mi.group(1).strip() if mi else None,
        "vote_result": mv.group(1).strip() if mv else None,
        "flags": flags,
        "flag_list": [k for k, v in flags.items() if v],
        "text_chars": len(text),
        "snippet": _snippet(text),
    }


def _dedupe(records: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in records:
        key = (r["doc_id"], r["url"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if not text:
        return []
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + CHUNK_CHARS])
        i += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks


def embed_chunks(docs: list[dict], limit: int = 0) -> tuple[list[dict], "object"]:
    """Embed retrieval chunks via Ollama nomic-embed-text. Returns (chunks, matrix)."""
    import numpy as np
    import requests

    # Tabular doc kinds (price/bidder/maturity lists) are noise for Q&A — skip them
    # so retrieval stays narrative (decisions, statements, ASTs) and embedding is faster.
    SKIP_KINDS = {"final_list", "participating_bidders", "auction_market_data", "auction_results"}
    chunks: list[dict] = []
    for d in docs:
        if d["doc_kind"] in SKIP_KINDS:
            continue
        text = _read_text_for(d["doc_id"], None)
        for j, c in enumerate(chunk_text(text)):
            chunks.append({
                "doc_id": d["doc_id"], "chunk": j, "text": c,
                "reference_entity": d["reference_entity"], "committee": d["committee"],
                "doc_kind": d["doc_kind"], "meeting_date": d["meeting_date"],
                "title": d["title"], "url": d["url"],
            })
    if limit:
        chunks = chunks[:limit]
    if not chunks:
        return [], np.zeros((0, 768), dtype="float32")

    vecs = []
    sess = requests.Session()
    for n, ch in enumerate(chunks, 1):
        try:
            r = sess.post(f"{OLLAMA_URL}/api/embeddings",
                          json={"model": EMBED_MODEL, "prompt": ch["text"]}, timeout=120)
            vecs.append(r.json()["embedding"])
        except Exception as exc:  # keep alignment: zero vector on failure
            print(f"  ! embed failed for chunk {n}: {exc}")
            vecs.append([0.0] * (len(vecs[0]) if vecs else 768))
        if n % 100 == 0:
            print(f"  embedded {n}/{len(chunks)} chunks")
    mat = np.asarray(vecs, dtype="float32")
    # L2-normalise so a dot product is cosine similarity at query time
    norms = (mat ** 2).sum(axis=1, keepdims=True) ** 0.5
    mat = mat / (norms + 1e-9)
    return chunks, mat


def main() -> None:
    ap = argparse.ArgumentParser(description="Build dashboard + RAG index artifacts")
    ap.add_argument("--no-embed", action="store_true", help="skip Ollama embeddings")
    ap.add_argument("--limit-embed", type=int, default=0, help="cap chunks embedded (debug)")
    args = ap.parse_args()

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    det = load_determinations()
    # The reconciled table also carries auction-only rows (standalone auctions
    # with no DC determination). They are not determinations, so exclude them
    # from the index — otherwise n_determinations and the clean table double.
    if "match_status" in det.columns:
        det = det[det["match_status"] != "auction_only"].copy()
    det_out = det.copy()
    for col in ("date", "auction_date"):
        if col in det_out:
            det_out[col] = pd.to_datetime(det_out[col], errors="coerce").dt.strftime("%Y-%m-%d")
    det_out.to_csv(INDEX_DIR / "determinations_clean.csv", index=False)

    docs = build_manifest(det)
    (INDEX_DIR / "documents.json").write_text(json.dumps(docs, indent=2, default=str))

    # documents grouped by entity (drives the per-row drawer)
    by_entity: dict[str, list[dict]] = {}
    for d in docs:
        key = d["reference_entity"] or "Unattributed"
        by_entity.setdefault(key, []).append({
            "title": d["title"], "url": d["url"], "doc_kind": d["doc_kind"],
            "is_proforma": d["is_proforma"], "is_blackline": d["is_blackline"],
            "meeting_date": d["meeting_date"], "issue_number": d["issue_number"],
            "vote_result": d["vote_result"], "flag_list": d["flag_list"],
        })
    (INDEX_DIR / "entity_docs.json").write_text(json.dumps(by_entity, indent=2, default=str))

    # group documents into determination runs + extractive (no-LLM) summaries
    runs = summaries.build_runs(docs, det)
    (INDEX_DIR / "runs.json").write_text(json.dumps(runs, indent=2, default=str))
    print(f"  built {len(runs)} determination runs with extractive summaries")

    n_chunks = 0
    if not args.no_embed:
        embed_limit = args.limit_embed or MAX_EMBED_CHUNKS
        chunks, mat = embed_chunks(docs, limit=embed_limit)
        if len(chunks) >= embed_limit:
            print(f"  (RAG embedding capped at {embed_limit} chunks; summaries are "
                  f"extractive and unaffected)")
        n_chunks = len(chunks)
        if n_chunks:
            import numpy as np
            np.save(INDEX_DIR / "embeddings.npy", mat)
            (INDEX_DIR / "chunks.json").write_text(json.dumps(chunks, default=str))
    else:
        # Skipping embedding: keep the existing chunks/embeddings on disk and report
        # their real count, so a --no-embed rebuild doesn't falsely zero out n_chunks
        # (the served RAG index is still those chunks).
        chunks_p = INDEX_DIR / "chunks.json"
        if chunks_p.exists():
            try:
                n_chunks = len(json.loads(chunks_p.read_text()))
            except (ValueError, OSError):
                n_chunks = 0

    flag_totals: dict[str, int] = {}
    for d in docs:
        for f in d["flag_list"]:
            flag_totals[f] = flag_totals.get(f, 0) + 1

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_determinations": int(len(det)),
        "n_runs": len(runs),
        "n_documents": len(docs),
        "n_chunks": n_chunks,
        "n_entities_with_docs": len([k for k in by_entity if k != "Unattributed"]),
        "doc_kind_counts": pd.Series([d["doc_kind"] for d in docs]).value_counts().to_dict(),
        "flag_totals": flag_totals,
        "manifest_source": "documents.csv" if MANIFEST_CSV.exists() else "local-scan",
    }
    (INDEX_DIR / "index_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps(meta, indent=2, default=str))


if __name__ == "__main__":
    main()
