"""
Local Q&A + refresh API for the CDS Determinations dashboard.

A thin FastAPI service that gives the otherwise-static dashboard the two things a
static file cannot do — answer free-text questions and trigger a data refresh —
without any external API key. Retrieval-augmented generation runs entirely on the
Pi's local Ollama (embeddings: nomic-embed-text, generation: llama3.2:3b by
default). It is meant to sit behind the same Caddy basic_auth gate as /cds/, with:

    @cdsapi path /cds/api/*
    reverse_proxy @cdsapi localhost:5055

Endpoints (all under /cds/api so Caddy can forward the path verbatim):
    GET  /cds/api/status   counts + last-refresh / index-build times (for the UI)
    POST /cds/api/ask      {question} -> {answer, citations[]}  (RAG over the corpus)
    POST /cds/api/refresh  kick the scrape+index pipeline async (locked, rate-limited)

Run:
    .venv/bin/uvicorn cds_api:app --host 127.0.0.1 --port 5055
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
INDEX_DIR = BASE / "data" / "index"
REFRESH_SH = BASE / "cds_refresh.sh"
STATE_FILE = INDEX_DIR / "refresh_state.json"
LOCK_FILE = INDEX_DIR / "refresh.lock"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"
# Default to the 1B model: on this Pi (CPU-only) prompt-eval dominates latency, and
# 1B evals ~3.6x faster than 3B. Override with CDS_LLM_MODEL=llama3.2:3b / qwen3:8b
# for higher-quality answers at the cost of speed.
LLM_MODEL = os.environ.get("CDS_LLM_MODEL", "llama3.2:1b")
TOP_K = int(os.environ.get("CDS_TOP_K", "4"))
CTX_CHARS = int(os.environ.get("CDS_CTX_CHARS", "700"))  # per-chunk cap fed to the LLM
REFRESH_MIN_INTERVAL = int(os.environ.get("CDS_REFRESH_MIN_INTERVAL", "900"))  # 15 min

app = FastAPI(title="CDS Determinations Q&A API")

# In-memory index, (re)loaded from disk on startup and after each refresh.
_INDEX: dict = {"mat": None, "chunks": [], "meta": {}}


def load_index() -> None:
    meta_p = INDEX_DIR / "index_meta.json"
    emb_p = INDEX_DIR / "embeddings.npy"
    chunks_p = INDEX_DIR / "chunks.json"
    _INDEX["meta"] = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    _INDEX["mat"] = np.load(emb_p) if emb_p.exists() else None
    _INDEX["chunks"] = json.loads(chunks_p.read_text()) if chunks_p.exists() else []


def warm_model() -> None:
    """Pre-load the LLM into memory so the first user question isn't a cold start."""
    try:
        requests.post(f"{OLLAMA_URL}/api/generate", timeout=300, json={
            "model": LLM_MODEL, "prompt": "ok", "stream": False,
            "keep_alive": "30m", "options": {"num_predict": 1}})
    except Exception as exc:
        print(f"warm-up skipped: {exc}")


@app.on_event("startup")
def _startup() -> None:
    try:
        load_index()
    except Exception as exc:  # never block startup on a half-built index
        print(f"index load failed: {exc}")
    warm_model()


def embed(text: str) -> "np.ndarray | None":
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                          json={"model": EMBED_MODEL, "prompt": text}, timeout=60)
        v = np.asarray(r.json()["embedding"], dtype="float32")
        return v / (float((v ** 2).sum()) ** 0.5 + 1e-9)
    except Exception as exc:
        print(f"embed failed: {exc}")
        return None


def retrieve(question: str, k: int = TOP_K) -> list[dict]:
    mat, chunks = _INDEX["mat"], _INDEX["chunks"]
    if mat is None or not len(chunks):
        return []
    q = embed(question)
    if q is None:
        return []
    sims = mat @ q  # cosine (rows are L2-normalised at build time)
    idx = np.argsort(-sims)[:k]
    out = []
    for i in idx:
        c = dict(chunks[int(i)])
        c["score"] = round(float(sims[int(i)]), 3)
        out.append(c)
    return out


