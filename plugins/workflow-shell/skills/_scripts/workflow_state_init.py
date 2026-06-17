#!/usr/bin/env python3
"""Scaffold a new `specs/<NNN>-<slug>/` workflow folder in one call.

Resolves the next monotonic 3-digit ID across BOTH `.claude/PRD/` and
`.claude/specs/`, seeds `state.json` from `workflow/templates/state.json`,
copies the matching `spec-<type>.md` template to `spec.md`, and appends the
`active[]` entry (composing `active_json_mutator.append-active`).

Refuses an unknown type and a colliding spec folder (AC-9 loud-refusal path).
Output/exit discipline is via `_state_common`.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _state_common import atomic_write_json, emit, fail, load_json
import active_json_mutator
from workflow_phase_next import _TYPE_SUBSET

_ID_RE = re.compile(r"^(\d{3})-")
# `docs` may scaffold without a spec template (trivial doc edits); every other
# type seeds spec.md from its template.
_NO_SPEC_TEMPLATE = {"docs"}


def _scan_max_id(directory: Path) -> int:
    highest = 0
    if not directory.is_dir():
        return highest
    for child in directory.iterdir():
        match = _ID_RE.match(child.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def _next_id(claude_dir: Path) -> str:
    highest = max(
        _scan_max_id(claude_dir / "specs"),
        _scan_max_id(claude_dir / "PRD"),
    )
    return f"{highest + 1:03d}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, dest="repo_root")
    parser.add_argument("--type", required=True, dest="wf_type")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--parent-prd", default=None, dest="parent_prd")
    parser.add_argument("--started", required=True)
    args = parser.parse_args(argv)

    if args.wf_type not in _TYPE_SUBSET:
        fail(f"unknown type: {args.wf_type!r} (expected one of {sorted(_TYPE_SUBSET)})")

    claude_dir = Path(args.repo_root) / ".claude"
    templates = claude_dir / "workflow" / "templates"
    specs_dir = claude_dir / "specs"

    next_id = _next_id(claude_dir)
    folder_name = f"{next_id}-{args.slug}"
    folder = specs_dir / folder_name
    if folder.exists():
        fail(f"spec folder already exists: {folder}; refusing to overwrite")

    folder.mkdir(parents=True)

    state = load_json(templates / "state.json")
    state["id"] = folder_name
    state["type"] = args.wf_type
    state["started"] = args.started
    state["parent_prd"] = args.parent_prd
    atomic_write_json(folder / "state.json", state)

    if args.wf_type not in _NO_SPEC_TEMPLATE:
        spec_template = templates / f"spec-{args.wf_type}.md"
        if not spec_template.is_file():
            fail(f"missing spec template: {spec_template}")
        shutil.copy(spec_template, folder / "spec.md")

    active_json_mutator.append_active_entry(
        claude_dir / "active.json",
        id=folder_name,
        path=f"specs/{folder_name}",
        type=args.wf_type,
        phase="spec",
        started=args.started,
    )

    emit("scaffolded", spec=folder_name, phase="spec")


if __name__ == "__main__":
    main()
