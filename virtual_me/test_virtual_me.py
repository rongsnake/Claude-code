"""
Tests for Virtual Me's corpus handling.

The important guarantee is negative: unfilled scaffolding (TODO markers, draft
banners) must never reach the model, because a twin that recites
"TODO: your actual profession" as though it were a fact is worse than one that
says nothing. Run with:  python virtual_me/test_virtual_me.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import virtual_me as vm  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}{(' — ' + detail) if detail else ''}")
        FAILURES.append(name)


def test_strip_placeholders() -> None:
    print("strip_placeholders")

    # A whole bullet that is a placeholder, wrapped onto a continuation line.
    bullet = ("- I'm Gareth Burton. I build things.\n"
              "- TODO: a few real lines on my history — where I'm from, and\n"
              "  what I do day to day (profession / background).\n"
              "- I keep a NAS at home.")
    out = vm.strip_placeholders(bullet)
    check("drops a placeholder bullet", "TODO" not in out, out)
    check("drops its wrapped continuation", "day to day" not in out, out)
    check("keeps the real bullets around it",
          "Gareth Burton" in out and "NAS at home" in out, out)

    # An inline aside inside otherwise-real content: keep the sentence, drop the aside.
    aside = ("A: Mostly the CDS dashboard and the energy optimiser. (TODO: tell me\n"
             "which one is front-of-mind today.)")
    out = vm.strip_placeholders(aside)
    check("drops a multi-line inline (TODO: …) aside", "TODO" not in out, out)
    check("keeps the real sentence containing it", "CDS dashboard" in out, out)

    # A draft banner blockquote goes; a genuine quotation stays.
    banner = ("> **DRAFT — please edit.** Everything below is a placeholder.\n\n"
              "## Who I am\n\nReal content.")
    out = vm.strip_placeholders(banner)
    check("drops a DRAFT banner blockquote", "DRAFT" not in out, out)
    check("keeps content after the banner", "Real content." in out, out)

    quote = "As my old boss put it:\n\n> Ship it, then measure.\n\nStill true."
    out = vm.strip_placeholders(quote)
    check("keeps a genuine blockquote", "Ship it, then measure." in out, out)

    # A FAQ answer that is only a placeholder should take its question with it.
    faq = ("**Q: How do you like to be contacted?**\n"
           "A: TODO — your real preference.\n\n"
           "**Q: Why self-host?**\n"
           "A: I like owning my stack.")
    out = vm.strip_placeholders(faq)
    check("drops a placeholder-only answer", "your real preference" not in out, out)
    check("drops the orphaned question with it",
          "How do you like to be contacted" not in out, out)
    check("keeps the answered question",
          "Why self-host?" in out and "owning my stack" in out, out)


def test_corpus_is_clean() -> None:
    print("live corpus")
    chunks = vm.load_chunks()
    check("loads at least one note section", bool(chunks), f"{len(chunks)} chunks")
    for c in chunks:
        check(f"no TODO leak in § {c['heading'] or '(intro)'}",
              "TODO" not in c["text"], c["text"][:120])
    profile = vm.load_profile()
    persona = vm.persona_block(profile)
    check("no TODO leak in the persona block", "TODO" not in persona, persona[:200])
    check("persona still names the person",
          profile.get("name", "") in persona if profile.get("name") else True)


def test_retrieval_ranks_sensibly() -> None:
    """With Ollama down this exercises the keyword fallback path specifically."""
    print("retrieval (keyword fallback)")
    chunks = vm.load_chunks()
    if not chunks:
        return
    for c in chunks:
        c["embedding"] = None
    hits = vm.retrieve("What do you think about synthetic data?", chunks)
    check("returns at most TOP_K hits", len(hits) <= vm.TOP_K, str(len(hits)))
    check("every hit carries a citable source",
          all(h.get("source") for h in hits))
    check("ranks the values section first for a values question",
          "think about my work" in (hits[0]["heading"] or "").lower(),
          hits[0]["heading"] if hits else "")


def test_cache_key_invalidation() -> None:
    print("embedding cache keys")
    a, b = vm.chunk_key("hello"), vm.chunk_key("hello ")
    check("different content -> different key", a != b)
    check("same content -> stable key", vm.chunk_key("hello") == a)


if __name__ == "__main__":
    test_strip_placeholders()
    test_corpus_is_clean()
    test_retrieval_ranks_sensibly()
    test_cache_key_invalidation()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
        sys.exit(1)
    print("all checks passed")
