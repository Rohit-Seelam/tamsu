"""Pure proposal-schema validator for the SDK memory pipeline (spec 038 M1, AC-1).

The propose→write pivot splits the pipeline into two halves: the LLM does ONE
bounded read-once pass returning a single structured PROPOSAL object (touching no
files), and a deterministic Python writer (`_memory_writer.py`) consumes it. This
module is the pure gate between the two — in the `_silo_shape_check.py` /
`_budget_check.py` mould: a pure function, no file I/O, separate from LLM content
generation. A non-empty finding list maps to pipeline exit 31 (wired in M9),
surfaced never swallowed (Constitution Rule 2).

Proposal object shape (plan.md "Resolved decisions" #1):

    {
      "decisions":      [{"title", "hook", "body"}],
      "project_topics": [{"slug", "title", "hook", "body", "append"}],
      "silos":          {"<agent>": [{"title", "topic_slug", "hook"}]},
      "shared_topics":  [{"slug", "title", "hook", "body"}],
    }

Constraints enforced here:
  - the four top-level keys MUST all be present;
  - `decisions` / `project_topics` / `shared_topics` are lists; `silos` is a dict;
  - a `silos` key NOT in `SILO_AGENTS` is NOT a structural finding (spec 047 AC-4):
    it is a recoverable writer-drop, not exit 31 — see `_memory_writer`;
  - each silo entry's `topic_slug` MUST be a bare slug (no `/`) referencing a ROOT
    `agent-memory/topics/<slug>.md`, never a nested `<agent>/topics/` path;
  - each entry carries its required string fields.

Spec 042 narrows what is STRUCTURAL (exit 31) here: an *unresolved* silo
`topic_slug` (a well-formed bare slug that simply has no backing shared-topic
body yet) is NO LONGER a finding — it is a recoverable WRITER-DROP handled by
`_memory_writer._drop_dead_silo_lines` (WARN + drop, the rest of the proposal is
written). Exit 31 stays reserved for genuine structural invalidity: missing
required keys, wrong types, a non-dict entry, or a nested `/` in a slug. The 041
"no silo dead link ever reaches disk" guarantee is preserved by the writer-drop.
"""

from __future__ import annotations

from typing import Any

# Closed set of silo agents carrying `memory: project` (spec 034). Single-sourced
# here to keep this module dependency-free of the heavier pipeline entry script.
SILO_AGENTS = (
    "product-manager",
    "architect",
    "backend-engineer",
    "task-decomposer",
    "qa-engineer",
    "cross-checker",
)

_REQUIRED_TOP_LEVEL = ("decisions", "project_topics", "silos", "shared_topics")

_DECISION_FIELDS = ("title", "hook", "body")
_PROJECT_TOPIC_FIELDS = ("slug", "title", "hook", "body")
_SILO_ENTRY_FIELDS = ("title", "topic_slug", "hook")
_SHARED_TOPIC_FIELDS = ("slug", "title", "hook", "body")


def _check_entry_fields(
    entry: Any, fields: tuple[str, ...], where: str
) -> list[str]:
    findings: list[str] = []
    if not isinstance(entry, dict):
        findings.append(f"{where}: entry must be an object, got {type(entry).__name__}")
        return findings
    for field in fields:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(f"{where}: missing or empty required field {field!r}")
    return findings


