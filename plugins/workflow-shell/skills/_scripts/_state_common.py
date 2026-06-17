"""Shared output, exit, and atomic-write discipline for the workflow-state
mutation scripts.

All four state scripts (`workflow_phase_next.py`, `state_json_mutator.py`,
`active_json_mutator.py`, `workflow_state_init.py`) route success output
through `emit()` and failures through `fail()`, so the one-line `key=value`
stdout contract (AC-10) and the non-zero-exit-with-stderr contract (AC-11)
live in ONE place, not copied four times.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def emit(label: str, **fields: Any) -> None:
    """Print exactly one `key=value` confirmation line to stdout.

    Never prints a JSON object dump: a value containing a brace is a sign the
    caller is leaking file contents, so it is refused loudly (AC-10).
    """
    parts = [label] if label else []
    for key, value in fields.items():
        text = str(value)
        if "{" in text or "}" in text:
            raise ValueError(f"emit() refuses brace-bearing value for {key!r}")
        parts.append(f"{key}={text}")
    line = " ".join(parts)
    if "{" in line or "}" in line:
        raise ValueError("emit() refuses brace-bearing output")
    sys.stdout.write(line + "\n")


def fail(msg: str, code: int = 1) -> None:
    """Write a non-empty message to stderr and exit non-zero (AC-11)."""
    if code == 0:
        code = 1
    sys.stderr.write(msg.rstrip("\n") + "\n")
    raise SystemExit(code)


def load_json(path: str | Path) -> Any:
    """Read and parse a JSON file, failing loudly on missing/malformed input."""
    p = Path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"file not found: {p}")
    except json.JSONDecodeError as exc:
        fail(f"malformed JSON in {p}: {exc}")


def atomic_write_json(path: str | Path, data: Any) -> None:
    """Serialize `data` to JSON and replace `path` atomically.

    The data is serialized to a string FIRST, so a serialization error leaves
    the existing file untouched and drops no temp file. The temp file is
    written in the target's directory (same filesystem) and renamed over the
    target, which is atomic on POSIX.
    """
    p = Path(path)
    payload = json.dumps(data, indent=2) + "\n"
    directory = p.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, str(p))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
