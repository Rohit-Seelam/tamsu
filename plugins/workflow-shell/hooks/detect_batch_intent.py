"""Detect multi-spec batch-intake intent in a top-level user prompt.

Single source of truth for the detection heuristic. The human-readable spec
lives at
`.claude/specs/024-batch-spec-planning/design/01-detection-heuristic.md`;
the orchestrator's "Batch intake" subsection in `agents/orchestrator.md`
cites this module by path.

Public API:
    detect_batch_intent(prompt: str) -> bool

Returns True when the prompt is multi-spec in intent and the orchestrator
should divert to the batch-intake path. False for all single-spec prompts.

See `design/01-detection-heuristic.md` for positive triggers, negative
cases, and known v1 limitations.
"""

from __future__ import annotations

import re

_SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+"
_SLUG_RE = re.compile(_SLUG)

_IMPERATIVE_VERBS = (
    "file",
    "create",
    "add",
    "build",
    "start",
    "queue",
    "make",
    "implement",
    "ship",
    "land",
    "plan",
    "do",
)

# Anchor for an imperative verb beginning a clause / sentence / line.
# Match the verb when it follows sentence-start, newline, or a sentence-end
# punctuation. This excludes verbs that appear in the middle of prose (e.g.,
# "the foo-bar handler" — no verb match — or "fix the timeout" — `fix` not
# in cue list).
_IMPERATIVE_CLAUSE_RE = re.compile(
    r"(?:\A|[\n.;])\s*"
    r"\b(?:" + "|".join(_IMPERATIVE_VERBS) + r")\b",
    re.IGNORECASE,
)

# After an imperative clause anchor, slugs are considered "in imperative
# position" until the end of that clause. A clause ends at: sentence-end
# punctuation (. ; !), a paragraph break (double newline), or after this
# many characters — whichever comes first. The character budget is generous
# enough to capture a comma-separated slug list immediately after the verb.
_CLAUSE_CHAR_BUDGET = 240
_CLAUSE_END_RE = re.compile(r"[.!?]\s|\n\s*\n")

# Explicit batch prefix: `batch:` or `queue these:` at the start of the
# prompt (allow one optional opening sentence ≤80 chars). Case-insensitive.
_BATCH_PREFIX_RE = re.compile(
    r"\A(?:[^\n]{0,80}\n)?\s*(?:batch:|queue these:)",
    re.IGNORECASE,
)


def _imperative_position_slugs(prompt: str) -> set[str]:
    """Return distinct slugs that appear in imperative position.

    A slug is "in imperative position" when it sits inside a clause that
    begins with an imperative verb cue. Implementation: for each imperative
    verb anchor, take a forward window up to clause end (sentence-end punct,
    paragraph break, or `_CLAUSE_CHAR_BUDGET` chars), and collect every slug
    in that window.
    """
    slugs: set[str] = set()
    for anchor in _IMPERATIVE_CLAUSE_RE.finditer(prompt):
        start = anchor.end()
        window = prompt[start : start + _CLAUSE_CHAR_BUDGET]
        clause_end = _CLAUSE_END_RE.search(window)
        if clause_end is not None:
            window = window[: clause_end.start()]
        for m in _SLUG_RE.finditer(window):
            slugs.add(m.group(0).lower())
    return slugs


def _explicit_batch_slugs(prompt: str) -> set[str]:
    """Distinct slugs found in an explicit batch-prefixed prompt."""
    if not _BATCH_PREFIX_RE.search(prompt):
        return set()
    body = _BATCH_PREFIX_RE.split(prompt, maxsplit=1)[-1]
    return {m.group(0).lower() for m in _SLUG_RE.finditer(body)}


def detect_batch_intent(prompt: str) -> bool:
    """Return True iff the cleaned prompt encodes multi-spec batch intent.

    See `design/01-detection-heuristic.md` for the full rule.
    """
    if not prompt or not prompt.strip():
        return False

    # Trigger 1: ≥3 distinct slugs in imperative position.
    if len(_imperative_position_slugs(prompt)) >= 3:
        return True

    # Trigger 2: explicit `batch:` / `queue these:` prefix with ≥2 slugs.
    if len(_explicit_batch_slugs(prompt)) >= 2:
        return True

    return False
