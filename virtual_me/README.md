# Virtual Me

A local, no-external-key **digital twin** that answers questions *as you*,
grounded only in a profile and personal notes you control. It reuses the same
local-Ollama retrieval-augmented-generation approach as the rest of this repo
(`cds_api.py`): nothing leaves the machine and no API key is required.

## How it works

```
profile.json          structured persona — who you are, tone, values, boundaries
knowledge/*.md        your personal notes — the only facts the twin may use
virtual_me.py         RAG CLI: retrieve relevant notes → local LLM answers as you
test_virtual_me.py    checks that scaffolding never reaches the model
.cache/               note embeddings, keyed by content hash (gitignored)
```

For each question it embeds the query (Ollama `nomic-embed-text`), ranks your
note sections, and asks a local LLM (`llama3.2:3b` by default) to answer in the
first person using **only** that material — saying "I don't have that" rather
than inventing facts, and respecting the boundaries in your profile. Every
answer is followed by the sections it drew on.

## Quick start

```bash
pip install -r virtual_me/requirements.txt        # just `requests`
# 1. Edit virtual_me/profile.json  (your persona)
# 2. Fill virtual_me/knowledge/about_me.md  (and add more .md notes)
# 3. Ask:
python virtual_me/virtual_me.py "What are you working on right now?"
python virtual_me/virtual_me.py                   # interactive REPL
python virtual_me/virtual_me.py --rebuild         # force a full re-embed
python virtual_me/virtual_me.py --no-stream "…"   # wait for the whole answer
```

Requires a local [Ollama](https://ollama.com) with the models pulled:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2:3b
```

If Ollama isn't running the CLI degrades gracefully — it prints the notes it
*would* have grounded on instead of pretending to have generated an answer.

## Adding notes

Drop more `.md` files into `knowledge/`. Each markdown header starts a new
retrievable section, so prefer several short, well-titled sections over one long
file — `## Alstin Lodge energy controller` retrieves far better than a wall of
prose. Sections are cited by heading, so headings are worth writing well.

## Design notes

**Embeddings are cached.** Notes are embedded once and stored in `.cache/`
keyed by a hash of their content plus the model name, so a question costs one
embedding call rather than one per note. Editing a section re-embeds only that
section; sections you delete are evicted. Switching `VM_EMBED_MODEL` invalidates
the cache automatically.

**Retrieval is hybrid.** Cosine similarity is blended with keyword overlap
(0.75/0.25). The corpus is small and full of proper nouns — *PolyArb*,
*Powerwall*, *Creditex* — that a small embedding model tends to blur together,
so an exact-term signal earns its place alongside the semantic one. With Ollama
down, keyword scoring carries retrieval on its own.

**Scaffolding never reaches the model.** `TODO` markers and `> **DRAFT …**`
banners are stripped before embedding or prompting — a twin that recites
*"TODO: your actual profession"* as though it were fact is worse than one that
stays quiet. Placeholder-only FAQ answers take their question with them, while
inline `(TODO: …)` asides are removed without losing the real sentence around
them. When a retrieved section still had placeholders, the CLI says so on
stderr. Genuine blockquotes are left alone. `test_virtual_me.py` covers this.

**Answers stream.** On a Pi, CPU prompt-eval dominates latency and a silent
terminal looks like a hang, so tokens print as they arrive — the same reason
`cds_api.py` streams.

## Config (env vars)

| Var              | Default                  | Purpose                             |
|------------------|--------------------------|-------------------------------------|
| `OLLAMA_URL`     | `http://localhost:11434` | Ollama endpoint                     |
| `VM_LLM_MODEL`   | `llama3.2:3b`            | Generation model                    |
| `VM_EMBED_MODEL` | `nomic-embed-text`       | Embedding model for retrieval       |
| `VM_TOP_K`       | `4`                      | How many note sections to ground on |

On a Pi, `VM_LLM_MODEL=llama3.2:1b` evaluates roughly 3.6x faster than `3b` —
the same trade-off `cds_api.py` documents — at some cost in answer quality.

## Tests

```bash
python virtual_me/test_virtual_me.py
```

No dependencies beyond `requests`; the retrieval tests exercise the keyword
fallback, so the suite passes with Ollama stopped.

## Honesty

In the spirit of this repo's data conventions: the twin answers from your
profile + notes only. Keep those honest and it stays honest — it will decline
rather than guess when the corpus doesn't cover a question.
