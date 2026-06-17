#!/usr/bin/env python3
"""Deterministic mutations on one `specs/<id>/state.json`.

Subcommands:
  advance              close the entry for the phase being LEFT (recording its
                       own verdict; synthesizing the entry if none is open),
                       set `phase` to the next phase (from workflow_phase_next),
                       then append a new open entry for it.
  set-status           set the top-level `status`.
  append-history-note  annotate the CURRENT (last) phase_history entry's `note`
                       in place; never append a new entry.
  rollback             set `phase` to an EARLIER target and append a rollback
                       note entry; refuse equal/later targets and type-skipped
                       phases (AC-5/AC-6).

`phase_history` entries are limited to `{phase, started, completed,
verifier_pass, fix_rounds}` plus optional `note`, matching the
`artifacts.md` schema and the `_phase_ledger.py` reader's tolerated key set
(AC-4). Output/exit discipline is via `_state_common`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _state_common import atomic_write_json, emit, fail, load_json
from workflow_phase_next import _effective_phases, _LANE_DROPS, _TYPE_SUBSET, next_phase


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_verifier_pass(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0"}:
        return False
    if lowered in {"null", "none", "n/a", ""}:
        return None
    fail(f"unrecognized --verifier-pass value: {value!r}")


def _validate_lane(wf_type: str, complexity: str) -> None:
    if wf_type not in _TYPE_SUBSET:
        fail(f"unknown type: {wf_type!r}")
    if complexity not in _LANE_DROPS:
        fail(f"unknown complexity: {complexity!r}")


def cmd_advance(args: argparse.Namespace) -> None:
    state = load_json(args.state)
    current = state.get("phase")
    nxt = next_phase(args.wf_type, args.complexity, current)
    history = state.setdefault("phase_history", [])
    # Close-then-open: the verdict args describe the phase being LEFT (`current`),
    # so they must land on `current`'s entry. Find the open entry labeled
    # `current`; if none exists (fresh init opens `spec` only in `state.phase`,
    # not yet in history), synthesize one so the phase being left is always
    # recorded with its own verdict and label.
    leaving = None
    if history and history[-1].get("phase") == current and history[-1].get("completed") is None:
        leaving = history[-1]
    else:
        leaving = {
            "phase": current,
            "started": state.get("started") or _now_iso(),
            "completed": None,
            "verifier_pass": None,
            "fix_rounds": 0,
        }
        history.append(leaving)
    leaving["completed"] = _now_iso()
    leaving["verifier_pass"] = _parse_verifier_pass(args.verifier_pass)
    leaving["fix_rounds"] = args.fix_rounds
    history.append(
        {
            "phase": nxt,
            "started": _now_iso(),
            "completed": None,
            "verifier_pass": None,
            "fix_rounds": 0,
        }
    )
    state["phase"] = nxt
    atomic_write_json(args.state, state)
    emit("advanced", spec=state.get("id", ""), phase=nxt)


def cmd_set_status(args: argparse.Namespace) -> None:
    state = load_json(args.state)
    state["status"] = args.status
    atomic_write_json(args.state, state)
    emit("status-set", spec=state.get("id", ""), status=args.status)


def cmd_append_history_note(args: argparse.Namespace) -> None:
    state = load_json(args.state)
    history = state.setdefault("phase_history", [])
    # Annotate the CURRENT (last) entry's note; never append a fresh entry
    # (that doubled and mislabeled entries — the 045 corruption). Only when no
    # entry exists yet do we open one for the current phase so the note lands
    # somewhere.
    if not history:
        history.append(
            {
                "phase": state.get("phase", ""),
                "started": state.get("started") or _now_iso(),
                "completed": None,
                "verifier_pass": None,
                "fix_rounds": 0,
            }
        )
    entry = history[-1]
    existing = entry.get("note")
    entry["note"] = f"{existing} {args.note}" if existing else args.note
    atomic_write_json(args.state, state)
    emit("note-appended", spec=state.get("id", ""))


def cmd_rollback(args: argparse.Namespace) -> None:
    _validate_lane(args.wf_type, args.complexity)
    state = load_json(args.state)
    current = state.get("phase")
    phases = _effective_phases(args.wf_type, args.complexity)
    if args.target not in phases:
        fail(
            f"target {args.target!r} is skipped by type {args.wf_type!r} "
            f"(effective phases: {phases})"
        )
    if current not in phases:
        fail(f"current phase {current!r} not in effective phases: {phases}")
    if phases.index(args.target) >= phases.index(current):
        fail(
            f"rollback target {args.target!r} is not earlier than current "
            f"{current!r}; refusing"
        )
    history = state.setdefault("phase_history", [])
    history.append(
        {
            "phase": args.target,
            "started": _now_iso(),
            "completed": None,
            "verifier_pass": None,
            "fix_rounds": 0,
            "note": f"rolled back from {current}: {args.note}",
        }
    )
    state["phase"] = args.target
    atomic_write_json(args.state, state)
    emit("rolled-back", spec=state.get("id", ""), phase=args.target)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_adv = sub.add_parser("advance")
    p_adv.add_argument("--state", required=True)
    p_adv.add_argument("--type", required=True, dest="wf_type")
    p_adv.add_argument("--complexity", required=True)
    p_adv.add_argument("--verifier-pass", required=True, dest="verifier_pass")
    p_adv.add_argument("--fix-rounds", required=True, type=int, dest="fix_rounds")
    p_adv.set_defaults(func=cmd_advance)

    p_status = sub.add_parser("set-status")
    p_status.add_argument("--state", required=True)
    p_status.add_argument("--status", required=True)
    p_status.set_defaults(func=cmd_set_status)

    p_note = sub.add_parser("append-history-note")
    p_note.add_argument("--state", required=True)
    p_note.add_argument("--note", required=True)
    p_note.set_defaults(func=cmd_append_history_note)

    p_rb = sub.add_parser("rollback")
    p_rb.add_argument("--state", required=True)
    p_rb.add_argument("--type", required=True, dest="wf_type")
    p_rb.add_argument("--complexity", required=True)
    p_rb.add_argument("--target", required=True)
    p_rb.add_argument("--note", required=True)
    p_rb.set_defaults(func=cmd_rollback)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
