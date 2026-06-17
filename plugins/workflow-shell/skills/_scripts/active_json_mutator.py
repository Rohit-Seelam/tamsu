#!/usr/bin/env python3
"""Deterministic array ops on `.claude/active.json`.

Subcommands (matching the `artifacts.md` active.json schema):
  append-active   append an entry to `active[]`; refuses if it would make
                  len(active) > 1 (single-active invariant, AC-8).
  append-queued   append a `{id, path, type, phase:"spec", queued_at}` entry
                  to `queued[]`.
  promote         move an entry from `queued[]` to `active[]`; refuses if the
                  active slot is occupied or the id is not queued.
  archive         move an entry from `active[]` to `archived[]`; refuses a
                  double-archive of an id not in `active[]`.
  mirror-phase    update `active[i].phase` for a matching id.

Readers use `.get("queued", [])` for backward compat with v1-shape files
(`artifacts.md` "Backward-compat"). Output/exit discipline is via
`_state_common`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _state_common import atomic_write_json, emit, fail, load_json


def append_active_entry(
    active_path: str,
    *,
    id: str,
    path: str,
    type: str,
    phase: str,
    started: str,
) -> None:
    """Append one entry to `active[]`, enforcing the single-active invariant.

    Shared by the `append-active` subcommand and `workflow_state_init.py`, so
    the invariant lives in one place. Writes the file; does NOT print — the
    caller owns the one-line confirmation (AC-10).
    """
    data = load_json(active_path)
    active = data.setdefault("active", [])
    if len(active) >= 1:
        fail(
            "single-active invariant: active[] already holds an entry "
            f"({active[0].get('id')}); refusing to append a second"
        )
    active.append(
        {
            "id": id,
            "path": path,
            "type": type,
            "phase": phase,
            "started": started,
        }
    )
    atomic_write_json(active_path, data)


def cmd_append_active(args: argparse.Namespace) -> None:
    append_active_entry(
        args.active,
        id=args.id,
        path=args.path,
        type=args.type,
        phase=args.phase,
        started=args.started,
    )
    emit("active-appended", id=args.id)


def cmd_append_queued(args: argparse.Namespace) -> None:
    data = load_json(args.active)
    queued = data.get("queued")
    if queued is None:
        queued = []
        data["queued"] = queued
    queued.append(
        {
            "id": args.id,
            "path": args.path,
            "type": args.type,
            "phase": "spec",
            "queued_at": args.queued_at,
        }
    )
    atomic_write_json(args.active, data)
    emit("queued-appended", id=args.id)


def cmd_promote(args: argparse.Namespace) -> None:
    data = load_json(args.active)
    active = data.setdefault("active", [])
    queued = data.get("queued", [])
    if len(active) >= 1:
        fail(
            "single-active invariant: cannot promote into an occupied "
            f"active slot ({active[0].get('id')})"
        )
    match = next((e for e in queued if e.get("id") == args.id), None)
    if match is None:
        fail(f"id {args.id!r} is not present in queued[]; cannot promote")
    data["queued"] = [e for e in queued if e.get("id") != args.id]
    active.append(
        {
            "id": match.get("id"),
            "path": match.get("path"),
            "type": match.get("type"),
            "phase": match.get("phase", "spec"),
            "started": args.started,
        }
    )
    atomic_write_json(args.active, data)
    emit("promoted", id=args.id)


def cmd_archive(args: argparse.Namespace) -> None:
    data = load_json(args.active)
    active = data.setdefault("active", [])
    archived = data.setdefault("archived", [])
    match = next((e for e in active if e.get("id") == args.id), None)
    if match is None:
        fail(f"id {args.id!r} is not in active[]; refusing double-archive")
    data["active"] = [e for e in active if e.get("id") != args.id]
    archived.append(
        {
            "id": match.get("id"),
            "path": match.get("path"),
            "completed": args.completed,
        }
    )
    atomic_write_json(args.active, data)
    emit("archived", id=args.id)


def cmd_mirror_phase(args: argparse.Namespace) -> None:
    data = load_json(args.active)
    active = data.get("active", [])
    match = next((e for e in active if e.get("id") == args.id), None)
    if match is None:
        fail(f"id {args.id!r} is not in active[]; cannot mirror phase")
    match["phase"] = args.phase
    atomic_write_json(args.active, data)
    emit("phase-mirrored", id=args.id, phase=args.phase)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_aa = sub.add_parser("append-active")
    p_aa.add_argument("--active", required=True)
    p_aa.add_argument("--id", required=True)
    p_aa.add_argument("--path", required=True)
    p_aa.add_argument("--type", required=True)
    p_aa.add_argument("--phase", required=True)
    p_aa.add_argument("--started", required=True)
    p_aa.set_defaults(func=cmd_append_active)

    p_aq = sub.add_parser("append-queued")
    p_aq.add_argument("--active", required=True)
    p_aq.add_argument("--id", required=True)
    p_aq.add_argument("--path", required=True)
    p_aq.add_argument("--type", required=True)
    p_aq.add_argument("--queued-at", required=True, dest="queued_at")
    p_aq.set_defaults(func=cmd_append_queued)

    p_pr = sub.add_parser("promote")
    p_pr.add_argument("--active", required=True)
    p_pr.add_argument("--id", required=True)
    p_pr.add_argument("--started", required=True)
    p_pr.set_defaults(func=cmd_promote)

    p_ar = sub.add_parser("archive")
    p_ar.add_argument("--active", required=True)
    p_ar.add_argument("--id", required=True)
    p_ar.add_argument("--completed", required=True)
    p_ar.set_defaults(func=cmd_archive)

    p_mp = sub.add_parser("mirror-phase")
    p_mp.add_argument("--active", required=True)
    p_mp.add_argument("--id", required=True)
    p_mp.add_argument("--phase", required=True)
    p_mp.set_defaults(func=cmd_mirror_phase)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
