"""Deterministic per-deliver write-budget check for the SDK memory pipeline (spec 036 M2).

035 over-produced (~100 files for one spec) because the live LLM ignored the
prompt-only budget. This is the mechanical backstop, in the `_orphan_check.py`
mould: a pure function, separate from LLM content generation, that counts the
files written across the four memory stores from a before/after snapshot diff
and reports any over-budget condition (the pipeline maps a non-empty finding
list to exit 29 — surfaced, never swallowed: Rule 2).

The four stores:
  - outer project `memory/topics/`            (canonical + repo mirror)
  - per-agent silos `agent-memory/<agent>/`   (canonical-only)
  - shared `agent-memory/topics/`             (canonical-only)

Per-store limits (exact, AC-1 / AC-2 / AC-3):
  - `memory/topics/decisions.md`                          ≤ 1 new entry
  - project spec-topics (new `memory/topics/*.md` other
    than `decisions.md`)                                  ≤ 2
  - each WORKED-agent silo (`agent-memory/<agent>/`)      ≤ 1 new craft-note
  - a silo for an agent NOT in the phase ledger           → 0 (any new note flags)
  - shared `agent-memory/topics/`                         ≤ 1 new note
  - total per-deliver touch ceiling                       ≤ 12

Worked agents are resolved deterministically from the spec's phase ledger
(`_phase_ledger.build_phase_ledger`), NOT LLM judgement — the caller passes the
resolved set in.

Snapshot keys are store-tagged so a file touched in BOTH the canonical and the
repo mirror (e.g. `decisions.md`) dedupes to ONE logical touch rather than two.
"""

from __future__ import annotations

from pathlib import Path

DECISIONS_LIMIT = 1
SPEC_TOPICS_LIMIT = 2
SILO_LIMIT = 1
SHARED_TOPICS_LIMIT = 1
TOTAL_CEILING = 12

SILO_AGENTS = (
    "product-manager",
    "architect",
    "backend-engineer",
    "task-decomposer",
    "qa-engineer",
    "cross-checker",
)


# Deterministic phase -> silo-agent mapping (workflow/phases.md:24-28). Used to
# resolve "which agents worked this spec" from the phase ledger WITHOUT LLM
# judgement: an agent is "worked" iff a phase it owns appears in phase_history.
_PHASE_AGENTS: dict[str, tuple[str, ...]] = {
    "spec": ("product-manager",),
    "plan": ("architect",),
    "tasks": ("task-decomposer",),
    "implement": ("backend-engineer", "qa-engineer"),
    "verify": ("qa-engineer", "cross-checker"),
}


def resolve_worked_agents(ledger: list[dict[str, str]]) -> set[str]:
    """Resolve the set of silo agents that worked the spec, from the phase ledger.

    Deterministic (NOT LLM judgement): an agent is "worked" iff a phase it owns
    appears in `phase_history`. The ledger is the rendered list from
    `_phase_ledger.build_phase_ledger` (each entry carries a `phase` key)."""
    worked: set[str] = set()
    for entry in ledger:
        phase = entry.get("phase", "")
        worked.update(_PHASE_AGENTS.get(phase, ()))
    return worked


def _scan_dir(directory: Path, kind: str, key_prefix: str) -> dict[str, int]:
    """Map `<kind>:<logical-name>` -> mtime_ns for every `*.md` in `directory`.

    `key_prefix` distinguishes silo-agent scans. The logical name deliberately
    OMITS the store root so a canonical/repo pair of the same file collapses to
    one key (no double-count across mirror copies)."""
    out: dict[str, int] = {}
    if not directory.is_dir():
        return out
    for path in directory.glob("*.md"):
        out[f"{kind}:{key_prefix}{path.name}"] = path.stat().st_mtime_ns
    return out


