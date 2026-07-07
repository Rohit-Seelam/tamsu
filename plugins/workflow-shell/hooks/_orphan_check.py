"""Deterministic orphan / dead-link check for a memory store (spec 035 M4).

A memory store is a directory holding `MEMORY.md` plus a `topics/` subdirectory.
This checker diffs the `topics/*.md` files on disk against the
`[...](topics/<file>.md)` link lines in `MEMORY.md` and reports:

  - ORPHAN: a `topics/<file>.md` on disk with no matching index line;
  - DEAD LINK: an index line pointing at a `topics/<file>.md` absent from disk.

It is the mechanical backstop to the prompt-side index reconciliation (AC-9) —
the LLM cross-checker missed orphans across >=3 delivers (spec 032), so this
non-LLM check exits non-zero on any mismatch (AC-17, Rule 2: no silent
suppression).

Only `topics/<file>.md` link lines are parsed, so headings, preamble, and
external links (e.g. `https://.../topics/foo.md`) never false-positive.

Standalone: `python _orphan_check.py <store-dir> [<store-dir> ...]` exits
non-zero if any store has a finding.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Match `](topics/<file>.md)` only when `topics/` is the link target ROOT.
# Requiring `](` immediately before `topics/` excludes external URLs and
# absolute paths (e.g. `](https://example.com/topics/foo.md)`), so headings,
# preamble, and non-store links never false-positive.
_LINK_RE = re.compile(r"\]\(topics/([^()/\s]+\.md)\)")


def _indexed_topics(memory_md: Path) -> set[str]:
    if not memory_md.is_file():
        return set()
    text = memory_md.read_text(encoding="utf-8")
    return set(_LINK_RE.findall(text))


def _topic_files(topics_dir: Path) -> set[str]:
    if not topics_dir.is_dir():
        return set()
    return {p.name for p in topics_dir.glob("*.md")}


def check_store(store_dir: str | Path) -> list[str]:
    """Return a sorted list of human-readable findings for one store.

    Empty list == clean store.
    """
    store = Path(store_dir)
    memory_md = store / "MEMORY.md"
    topics_dir = store / "topics"

    indexed = _indexed_topics(memory_md)
    on_disk = _topic_files(topics_dir)

    findings: list[str] = []
    for orphan in sorted(on_disk - indexed):
        findings.append(f"ORPHAN: topics/{orphan} has no index line in {memory_md}")
    for dead in sorted(indexed - on_disk):
        findings.append(f"DEAD LINK: {memory_md} indexes topics/{dead} but the file is absent")
    return findings


def check_silo_store(agent_dir: str | Path, shared_topics_dir: str | Path) -> list[str]:
    """Orphan / dead-link check for one per-agent silo (spec 036 M3, AC-11).

    A silo differs from an outer store: the agent folder
    (`agent-memory/<agent>/`) holds only `MEMORY.md`, whose
    `[...](topics/<file>.md)` index lines reference the SHARED ROOT
    `agent-memory/topics/` — NOT a nested `<agent>/topics/`. So the index lives
    in `agent_dir` while the topic bodies live in `shared_topics_dir`.

    DEAD LINK: an index line pointing at a `topics/<file>.md` absent from the
    shared store. (ORPHAN detection — a shared topic with no referrer — is NOT a
    silo-level concern: a shared topic may legitimately be referenced by a
    different agent's silo, so it is checked once at the shared-store level by
    the caller, not per silo.)
    """
    agent = Path(agent_dir)
    memory_md = agent / "MEMORY.md"
    indexed = _indexed_topics(memory_md)
    on_disk = _topic_files(Path(shared_topics_dir))

    findings: list[str] = []
    for dead in sorted(indexed - on_disk):
        findings.append(
            f"DEAD LINK: {memory_md} indexes topics/{dead} but the shared "
            f"agent-memory/topics/ file is absent"
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: _orphan_check.py <store-dir> [<store-dir> ...]", file=sys.stderr)
        return 2
    total = 0
    for store in argv:
        findings = check_store(store)
        for f in findings:
            print(f"sdk_memory orphan-check: {f}", file=sys.stderr)
        total += len(findings)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
