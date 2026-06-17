#!/usr/bin/env python3
"""Canonical machine-readable phase/lane lookup for the workflow contract.

This script is the AUTHORITATIVE machine-readable form of the per-type phase
subset (`workflow/routing.md` "Per-type phase subset") intersected with the
complexity lane (`workflow/routing.md` "Complexity lane"). The prose tables in
`routing.md` are illustrative/derived and cite this script as the source of
truth (Constitution Rule 7).

Input: --type, --complexity, --phase. Output: one `key=value` line naming the
next phase AND whether a HITL gate fires after the phase being LEFT
(`gate=<true|false>`). `deliver` is an explicit non-zero terminal refusal
(AC-2); unknown type/complexity/phase exit non-zero with stderr (AC-11).

The `gate=` token is additive and is emitted BEFORE `phase=` so the historical
`phase=` end-of-line position (relied on by existing callers/tests) is unchanged.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _state_common import emit, fail

# Per-type phase subset (routing.md "Per-type phase subset"). Ordered.
_TYPE_SUBSET: dict[str, list[str]] = {
    "feature": ["spec", "plan", "tasks", "implement", "verify", "deliver"],
    "bugfix": ["spec", "tasks", "implement", "verify", "deliver"],
    "refactor": ["spec", "plan", "tasks", "implement", "verify", "deliver"],
    "spike": ["spec", "implement", "verify", "deliver"],
    "docs": ["spec", "implement", "verify", "deliver"],
    "prd": ["spec", "implement", "verify", "deliver"],
}

# Complexity lane (routing.md "Complexity lane"): phases the lane DROPS from
# the type subset (INTERSECTION, never override). `medium` drops nothing.
# `trivial`/`epic` never reach this lookup (no on-disk state.json).
_LANE_DROPS: dict[str, set[str]] = {
    "small": {"plan", "tasks"},
    "medium": set(),
}

# Phases after which a HITL gate fires, per surviving-gate lane table
# (`workflow/phases.md` "Surviving gates per complexity lane"). The gate is keyed
# on the phase being LEFT. `small` survives gates after `spec` and `verify`;
# `medium` survives gates after `spec`, `tasks`, and `verify`. A gate is never
# reported for a phase the lane drops (it cannot be left if it never runs).
_GATE_AFTER: dict[str, set[str]] = {
    "small": {"spec", "verify"},
    "medium": {"spec", "tasks", "verify"},
}


def _effective_phases(wf_type: str, complexity: str) -> list[str]:
    subset = _TYPE_SUBSET[wf_type]
    dropped = _LANE_DROPS[complexity]
    return [p for p in subset if p not in dropped]


def next_phase(wf_type: str, complexity: str, phase: str) -> str:
    if wf_type not in _TYPE_SUBSET:
        fail(f"unknown type: {wf_type!r} (expected one of {sorted(_TYPE_SUBSET)})")
    if complexity not in _LANE_DROPS:
        fail(
            f"unknown complexity for lane lookup: {complexity!r} "
            f"(expected one of {sorted(_LANE_DROPS)})"
        )
    phases = _effective_phases(wf_type, complexity)
    if phase not in phases:
        fail(
            f"phase {phase!r} not in effective phase set for "
            f"{wf_type}/{complexity}: {phases}"
        )
    if phase == "deliver":
        fail("deliver is the terminal phase: nothing follows it")
    idx = phases.index(phase)
    return phases[idx + 1]


def gate_after(complexity: str, phase: str) -> bool:
    """Whether a HITL gate fires after `phase` is left, for this lane.

    Derived solely from `_GATE_AFTER` (the surviving-gate lane table). Callers
    pass a phase already validated by `next_phase`, so `complexity` is known-good.
    """
    return phase in _GATE_AFTER[complexity]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", required=True, dest="wf_type")
    parser.add_argument("--complexity", required=True)
    parser.add_argument("--phase", required=True)
    args = parser.parse_args(argv)
    result = next_phase(args.wf_type, args.complexity, args.phase)
    gate = gate_after(args.complexity, args.phase)
    emit("next", gate=str(gate).lower(), phase=result)


if __name__ == "__main__":
    main()