def snapshot_stores(
    canonical_dir: str | Path,
    repo_dir: str | Path,
) -> dict[str, int]:
    """Snapshot all four memory stores into a single `key -> mtime_ns` map.

    Keys are store-CLASS tagged (not store-LOCATION tagged) so the same logical
    file mirrored into both the canonical and repo `memory/topics/` dirs maps to
    one key and counts as a single touch."""
    canonical = Path(canonical_dir)
    repo = Path(repo_dir)
    snapshot: dict[str, int] = {}
    # The silo/shared base lives UNDER the auto-memory root memory/ (spec 047 AC-1)
    # — kept in lockstep with `_memory_writer.agent_memory_base` (single shape).
    agent_memory = canonical / "memory" / "agent-memory"
    # Outer project topics: union of canonical + repo (deduped by class:name key).
    for store_root in (canonical / "memory" / "topics", repo / "memory" / "topics"):
        snapshot.update(_scan_dir(store_root, "outer", ""))
    # Per-agent silos (canonical-only): one MEMORY.md (+ any md) per agent folder.
    for agent in SILO_AGENTS:
        snapshot.update(
            _scan_dir(agent_memory / agent, "silo", f"{agent}/")
        )
    # Shared cross-agent topics (canonical-only).
    snapshot.update(
        _scan_dir(agent_memory / "topics", "shared", "")
    )
    return snapshot


def _changed_keys(before: dict[str, int], after: dict[str, int]) -> set[str]:
    """Keys whose file was created or whose mtime changed between snapshots."""
    changed: set[str] = set()
    for key, mtime in after.items():
        if before.get(key) != mtime:
            changed.add(key)
    return changed


def check_budget(
    *,
    before: dict[str, int],
    after: dict[str, int],
    worked_agents: set[str],
) -> list[str]:
    """Return a sorted list of human-readable over-budget findings.

    Empty list == within budget. A non-empty list maps to pipeline exit 29.
    """
    changed = _changed_keys(before, after)

    decisions_touches = 0
    spec_topic_touches = 0
    shared_touches = 0
    silo_touches: dict[str, int] = {}

    for key in changed:
        kind, _, name = key.partition(":")
        if kind == "outer":
            if name == "decisions.md":
                decisions_touches += 1
            else:
                spec_topic_touches += 1
        elif kind == "shared":
            shared_touches += 1
        elif kind == "silo":
            agent = name.split("/", 1)[0]
            silo_touches[agent] = silo_touches.get(agent, 0) + 1

    findings: list[str] = []
    if decisions_touches > DECISIONS_LIMIT:
        findings.append(
            f"OVER BUDGET: memory/topics/decisions.md touched "
            f"{decisions_touches} times (limit {DECISIONS_LIMIT})"
        )
    if spec_topic_touches > SPEC_TOPICS_LIMIT:
        findings.append(
            f"OVER BUDGET: project spec-topics (memory/topics/*.md) "
            f"created {spec_topic_touches} (limit {SPEC_TOPICS_LIMIT})"
        )
    if shared_touches > SHARED_TOPICS_LIMIT:
        findings.append(
            f"OVER BUDGET: shared agent-memory/topics/ "
            f"created {shared_touches} (limit {SHARED_TOPICS_LIMIT})"
        )
    for agent in sorted(silo_touches):
        count = silo_touches[agent]
        if agent not in worked_agents:
            findings.append(
                f"OVER BUDGET: silo agent-memory/{agent}/ written "
                f"({count}) but {agent} did not work this spec (limit 0)"
            )
        elif count > SILO_LIMIT:
            findings.append(
                f"OVER BUDGET: silo agent-memory/{agent}/ touched "
                f"{count} times (limit {SILO_LIMIT})"
            )

    total = decisions_touches + spec_topic_touches + shared_touches + sum(
        silo_touches.values()
    )
    if total > TOTAL_CEILING:
        findings.append(
            f"OVER BUDGET: total per-deliver touches {total} "
            f"exceed ceiling {TOTAL_CEILING}"
        )

    return sorted(findings)
