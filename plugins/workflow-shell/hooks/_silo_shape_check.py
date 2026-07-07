"""Deterministic silo-shape check for the SDK memory pipeline (spec 036 M4, AC-8).

035 leaked forbidden nested `agent-memory/<agent>/topics/` paths even though the
prompt directive AND `build_silo_index`'s build-time guard reject them — the live
LLM wrote files directly, bypassing the builder. This is the on-disk backstop, in
the `_orphan_check.py` mould: a pure function that scans the silo store for any
nested `<agent>/topics/` path and returns findings (the pipeline maps a non-empty
list to exit 30 — surfaced, never swallowed: Rule 2).

Shape contract (spec 034/036): per-agent silo folders
(`agent-memory/<agent>/`) hold ONLY `MEMORY.md`; ALL topic bodies live at the
ROOT shared store `agent-memory/topics/`. The ROOT `topics/` dir is the one
sanctioned `topics/` directory; any OTHER `topics/` directory nested under an
agent folder is forbidden.

Standalone: `python _silo_shape_check.py <agent-memory-dir>` exits non-zero on
any nested path.
"""

from __future__ import annotations

import sys
from pathlib import Path


def check_silo_shape(agent_memory_dir: str | Path) -> list[str]:
    """Return a sorted list of findings for forbidden nested silo paths.

    Empty list == clean. A finding is any `topics/` directory (or `.md` file
    directly under a path component named `topics`) nested below a per-agent
    folder, i.e. `agent-memory/<agent>/topics/...`. The ROOT shared store
    `agent-memory/topics/` is sanctioned and never flagged.
    """
    root = Path(agent_memory_dir)
    if not root.is_dir():
        return []

    findings: list[str] = []
    for path in sorted(root.rglob("topics")):
        if not path.is_dir():
            continue
        rel_parts = path.relative_to(root).parts
        # Sanctioned ROOT shared store: exactly `<root>/topics`.
        if rel_parts == ("topics",):
            continue
        # Anything else with a `topics` component is a nested per-agent path.
        findings.append(
            f"NESTED SILO PATH: forbidden agent-memory/{'/'.join(rel_parts)} "
            f"— per-agent folders hold only MEMORY.md; topic bodies live at the "
            f"ROOT agent-memory/topics/"
        )
    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: _silo_shape_check.py <agent-memory-dir>", file=sys.stderr)
        return 2
    total = 0
    for root in argv:
        findings = check_silo_shape(root)
        for f in findings:
            print(f"sdk_memory silo-shape-check: {f}", file=sys.stderr)
        total += len(findings)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
