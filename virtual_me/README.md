# Virtual Me

A local, no-external-key **digital twin** that answers questions *as you*,
grounded only in a profile and personal notes you control. It reuses the same
local-Ollama retrieval-augmented-generation approach as the rest of this repo
(`cds_api.py`): nothing leaves the machine and no API key is required.

## How it works

```
profile.json        structured persona  — who you are, tone, values, boundaries
knowledge/*.md      your personal notes — the only facts it is allowed to use
virtual_me.py       RAG CLI: retrieve relevant notes → ask local LLM to answer as you
```

For each question it embeds the query (Ollama `nomic-embed-text`), pulls the
most relevant note sections, and asks a local LLM (`llama3.2:3b` by default) to
answer in the first person using **only** that material — saying "I don't have
that" rather than inventing facts, and respecting the boundaries in your profile.

## Quick start

```bash
pip install -r virtual_me/requirements.txt        # just `requests`
# 1. Edit virtual_me/profile.json  (your persona)
# 2. Fill virtual_me/knowledge/about_me.md  (and add more .md notes)
# 3. Ask:
python virtual_me/virtual_me.py "What are you working on right now?"
python virtual_me/virtual_me.py                   # interactive REPL
```

Requires a local [Ollama](https://ollama.com) with the models pulled:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2:3b
```

If Ollama isn't running the CLI degrades gracefully — it prints the notes it
*would* have grounded on instead of pretending to have generated an answer.

## Config (env vars)

| Var             | Default                  | Purpose                          |
|-----------------|--------------------------|----------------------------------|
| `OLLAMA_URL`    | `http://localhost:11434` | Ollama endpoint                  |
| `VM_LLM_MODEL`  | `llama3.2:3b`            | Generation model                 |
| `VM_EMBED_MODEL`| `nomic-embed-text`       | Embedding model for retrieval    |
| `VM_TOP_K`      | `4`                      | How many note sections to ground on |

## Honesty

In the spirit of this repo's data conventions: the twin answers from your
profile + notes only. Keep those honest and it stays honest — it will decline
rather than guess when the corpus doesn't cover a question.
