"""
Virtual Me — a local, no-external-key "digital twin" that answers as you.

It mirrors the rest of this repo's approach (cds_api.py): retrieval-augmented
generation over a small personal corpus, generated entirely by a local Ollama
model. Nothing leaves the machine and no API key is required.

The corpus is yours to control:
    profile.json        structured facts + persona (tone, values, boundaries)
    knowledge/*.md      free-text notes the model is allowed to draw on

Usage:
    python virtual_me/virtual_me.py "What are you working on right now?"
    python virtual_me/virtual_me.py                 # interactive REPL
    python virtual_me/virtual_me.py --rebuild       # re-embed notes, then continue
    python virtual_me/virtual_me.py --no-stream Q   # wait for the whole answer

Config (env):
    OLLAMA_URL        default http://localhost:11434
    VM_LLM_MODEL      default llama3.2:3b   (llama3.2:1b is ~3.6x faster on a Pi)
    VM_EMBED_MODEL    default nomic-embed-text
    VM_TOP_K          default 4   (how many note-chunks to ground on)

Note embeddings are cached in .cache/embeddings.json, keyed by content hash, so
only new or edited sections are re-embedded — a question costs one embedding
call, not one per note. Editing a note invalidates just that section.

If Ollama is unreachable the script degrades gracefully: it prints the persona
and the most relevant notes it would have grounded on, so it is still useful
offline and never pretends to have generated an answer it didn't.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:  # keep the failure legible
    print("This tool needs `requests` (see requirements.txt): pip install requests")
    sys.exit(1)

BASE = Path(__file__).resolve().parent
PROFILE_PATH = BASE / "profile.json"
KNOWLEDGE_DIR = BASE / "knowledge"
CACHE_PATH = BASE / ".cache" / "embeddings.json"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.environ.get("VM_LLM_MODEL", "llama3.2:3b")
EMBED_MODEL = os.environ.get("VM_EMBED_MODEL", "nomic-embed-text")
TOP_K = int(os.environ.get("VM_TOP_K", "4"))

# Unfilled scaffolding rather than facts about you. It is stripped before
# anything reaches the model, so the twin can never recite "TODO: your actual
# profession" as though it were an answer. Placeholders show up three ways:
# a whole bullet, an inline "(TODO: …)" aside, and a draft banner blockquote.
TODO_RE = re.compile(r"(?i)\bTODO\b")
TODO_ASIDE_RE = re.compile(r"\(\s*(?:TODO|FIXME)\b[^)]*\)", re.I | re.S)
BULLET_RE = re.compile(r"(?:[-*+]|\d+\.|#)")
QUESTION_RE = re.compile(r"\s*(?:\*\*)?Q:")
ANSWER_RE = re.compile(r"\s*(?:\*\*)?A:")


def _drop_draft_blockquotes(lines: list[str]) -> list[str]:
    """Drop blockquote blocks that are draft/TODO banners, keeping real quotes."""
    out, i = [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith(">"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith(">"):
                j += 1
            block = lines[i:j]
            if not re.search(r"(?i)\b(?:TODO|DRAFT)\b", "\n".join(block)):
                out.extend(block)  # a genuine quotation — keep it
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def _drop_orphan_questions(lines: list[str]) -> list[str]:
    """Drop a FAQ question whose answer was nothing but a placeholder."""
    out = []
    for i, line in enumerate(lines):
        if QUESTION_RE.match(line):
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            if not ANSWER_RE.match(nxt):
                continue
        out.append(line)
    return out


def strip_placeholders(text: str) -> str:
    """Remove TODO scaffolding and draft banners; tidy the gaps they leave."""
    lines = _drop_draft_blockquotes(TODO_ASIDE_RE.sub("", text).splitlines())
    kept, swallowing = [], False
    for line in lines:
        if TODO_RE.search(line):
            # The whole line is scaffolding. A wrapped bullet continues onto
            # indented lines, so swallow those too rather than orphan them.
            swallowing = True
            continue
        if swallowing:
            stripped = line.lstrip()
            is_continuation = (bool(stripped) and line[:1].isspace()
                               and not BULLET_RE.match(stripped))
            if is_continuation:
                continue
            swallowing = False
        kept.append(line)
    out = "\n".join(_drop_orphan_questions(kept))
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def has_placeholders(text: str) -> bool:
    return bool(TODO_RE.search(text))


# --------------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------------- #

def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    try:
        return json.loads(PROFILE_PATH.read_text())
    except json.JSONDecodeError as exc:
        print(f"warning: profile.json is not valid JSON ({exc}); ignoring it.")
        return {}


def load_chunks() -> list[dict]:
    """Split every knowledge/*.md file into section-sized chunks (split on headers).

    Each chunk keeps its source file and heading so answers can cite where a
    claim came from, and so the heading itself contributes to the embedding.
    """
    chunks: list[dict] = []
    if not KNOWLEDGE_DIR.exists():
        return chunks
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        raw = md.read_text()
        # Split before each markdown header, keeping the header with its body.
        for part in re.split(r"(?m)^(?=#{1,6}\s)", raw):
            body = strip_placeholders(part)
            if not body:
                continue  # section was nothing but scaffolding
            first = body.splitlines()[0]
            heading = first.lstrip("#").strip() if first.startswith("#") else ""
            chunks.append({
                "source": md.name,
                "heading": heading,
                "text": body,
                "had_placeholders": has_placeholders(part),
            })
    return chunks


def chunk_key(text: str) -> str:
    """Cache key: content + embedding model, so edits and model swaps invalidate."""
    return hashlib.sha256(f"{EMBED_MODEL}\x00{text}".encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Embeddings (cached)
# --------------------------------------------------------------------------- #

def embed(text: str) -> "list[float] | None":
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                          json={"model": EMBED_MODEL, "prompt": text}, timeout=60)
        vec = r.json().get("embedding")
        return _normalise(vec) if vec else None
    except Exception:
        return None


def _normalise(vec: list[float]) -> list[float]:
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}  # a corrupt cache is a rebuild, not a crash


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache))
    except OSError as exc:
        print(f"warning: could not write embedding cache ({exc})")


def ensure_embeddings(chunks: list[dict], rebuild: bool = False) -> bool:
    """Attach a cached embedding to each chunk, embedding only what's missing.

    Returns True if every chunk ended up with a vector (i.e. Ollama answered).
    """
    cache = {} if rebuild else _load_cache()
    missing = [c for c in chunks if chunk_key(c["text"]) not in cache]
    if missing:
        print(f"embedding {len(missing)} new/changed note section"
              f"{'s' if len(missing) != 1 else ''}…", file=sys.stderr)
    for chunk in missing:
        vec = embed(chunk["text"])
        if vec is None:
            return False  # Ollama is down; fall back to keyword retrieval
        cache[chunk_key(chunk["text"])] = vec
    for chunk in chunks:
        chunk["embedding"] = cache.get(chunk_key(chunk["text"]))
    # Drop entries for sections that no longer exist, so the cache can't grow
    # without bound as notes are rewritten.
    live = {chunk_key(c["text"]) for c in chunks}
    _save_cache({k: v for k, v in cache.items() if k in live})
    return all(c.get("embedding") for c in chunks)


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #

def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both sides are L2-normalised


def _keyword_score(question: str, text: str) -> float:
    terms = {w for w in re.findall(r"\w+", question.lower()) if len(w) > 2}
    if not terms:
        return 0.0
    low = text.lower()
    return sum(1 for t in terms if t in low) / len(terms)


def retrieve(question: str, chunks: list[dict], k: int = TOP_K) -> list[dict]:
    """Hybrid retrieval: embedding similarity plus keyword overlap.

    The corpus is small and full of proper nouns ("PolyArb", "Powerwall") that a
    small embedding model can blur together, so an exact-term signal is folded in
    alongside the semantic one. Falls back to keywords alone when Ollama is down.
    """
    if not chunks:
        return []
    q_emb = embed(question)
    scored = []
    for c in chunks:
        kw = _keyword_score(question, f"{c['heading']} {c['text']}")
        if q_emb is not None and c.get("embedding"):
            score = 0.75 * _cosine(q_emb, c["embedding"]) + 0.25 * kw
        else:
            score = kw
        scored.append((score, c))
    scored.sort(key=lambda s: -s[0])
    hits = [dict(c, score=round(score, 3)) for score, c in scored[:k] if score > 0]
    return hits or [dict(c, score=0.0) for c in chunks[:k]]


# --------------------------------------------------------------------------- #
# Prompting
# --------------------------------------------------------------------------- #

def persona_block(profile: dict) -> str:
    if not profile:
        return "You are a helpful digital twin. No profile is configured yet."
    lines = [f"You are the virtual version of {profile.get('name', 'this person')}, "
             "answering in the first person as them."]
    if profile.get("tagline"):
        lines.append(strip_placeholders(profile["tagline"]) or "")
    for key, label in [
        ("roles", "Roles"), ("expertise", "Expertise"),
        ("values", "Values"), ("communication_style", "How you communicate"),
        ("current_focus", "Current focus"), ("boundaries", "Boundaries"),
    ]:
        vals = [v for v in profile.get(key) or [] if not has_placeholders(v)]
        if vals:
            lines.append(f"{label}: " + "; ".join(vals))
    return "\n".join(l for l in lines if l)


def build_prompt(question: str, profile: dict, ctx: list[dict]) -> str:
    notes = "\n\n---\n\n".join(
        f"[{i}] {c['source']}" + (f" § {c['heading']}" if c["heading"] else "")
        + f"\n{c['text']}"
        for i, c in enumerate(ctx, 1)
    ) or "(no personal notes available)"
    return (
        f"{persona_block(profile)}\n\n"
        "Answer the question in the first person, in your own voice, USING ONLY the "
        "profile above and the numbered personal notes below. If they do not cover "
        "the question, say so plainly rather than inventing facts — never guess at "
        "biographical details. Respect your stated boundaries. Keep it concise.\n\n"
        f"=== PERSONAL NOTES ===\n{notes}\n\n"
        f"=== QUESTION ===\n{question}\n\n=== ANSWER (as me) ===\n"
    )


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #

def generate(prompt: str, stream: bool = True) -> "str | None":
    """Generate an answer, printing tokens as they arrive when streaming.

    Streaming matters on a Pi: CPU prompt-eval dominates latency, so the first
    token can be many seconds out and a silent terminal looks like a hang.
    """
    try:
        body = {
            "model": LLM_MODEL, "prompt": prompt, "stream": stream,
            "keep_alive": "30m",
            "options": {"temperature": 0.4, "num_predict": 400},
        }
        if not stream:
            r = requests.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=300)
            return (r.json().get("response") or "").strip()
        parts: list[str] = []
        with requests.post(f"{OLLAMA_URL}/api/generate", json=body,
                           stream=True, timeout=300) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("response"):
                    parts.append(obj["response"])
                    print(obj["response"], end="", flush=True)
                if obj.get("done"):
                    break
        if parts:
            print()
        return "".join(parts).strip()
    except Exception:
        return None


def format_sources(ctx: list[dict]) -> str:
    seen, out = set(), []
    for c in ctx:
        label = c["source"] + (f" § {c['heading']}" if c["heading"] else "")
        if label not in seen:
            seen.add(label)
            out.append(f"  [{len(out) + 1}] {label}  (score {c.get('score', 0)})")
    return "Sources:\n" + "\n".join(out) if out else ""


def answer(question: str, profile: dict, chunks: list[dict],
           stream: bool = True) -> None:
    ctx = retrieve(question, chunks)
    out = generate(build_prompt(question, profile, ctx), stream=stream)
    if out:
        if not stream:
            print(out)
    else:
        # Graceful offline fallback — never fabricate a "generated" answer.
        grounding = "\n\n".join(
            f"• [{c['source']}] {c['text'][:300]}" for c in ctx) or "  (none yet)"
        print("(Local model unavailable — start Ollama to get a spoken-as-you "
              f"answer.)\n\nMost relevant notes for your question:\n{grounding}")
    if ctx:
        print("\n" + format_sources(ctx))
    if any(c.get("had_placeholders") for c in ctx):
        print("\nnote: some retrieved sections still contain TODO placeholders — "
              "they were withheld from the model. Fill them in for a fuller answer.",
              file=sys.stderr)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    argv = sys.argv[1:]
    rebuild = "--rebuild" in argv
    stream = "--no-stream" not in argv
    question = " ".join(a for a in argv if not a.startswith("--")).strip()

    profile = load_profile()
    chunks = load_chunks()
    if not chunks:
        print(f"No notes found in {KNOWLEDGE_DIR}/ — add a .md file first.")
        return
    ensure_embeddings(chunks, rebuild=rebuild)

    if question:
        answer(question, profile, chunks, stream=stream)
        return

    name = profile.get("name", "me")
    print(f"Virtual {name} — ask a question (Ctrl-D or blank line to quit).")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            break
        print()
        answer(q, profile, chunks, stream=stream)


if __name__ == "__main__":
    main()
