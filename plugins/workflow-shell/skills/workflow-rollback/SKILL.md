---
name: workflow-rollback
description: Roll back the active feature to an earlier phase. Updates state.json.phase and appends a phase_history rollback note via the deterministic state script. Old artifacts in later phases stay on disk (audit trail).
allowed-tools: Read, Bash(python3:*), Agent
argument-hint: "<feature-id> <target-phase>"
---

# Workflow: rollback

User-initiated only. Orchestrator never rolls back without explicit user request. The phase change and `phase_history` note are written by `_scripts/state_json_mutator.py rollback`, which enforces the linear-order and type-skip refusals itself rather than relying on a hand-edit of the state file.

## Steps

1. Parse `$ARGUMENTS`: feature ID and target phase.
2. Read `specs/<id>/state.json` for `type` and `complexity` (read-only).
3. Roll back. The script validates that the target is EARLIER than the current phase and is not a phase the workflow type skips, sets `phase` to the target, and appends a `{phase, ..., note}` rollback entry — one atomic write. An illegal target (equal/later, or type-skipped) is a loud non-zero refusal that writes nothing:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/state_json_mutator.py rollback \
     --state .claude/specs/<id>/state.json \
     --type <type> --complexity <complexity> \
     --target <target-phase> --note "<user note>"
   ```
   Then mirror the rolled-back phase into `active.json` (same batch):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/active_json_mutator.py mirror-phase \
     --active .claude/active.json --id <id> --phase <target-phase>
   ```
4. Old artifacts (later than target phase) stay on disk. They will be overwritten as phases re-run.
5. Re-trigger the target phase's actor with the delegation template.

## Constraints

- Cannot roll back from `deliver` (state is `completed`).
- Cannot roll back to a phase the workflow type skips (e.g., `bugfix` cannot roll back to `plan`). The script refuses both cases automatically.
