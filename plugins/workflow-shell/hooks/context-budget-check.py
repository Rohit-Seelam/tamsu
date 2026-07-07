#!/usr/bin/env python3
"""PostToolUse hook: warn the orchestrator before its context overflows.

The main session runs on a 1M-token window but Claude Code surfaces no
"you are at N% of context" signal. Without it the orchestrator can drift past
the safe working range and get forced into a disruptive mid-task double
`/compact`. This hook reads the session transcript after every tool call,
computes the main thread's current context occupancy from the last
main-thread assistant record's `message.usage`, and — once occupancy crosses a
configurable threshold — injects a one-time instruction (per rising 50K band)
telling the agent to stop and run `/compact`.

Graceful degradation is a hard requirement, not an oversight: a context-budget
guard that could itself wedge the workflow would be worse than no guard. Every
error/edge condition (missing transcript path, unreadable file, all-malformed
lines, no qualifying main-thread assistant record) yields a silent exit 0 with
NOTHING on stdout. This is the AC-5 contract and the constitution Rule 2
"reason in the artifact" carve-out — each silent path maps to a named, tested
condition, not a swallowed bug.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

DEFAULT_THRESHOLD = 350000
BAND_SIZE = 50000
TAIL_BYTES = 64 * 1024


def _resolve_threshold() -> int:
    raw = os.environ.get("CONTEXT_BUDGET_THRESHOLD")
    if raw is None:
        return DEFAULT_THRESHOLD
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


def _state_dir() -> str:
    return os.environ.get("CONTEXT_BUDGET_STATE_DIR") or tempfile.gettempdir()


def _marker_path(session_id: str) -> str:
    return os.path.join(_state_dir(), f"context-budget-{session_id}.band")


def _read_last_warned_band(session_id: str) -> int:
    try:
        with open(_marker_path(session_id), encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return -1


def _write_warned_band(session_id: str, band: int) -> None:
    try:
        with open(_marker_path(session_id), "w", encoding="utf-8") as fh:
            fh.write(str(band))
    except OSError:
        # A failed marker write only costs us a duplicate warning later; it must
        # never escalate into a non-zero exit that blocks the tool call.
        pass


def _tail_lines(path: str) -> list[str]:
    """Return the lines from the last ~TAIL_BYTES of the file.

    Reads a bounded window from the END so a ~21K-line transcript is not parsed
    in full on every tool call. The first (possibly partial) line of the window
    is dropped since it may be truncated mid-record.
    """
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        start = max(0, size - TAIL_BYTES)
        fh.seek(start)
        chunk = fh.read()
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    return lines


def _occupancy_from_usage(usage: dict) -> int:
    total = 0
    for key in (
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        val = usage.get(key, 0)
        if isinstance(val, (int, float)):
            total += int(val)
    return total


def _last_main_thread_occupancy(lines: list[str]) -> int | None:
    """Scan backward for the last main-thread assistant record's occupancy.

    Main thread = `isSidechain` falsy/absent. Returns None when no qualifying
    record (assistant + main-thread + `message.usage`) is found.
    """
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        if record.get("isSidechain"):
            continue
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        return _occupancy_from_usage(usage)
    return None


def _emit_warning(occupancy: int, threshold: int) -> None:
    additional = (
        f"CONTEXT-WATCH: orchestrator context is ~{occupancy} tokens "
        f"(threshold {threshold}). Stop now, run /compact, then resume."
    )
    system = (
        f"Context near budget (~{occupancy} tokens). Run /compact."
    )
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": additional,
        },
        "systemMessage": system,
    }
    print(json.dumps(payload))


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw)
    except (ValueError, TypeError):
        return 0
    if not isinstance(event, dict):
        return 0

    transcript_path = event.get("transcript_path")
    session_id = event.get("session_id")
    if not transcript_path or not session_id:
        return 0

    try:
        lines = _tail_lines(transcript_path)
    except OSError:
        return 0

    occupancy = _last_main_thread_occupancy(lines)
    if occupancy is None:
        return 0

    threshold = _resolve_threshold()
    if occupancy < threshold:
        return 0

    band = occupancy // BAND_SIZE * BAND_SIZE
    last_warned = _read_last_warned_band(session_id)
    if band <= last_warned:
        return 0

    _write_warned_band(session_id, band)
    _emit_warning(occupancy, threshold)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Last-resort guard: the hook is advisory and MUST NOT block a tool call
        # on any unforeseen error (AC-5). Silent exit 0, nothing on stdout.
        sys.exit(0)
