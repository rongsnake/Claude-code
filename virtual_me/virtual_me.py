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
    python virtual_me/virtual_me.py            # interactive REPL

Config (env):
    OLLAMA_URL        default http://localhost:11434
    VM_LLM_MODEL      default llama3.2:3b
    VM_EMBED_MODEL    default nomic-embed-text
    VM_TOP_K          default 4   (how many note-chunks to ground on)

If Ollama is unreachable the script degrades gracefully: it prints the persona
and the most relevant notes it would have grounded on, so it is still useful
offline and never pretends to have generated an answer it didn't.
"""

from __future__ import annotations

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

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.environ.get("VM_LLM_MODEL", "llama3.2:3b")
EMBED_MODEL = os.environ.get("VM_EMBED_MODEL", "nomic-embed-text")
TOP_K = int(os.environ.get("VM_TOP_K", "4"))


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    try:
        return json.loads(PROFILE_PATH.read_text())
    except json.JSONDecodeError as exc:
        print(f"warning: profile.json is not valid JSON ({exc}); ignoring it.")
        return {}


def load_chunks() -> list[dict]:
    """Split every knowledge/*.md file into section-sized chunks (split on `##`)."""
    chunks: list[dict] = []
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = md.read_text()
        # Split on markdown section headers, keeping the header with its body.
        parts = re.split(r"(?m)^(?=#{1,6}\s)", text)
        for part in parts:
            body = part.strip()
            if body:
                chunks.append({"source": md.name, "text": body})
    return chunks


def embed(text: str) -> "list[float] | None":
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                          json={"model": EMBED_MODEL, "prompt": text}, timeout=60)
        return r.json().get("embedding")
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb + 1e-9)


def retrieve(question: str, chunks: list[dict], k: int = TOP_K) -> list[dict]:
    """Rank notes by embedding similarity, falling back to keyword overlap."""
    if not chunks:
        return []
    q_emb = embed(question)
    if q_emb is not None:
        scored = []
        for c in chunks:
            c_emb = embed(c["text"][:1500])
            if c_emb is None:
                continue
            scored.append((_cosine(q_emb, c_emb), c))
        if scored:
            scored.sort(key=lambda s: -s[0])
            return [c for _, c in scored[:k]]
    # Keyword fallback (also used when embeddings are unavailable).
    terms = {w for w in re.findall(r"\w+", question.lower()) if len(w) > 2}
    scored = [(sum(c["text"].lower().count(t) for t in terms), c) for c in chunks]
    scored.sort(key=lambda s: -s[0])
    return [c for score, c in scored[:k] if score > 0] or chunks[:k]


def persona_block(profile: dict) -> str:
    if not profile:
        return "You are a helpful digital twin. No profile is configured yet."
    lines = [f"You are the virtual version of {profile.get('name', 'this person')}, "
             "answering in the first person as them."]
    if profile.get("tagline"):
        lines.append(profile["tagline"])
    for key, label in [
        ("roles", "Roles"), ("expertise", "Expertise"),
        ("values", "Values"), ("communication_style", "How you communicate"),
        ("current_focus", "Current focus"), ("boundaries", "Boundaries"),
    ]:
        vals = profile.get(key)
        if vals:
            lines.append(f"{label}: " + "; ".join(vals))
    return "\n".join(lines)


def build_prompt(question: str, profile: dict, ctx: list[dict]) -> str:
    notes = "\n\n---\n\n".join(f"[{c['source']}]\n{c['text']}" for c in ctx) \
        or "(no personal notes available)"
    return (
        f"{persona_block(profile)}\n\n"
        "Answer the question in the first person, in your own voice, USING ONLY the "
        "profile above and the personal notes below. If they do not cover the "
        "question, say so plainly rather than inventing facts. Respect your stated "
        "boundaries.\n\n"
        f"=== PERSONAL NOTES ===\n{notes}\n\n"
        f"=== QUESTION ===\n{question}\n\n=== ANSWER (as me) ===\n"
    )


def generate(prompt: str) -> "str | None":
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", timeout=300, json={
            "model": LLM_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.4, "num_predict": 400},
        })
        return r.json().get("response", "").strip()
    except Exception:
        return None


def answer(question: str, profile: dict, chunks: list[dict]) -> str:
    ctx = retrieve(question, chunks)
    prompt = build_prompt(question, profile, ctx)
    out = generate(prompt)
    if out:
        return out
    # Graceful offline fallback — never fabricate a "generated" answer.
    grounding = "\n\n".join(f"• [{c['source']}] {c['text'][:300]}" for c in ctx)
    return ("(Local model unavailable — start Ollama to get a spoken-as-you answer.)\n\n"
            f"Most relevant notes for your question:\n{grounding or '  (none yet)'}")


def main() -> None:
    profile = load_profile()
    chunks = load_chunks()
    if len(sys.argv) > 1:
        print(answer(" ".join(sys.argv[1:]), profile, chunks))
        return
    name = profile.get("name", "me")
    print(f"Virtual {name} — ask a question (Ctrl-D / blank line to quit).")
    while True:
        try:
            q = input("\n> ").strip()
        except EOFError:
            break
        if not q:
            break
        print("\n" + answer(q, profile, chunks))


if __name__ == "__main__":
    main()
