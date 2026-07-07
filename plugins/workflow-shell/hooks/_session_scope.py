"""Session-scope helpers for the SDK memory pipeline.

Pre-extracts the scope the SDK agent will see:
- The current main-segment of the orchestrator's JSONL (events after the
  last `compact_boundary`).
- The list of per-subagent JSONLs + tool-results under `<S>/`.
- Per-teammate equivalents resolved via the team audit copy.

All functions are pure (no global state, no side effects beyond stderr
warnings) so they can be unit-tested in isolation. The module is read by
`sdk_memory_pipeline.py` at request-build time.

The `find_last_compact_boundary` parser performs a single O(n) pass over
the input file. Malformed lines (partial flushes, invalid JSON) are skipped
without raising — the pipeline must never crash on a mid-deliver write.

Compact-boundary detection requires `type == "system"` AND
`subtype == "compact_boundary"` per
`skills/memory/jsonl-format/SKILL.md § system.subtype enum`. Substring matches
in unrelated payloads do NOT trigger.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


def find_last_compact_boundary(path: str | Path) -> int:
    """Return the byte offset immediately after the last `compact_boundary` line.

    - Returns 0 if the file has no boundary marker (first-deliver fallback,
      AC-17).
    - Returns the offset after the LAST boundary on multi-boundary files
      (AC-3).
    - Skips malformed JSON lines without raising (AC-3 case d).

    Single O(n) pass: we read line-by-line, tracking the byte position after
    each line we consume. When we encounter a boundary marker, we remember
    that post-line offset; the last one wins.
    """
    p = Path(path)
    last_offset = 0
    pos = 0
    with p.open("rb") as fh:
        for raw in fh:
            pos += len(raw)
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("type") == "system" and obj.get("subtype") == "compact_boundary":
                last_offset = pos
    return last_offset


def is_sdk_py_jsonl(path: str | Path) -> bool:
    """True iff the JSONL's first non-`queue-operation` line has `entrypoint == "sdk-py"`.

    Used for self-exclusion (AC-6): the SDK subprocess writes its own JSONL
    into the canonical directory; pipeline must skip its own output to avoid
    a recursive self-read on the next deliver.
    """
    p = Path(path)
    try:
        with p.open("rb") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") == "queue-operation":
                    continue
                return obj.get("entrypoint") == "sdk-py"
    except OSError:
        return False
    return False


def list_session_jsonls(canonical_dir: str | Path, *, exclude_self: bool = True) -> list[Path]:
    """List top-level session JSONLs under `canonical_dir`.

    When `exclude_self=True`, drops any JSONL whose first JSON line marks it
    as an `sdk-py` self-output (AC-6).
    """
    base = Path(canonical_dir)
    if not base.is_dir():
        return []
    results: list[Path] = []
    for entry in sorted(base.glob("*.jsonl")):
        if exclude_self and is_sdk_py_jsonl(entry):
            continue
        results.append(entry)
    return results


# ---- Scope builder (T5.1 + T5.2) -----------------------------------------

# Team-config sessions are recorded as ms-since-epoch in `createdAt`. The
# fallback time window is 24h around that anchor (P5: spec 018 was ~22 min
# wall-clock; 24h is generous headroom).
_FALLBACK_WINDOW_MS = 24 * 60 * 60 * 1000


@dataclass
class TeammateScope:
    name: str
    main: Path | None
    segment_offset: int = 0
    subagents: list[Path] = field(default_factory=list)
    tool_results: list[Path] = field(default_factory=list)


@dataclass
class Scope:
    orchestrator_main: Path
    orchestrator_segment_offset: int
    orchestrator_subagents: list[Path]
    orchestrator_tool_results: list[Path]
    teammates: dict[str, TeammateScope]


def _list_subagents(canonical_dir: Path, session_id: str) -> list[Path]:
    sdir = canonical_dir / session_id / "subagents"
    if not sdir.is_dir():
        return []
    return sorted(p for p in sdir.glob("agent-*.jsonl"))


def _list_tool_results(canonical_dir: Path, session_id: str) -> list[Path]:
    tdir = canonical_dir / session_id / "tool-results"
    if not tdir.is_dir():
        return []
    return sorted(p for p in tdir.glob("*.txt"))


def _first_jsonl_line(path: Path) -> dict | None:
    try:
        with path.open("rb") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(obj, dict) and obj.get("type") != "queue-operation":
                    return obj
    except OSError:
        return None
    return None


def _timestamp_ms(obj: dict | None) -> int | None:
    if not obj:
        return None
    ts = obj.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        # ISO-8601 with millisecond resolution; parse via datetime.
        from datetime import datetime

        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, AttributeError):
        return None


def _fallback_resolve_teammate(
    canonical_dir: Path,
    teammate_name: str,
    orchestrator_cwd: str | None,
    team_created_at_ms: int | None,
) -> str | None:
    """Pick a teammate session-id by cwd + time-window match.

    Conservative: only returns a session-id whose first JSONL line shows
    `cwd == orchestrator_cwd` AND whose timestamp falls within the team
    lifetime window. Returns None if no unique candidate matches.
    """
    candidates: list[tuple[int, str]] = []
    for jsonl in canonical_dir.glob("*.jsonl"):
        # Don't pick up the orchestrator's own JSONL or sdk-py self-output.
        if is_sdk_py_jsonl(jsonl):
            continue
        head = _first_jsonl_line(jsonl)
        if not head:
            continue
        if orchestrator_cwd is not None and head.get("cwd") != orchestrator_cwd:
            continue
        ts_ms = _timestamp_ms(head)
        if team_created_at_ms is not None and ts_ms is not None:
            if ts_ms < team_created_at_ms - _FALLBACK_WINDOW_MS:
                continue
            if ts_ms > team_created_at_ms + _FALLBACK_WINDOW_MS:
                continue
        sid = jsonl.stem
        candidates.append((ts_ms or 0, sid))
    candidates.sort()
    # If candidates collapse to nothing or more than one match, we cannot
    # confidently assign — return None. The caller still emits a warning.
    if len(candidates) == 1:
        return candidates[0][1]
    return None


def _read_team_config(team_config_path: Path | None) -> dict | None:
    if team_config_path is None:
        return None
    if not Path(team_config_path).is_file():
        return None
    try:
        return json.loads(Path(team_config_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_scope(
    canonical_dir: str | Path,
    orchestrator_session_id: str,
    team_config_path: str | Path | None = None,
    *,
    orchestrator_cwd: str | None = None,
) -> Scope:
    """Pre-compute the bounded input set the SDK agent will read.

    - `canonical_dir`: typically `~/.claude/projects/<project-slug>/`.
    - `orchestrator_session_id`: from CLAUDE_SESSION_ID (plumbed via launcher).
    - `team_config_path`: audit copy at `specs/<NNN>/teams/<team-name>/config.json`.
      None when implement phase did not engage Teams.
    - `orchestrator_cwd`: used by the legacy fallback to filter unrelated
      sessions. Defaults to the cwd recorded on the orchestrator JSONL's
      first line.
    """
    base = Path(canonical_dir)
    orch_main = base / f"{orchestrator_session_id}.jsonl"
    orch_offset = find_last_compact_boundary(orch_main) if orch_main.is_file() else 0
    orch_subagents = _list_subagents(base, orchestrator_session_id)
    orch_tool_results = _list_tool_results(base, orchestrator_session_id)

    if orchestrator_cwd is None and orch_main.is_file():
        head = _first_jsonl_line(orch_main)
        if head:
            orchestrator_cwd = head.get("cwd")

    teammates: dict[str, TeammateScope] = {}
    config = _read_team_config(Path(team_config_path) if team_config_path else None)
    if config:
        created_at_ms = config.get("createdAt")
        for member in config.get("members", []):
            name = member.get("name")
            if not name or name == "team-lead":
                continue
            sid = member.get("sessionId")
            if not sid:
                sys.stderr.write(
                    f"SDK memory: teammate {name} sessionId missing; falling back to time-window scan\n"
                )
                sid = _fallback_resolve_teammate(
                    base,
                    name,
                    orchestrator_cwd,
                    created_at_ms,
                )
            tm_main = base / f"{sid}.jsonl" if sid else None
            tm_offset = (
                find_last_compact_boundary(tm_main) if tm_main and tm_main.is_file() else 0
            )
            tm_subs = _list_subagents(base, sid) if sid else []
            tm_tools = _list_tool_results(base, sid) if sid else []
            teammates[name] = TeammateScope(
                name=name,
                main=tm_main if tm_main and tm_main.is_file() else None,
                segment_offset=tm_offset,
                subagents=tm_subs,
                tool_results=tm_tools,
            )

    return Scope(
        orchestrator_main=orch_main,
        orchestrator_segment_offset=orch_offset,
        orchestrator_subagents=orch_subagents,
        orchestrator_tool_results=orch_tool_results,
        teammates=teammates,
    )


def render_scope_section(scope: Scope) -> str:
    """Render the `## Session scope` prompt section per design/02-prompt-structure.md."""
    lines: list[str] = ["## Session scope", ""]
    lines.append(f"Orchestrator main: {scope.orchestrator_main}")
    lines.append(
        f"  segment start byte offset: {scope.orchestrator_segment_offset}"
        "  (events after last compact_boundary)"
    )
    lines.append("")
    lines.append("Orchestrator subagents:")
    if scope.orchestrator_subagents:
        for sub in scope.orchestrator_subagents:
            lines.append(f"  - {sub}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Tool-results (externalized large outputs):")
    if scope.orchestrator_tool_results:
        for tr in scope.orchestrator_tool_results:
            lines.append(f"  - {tr}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Teammates:")
    if not scope.teammates:
        lines.append("  (none — no team engaged this run)")
    else:
        for name in sorted(scope.teammates.keys()):
            ts = scope.teammates[name]
            lines.append(f"  {name}:")
            main_str = str(ts.main) if ts.main else "(unresolved)"
            lines.append(f"    main: {main_str}  (segment offset: {ts.segment_offset})")
            if ts.subagents:
                lines.append("    subagents:")
                for sub in ts.subagents:
                    lines.append(f"      - {sub}")
            else:
                lines.append("    subagents: (none)")
    return "\n".join(lines) + "\n"