def validate_proposal(
    obj: Any, existing_canonical_slugs: frozenset[str] = frozenset()
) -> list[str]:
    """Return a sorted list of schema findings (empty == valid).

    Pure: no file I/O, no LLM. A non-empty list maps to pipeline exit 31.

    `existing_canonical_slugs` is retained for signature stability (the caller at
    `sdk_memory_pipeline._proposal_schema_validate` still threads it). Spec 042
    moved the silo `topic_slug` RESOLUTION check out of this validator: an
    unresolved slug is now a writer-recoverable drop, not an exit-31 finding (see
    module docstring). This validator therefore no longer consults the parameter
    for resolution; it remains a pure STRUCTURAL gate.
    """
    findings: list[str] = []

    if not isinstance(obj, dict):
        return [f"proposal must be an object, got {type(obj).__name__}"]

    for key in _REQUIRED_TOP_LEVEL:
        if key not in obj:
            findings.append(f"proposal missing required top-level key {key!r}")

    decisions = obj.get("decisions")
    if "decisions" in obj:
        if not isinstance(decisions, list):
            findings.append("'decisions' must be a list")
        else:
            for i, entry in enumerate(decisions):
                findings.extend(
                    _check_entry_fields(entry, _DECISION_FIELDS, f"decisions[{i}]")
                )

    project_topics = obj.get("project_topics")
    if "project_topics" in obj:
        if not isinstance(project_topics, list):
            findings.append("'project_topics' must be a list")
        else:
            for i, entry in enumerate(project_topics):
                findings.extend(
                    _check_entry_fields(
                        entry, _PROJECT_TOPIC_FIELDS, f"project_topics[{i}]"
                    )
                )

    silos = obj.get("silos")
    if "silos" in obj:
        if not isinstance(silos, dict):
            findings.append("'silos' must be an object keyed by agent name")
        else:
            for agent, entries in silos.items():
                # Spec 047 AC-4: an UNKNOWN silo agent key is NO LONGER a structural
                # finding (exit 31 discarded the whole proposal at 045's deliver).
                # It is now a recoverable WRITER-DROP (`_memory_writer` drops that one
                # key + WARN, writes the rest) — parallel to spec 042's unresolved
                # `topic_slug` drop. Exit 31 stays reserved for genuine structural
                # invalidity (wrong types, non-dict entry, nested `/` in a slug). The
                # entries under an unknown key are still STRUCTURALLY validated below
                # so a malformed entry is still caught regardless of the key.
                if not isinstance(entries, list):
                    findings.append(f"silos[{agent!r}] must be a list")
                    continue
                for i, entry in enumerate(entries):
                    where = f"silos[{agent!r}][{i}]"
                    findings.extend(_check_entry_fields(entry, _SILO_ENTRY_FIELDS, where))
                    if isinstance(entry, dict):
                        slug = entry.get("topic_slug")
                        if isinstance(slug, str) and "/" in slug:
                            findings.append(
                                f"{where}: topic_slug {slug!r} must be a bare slug "
                                f"referencing a ROOT agent-memory/topics/<slug>.md "
                                f"target — a nested path (containing '/') is forbidden"
                            )

    shared_topics = obj.get("shared_topics")
    if "shared_topics" in obj:
        if not isinstance(shared_topics, list):
            findings.append("'shared_topics' must be a list")
        else:
            for i, entry in enumerate(shared_topics):
                findings.extend(
                    _check_entry_fields(
                        entry, _SHARED_TOPIC_FIELDS, f"shared_topics[{i}]"
                    )
                )

    return sorted(findings)


# Phrases that mark an entry as DEFERRED WORK rather than a landed decision —
# these belong in `workflow/queue.md`, not `memory/` (spec 047 AC-6b). Matched
# case-insensitively against an outer-memory entry's title/hook/body.
_DEFERRED_WORK_MARKERS = (
    "followup",
    "follow-up",
    "follow up",
    "todo",
    "bundle with next",
    "bundle into next",
    "defer",
    "deferred",
    "in a later spec",
    "next touch",
)


def validate_memory_queue_boundary(obj: Any) -> list[str]:
    """SOFT guard (spec 047 AC-6b): surface outer-memory entries framed as DEFERRED
    WORK as WARNs — NOT exit-31 findings.

    `memory/` holds landed decisions and characterization findings; pending work
    ("followup"/"TODO"/"bundle with next touch") belongs in `workflow/queue.md`.
    This is advisory: the caller logs each WARN (Rule 2 — surfaced) and STILL
    writes the proposal. Applies to OUTER memory only — `decisions` and
    `project_topics`. Silo craft notes and shared topics are out of scope (a silo
    hook may legitimately reference a followup in its own craft)."""
    if not isinstance(obj, dict):
        return []
    warnings: list[str] = []

    def _scan(entry: Any, where: str) -> None:
        if not isinstance(entry, dict):
            return
        haystack = " ".join(
            str(entry.get(f, "")) for f in ("title", "hook", "body")
        ).lower()
        for marker in _DEFERRED_WORK_MARKERS:
            if marker in haystack:
                label = entry.get("title") or entry.get("slug") or where
                warnings.append(
                    f"{where}: {label!r} reads as deferred work ({marker!r}) — "
                    f"pending work belongs in workflow/queue.md, not memory/"
                )
                return

    for i, entry in enumerate(obj.get("decisions") or []):
        _scan(entry, f"decisions[{i}]")
    for i, entry in enumerate(obj.get("project_topics") or []):
        _scan(entry, f"project_topics[{i}]")

    return sorted(warnings)
