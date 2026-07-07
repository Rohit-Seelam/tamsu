"""Phase-ledger builder for the SDK memory pipeline.

Reads `state.json.phase_history` for the just-completed spec and renders the
`## Phase ledger` prompt section per `design/02-prompt-structure.md`. Each
entry resolves its owner via the actor map (`_actor_map.py`). Team-implement
entries render an inline member list.

Per AC-9 (`specs/020-sdk-session-targeting/spec.md`), missing
`verifier_pass` booleans default to the string `"n/a"` — older specs (pre
spec 012 contract) may lack the field on every entry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_PAD_PHASE = 11
_PAD_OWNER = 22
_MIN_OWNER_TRAIL = 2


def _format_owner(entry: dict[str, Any], actor_map: dict[str, Any]) -> str:
    """Resolve an entry's owner into a printable label.

    - Bare strings pass through unchanged (already workflow-vocabulary).
    - When `owner == "team"` and `team_members` is present, render as
      `team (m1, m2, ...)`.
    """
    owner = entry.get("owner")
    if owner == "team":
        members = entry.get("team_members") or []
        if not members:
            # Fallback: pull names from actor_map.teammates.
            members = sorted(
                v.get("name", "")
                for v in (actor_map.get("teammates") or {}).values()
                if v.get("name")
            )
        return f"team ({', '.join(members)})"
    if isinstance(owner, str) and owner:
        return owner
    return "unknown"


def _format_verifier_pass(entry: dict[str, Any]) -> str:
    vp = entry.get("verifier_pass")
    if vp is True:
        return "true"
    if vp is False:
        return "false"
    return "n/a"


def build_phase_ledger(
    state_json_path: str | Path,
    actor_map: dict[str, Any],
) -> list[dict[str, str]]:
    """Read `state.json.phase_history` and produce a list of rendered entries."""
    p = Path(state_json_path)
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    history = state.get("phase_history") or []
    out: list[dict[str, str]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "phase": str(entry.get("phase", "")),
                "owner": _format_owner(entry, actor_map),
                "verifier_pass": _format_verifier_pass(entry),
            }
        )
    return out


def render_phase_ledger_section(ledger: list[dict[str, str]]) -> str:
    """Render the `## Phase ledger` section per design/02-prompt-structure.md."""
    lines: list[str] = ["## Phase ledger", ""]
    if not ledger:
        lines.append("(no phase history)")
        return "\n".join(lines) + "\n"
    for entry in ledger:
        phase = entry["phase"].ljust(_PAD_PHASE)
        owner_raw = entry["owner"]
        owner_pad = max(_MIN_OWNER_TRAIL, _PAD_OWNER - len(owner_raw))
        owner = owner_raw + " " * owner_pad
        vp = entry["verifier_pass"]
        lines.append(f"{phase}— owner: {owner}— verifier_pass: {vp}")
    return "\n".join(lines) + "\n"
