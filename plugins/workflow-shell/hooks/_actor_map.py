"""Actor-map builder for the SDK memory pipeline.

Maps:
- every `agent-<id>` under `<orchestrator-session>/subagents/` to its
  `{agentType, description}` (from the paired `agent-<id>.meta.json`),
- every non-`team-lead` teammate session-id to its `{name, agentType}`
  (from the team audit copy).

Per AC-8 (`specs/020-sdk-session-targeting/spec.md`), the rendered section
must follow the shape in `design/02-prompt-structure.md § Actor map`.

Missing `verifier_pass` booleans in upstream consumers default to the string
`"n/a"` — see `_phase_ledger.py` for that detail; this module only deals
with actor identity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_subagent_metas(canonical_dir: Path, session_id: str) -> dict[str, dict[str, str]]:
    """Return `{agent-<id>: {agentType, description}}` for one session."""
    sdir = canonical_dir / session_id / "subagents"
    if not sdir.is_dir():
        return {}
    out: dict[str, dict[str, str]] = {}
    for meta in sorted(sdir.glob("agent-*.meta.json")):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        agent_id = meta.stem  # "agent-<id>.meta" → "agent-<id>"
        if agent_id.endswith(".meta"):
            agent_id = agent_id[:-5]
        out[agent_id] = {
            "agentType": str(data.get("agentType", "")),
            "description": str(data.get("description", "")),
        }
    return out


def _read_team_config(team_config_path: Path | None) -> dict | None:
    if team_config_path is None:
        return None
    p = Path(team_config_path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_actor_map(
    canonical_dir: str | Path,
    orchestrator_session_id: str,
    team_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return `{subagents: {...}, teammates: {sessionId: {name, agentType}}, team_name}`.

    `subagents` is keyed by `agent-<id>`. `teammates` is keyed by session ID
    (the value the orchestrator's main JSONL uses to identify the teammate
    process), so the SDK agent can resolve a session-id seen in a JSONL line
    back to a workflow-vocabulary name.
    """
    base = Path(canonical_dir)
    subagents = _read_subagent_metas(base, orchestrator_session_id)
    teammates: dict[str, dict[str, str]] = {}
    team_name = ""
    config = _read_team_config(Path(team_config_path) if team_config_path else None)
    if config:
        team_name = str(config.get("name", ""))
        for member in config.get("members", []):
            if member.get("name") == "team-lead":
                continue
            sid = member.get("sessionId")
            if not sid:
                continue
            teammates[str(sid)] = {
                "name": str(member.get("name", "")),
                "agentType": str(member.get("agentType", "")),
            }
    return {
        "subagents": subagents,
        "teammates": teammates,
        "team_name": team_name,
    }


def render_actor_map_section(actor_map: dict[str, Any]) -> str:
    """Render the `## Actor map` section per design/02-prompt-structure.md."""
    lines: list[str] = ["## Actor map", ""]
    lines.append("Subagents (orchestrator-spawned):")
    subs = actor_map.get("subagents", {})
    if subs:
        for agent_id in sorted(subs.keys()):
            entry = subs[agent_id]
            atype = entry.get("agentType", "")
            desc = entry.get("description", "")
            lines.append(f'  {agent_id} → {atype}  ("{desc}")')
    else:
        lines.append("  (none)")
    lines.append("")
    team_name = actor_map.get("team_name", "")
    header = f"Teammates (team {team_name}):" if team_name else "Teammates:"
    lines.append(header)
    teammates = actor_map.get("teammates", {})
    if teammates:
        for sid in sorted(teammates.keys()):
            name = teammates[sid].get("name", "")
            lines.append(f"  {sid} → {name}")
    else:
        lines.append("  (none)")
    return "\n".join(lines) + "\n"