def build_prompt(question: str, ctx: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(ctx, 1):
        tag = f"[{i}] {c.get('reference_entity') or '?'} · {c.get('committee') or '?'} · " \
              f"{c.get('doc_kind')} · {c.get('meeting_date') or ''}"
        blocks.append(f"{tag}\n{(c['text'] or '')[:CTX_CHARS]}")
    context = "\n\n---\n\n".join(blocks)
    return (
        "You are an analyst of the ISDA Credit Derivatives Determinations Committees "
        "(CDS DC). Answer the question USING ONLY the numbered source excerpts below. "
        "Cite the sources you rely on inline as [1], [2], etc. If the excerpts do not "
        "contain the answer, say so plainly — do not invent facts.\n\n"
        f"=== SOURCES ===\n{context}\n\n=== QUESTION ===\n{question}\n\n=== ANSWER ===\n"
    )


def _citations(ctx: list[dict]) -> list[dict]:
    seen, citations = set(), []
    for c in ctx:
        if c["doc_id"] in seen:
            continue
        seen.add(c["doc_id"])
        citations.append({
            "n": len(citations) + 1,
            "reference_entity": c.get("reference_entity"),
            "committee": c.get("committee"),
            "doc_kind": c.get("doc_kind"),
            "meeting_date": c.get("meeting_date"),
            "title": c.get("title"),
            "url": c.get("url"),
            "score": c.get("score"),
            "excerpt": (c.get("text") or "")[:300],
        })
    return citations


class AskBody(BaseModel):
    question: str


@app.post("/cds/api/ask")
def ask(body: AskBody):
    """Stream the answer as newline-delimited JSON: first a citations event, then
    token events as the local model generates, then a done event. Streaming keeps
    the UI responsive despite slow CPU prompt-eval on the Pi."""
    question = (body.question or "").strip()
    ctx = retrieve(question) if question else []
    citations = _citations(ctx)

    def stream():
        yield json.dumps({"type": "citations", "citations": citations}) + "\n"
        if not question:
            yield json.dumps({"type": "token", "t": "Please enter a question."}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return
        if not ctx:
            msg = ("No indexed documents to answer from yet. Click **Update** to build "
                   "the index, then ask again.")
            yield json.dumps({"type": "token", "t": msg}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return
        prompt = build_prompt(question, ctx)
        try:
            with requests.post(f"{OLLAMA_URL}/api/generate", stream=True, timeout=300, json={
                "model": LLM_MODEL, "prompt": prompt, "stream": True, "keep_alive": "30m",
                "options": {"temperature": 0.1, "num_predict": 350},
            }) as r:
                for line in r.iter_lines():
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("response"):
                        yield json.dumps({"type": "token", "t": obj["response"]}) + "\n"
                    if obj.get("done"):
                        break
        except Exception as exc:
            yield json.dumps({"type": "token",
                              "t": f"\n\n_Local model error: {exc}_"}) + "\n"
        yield json.dumps({"type": "done", "model": LLM_MODEL}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


def _read_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _refresh_running() -> bool:
    if not LOCK_FILE.exists():
        return False
    try:  # stale-lock guard: a lock older than 2h is treated as dead
        return (time.time() - LOCK_FILE.stat().st_mtime) < 7200
    except OSError:
        return False


@app.get("/cds/api/status")
def status() -> dict:
    meta = _INDEX["meta"] or {}
    st = _read_state()
    return {
        "n_determinations": meta.get("n_determinations"),
        "n_documents": meta.get("n_documents"),
        "n_chunks": meta.get("n_chunks"),
        "index_built_at": meta.get("built_at"),
        "manifest_source": meta.get("manifest_source"),
        "flag_totals": meta.get("flag_totals", {}),
        "last_refresh_started": st.get("started_at"),
        "last_refresh_finished": st.get("finished_at"),
        "last_refresh_ok": st.get("ok"),
        "busy": _refresh_running(),
        "model": LLM_MODEL,
    }


@app.post("/cds/api/refresh")
def refresh() -> JSONResponse:
    if _refresh_running():
        return JSONResponse({"status": "busy", "message": "A refresh is already running."}, 409)
    st = _read_state()
    last = st.get("finished_epoch", 0)
    if time.time() - last < REFRESH_MIN_INTERVAL:
        wait = int(REFRESH_MIN_INTERVAL - (time.time() - last))
        return JSONResponse(
            {"status": "rate_limited", "message": f"Refreshed recently — try again in {wait}s."}, 429)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.touch()
    STATE_FILE.write_text(json.dumps({
        **st, "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ok": None, "finished_at": None,
    }))
    # Detach the pipeline; a wrapper clears the lock + records the outcome.
    log = INDEX_DIR / "refresh.log"
    wrapper = (
        f'set -o pipefail; '
        f'if bash {REFRESH_SH} >> "{log}" 2>&1; then ok=true; else ok=false; fi; '
        f'python - "$ok" <<PY\n'
        f'import json,sys,time,datetime\n'
        f'from pathlib import Path\n'
        f'p=Path("{STATE_FILE}"); st=json.loads(p.read_text()) if p.exists() else {{}}\n'
        f'st["ok"]= (sys.argv[1]=="true"); '
        f'st["finished_at"]=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"); '
        f'st["finished_epoch"]=time.time()\n'
        f'p.write_text(json.dumps(st))\n'
        f'PY\n'
        f'rm -f "{LOCK_FILE}"'
    )
    subprocess.Popen(["bash", "-c", wrapper], cwd=str(BASE),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return JSONResponse({"status": "started",
                         "message": "Refresh started — scraping, re-indexing and redeploying."})


@app.post("/cds/api/reload")
def reload_index() -> dict:
    """Reload the on-disk index without a full refresh (used after a refresh finishes)."""
    load_index()
    return {"status": "reloaded", "n_chunks": (_INDEX["meta"] or {}).get("n_chunks")}
