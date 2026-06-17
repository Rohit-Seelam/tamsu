---
name: workflow-advance
description: Advance the active feature to the next phase. Reads state.json, runs verifier if missing, presents HITL gate if applicable, updates phase + phase_history via the deterministic state scripts. Invoked by orchestrator and available to user as /workflow-advance.
allowed-tools: Read, Write, Bash(python3:*), Agent, AskUserQuestion
argument-hint: "[<feature-id>] (defaults to first active feature)"
---

# Workflow: advance

Advance the active feature one phase. Same logic whether triggered by orchestrator or user via `/workflow-advance`. The deterministic state mutations are performed by the `_scripts/` mutators rather than by hand-editing the state file.

## Steps

1. Resolve target: `$ARGUMENTS` if provided, else `active.json.active[0]`.
2. Read `specs/<id>/state.json` (for `type`, `complexity`, `phase`, gate decisions — read-only).
3. Verify primary artifact for `state.phase` exists per `workflow/artifacts.md`:
   - `spec` phase → `spec.md`
   - `plan` phase → `plan.md`
   - `tasks` phase → `tasks.md`
   - `implement` phase → code + `tasks.md` task checkboxes complete
   - `verify` phase → all `verification/*.md` reports
4. If verification report for current phase missing → spawn matching verifier from `agents/review/`. Wait.
5. Read ONLY the YAML frontmatter of `verification/<phase>-report.md` — the `status` field and the severity counts (`critical`/`major`/`minor`). Do NOT read the report body on the pass path; the frontmatter carries every verdict the gate decision needs. (Reports follow the frontmatter schema in `workflow/evaluation.md`; the body is for the fixer, not the orchestrator.)
6. If `status: fail`:
   - If `fix_round < state.max_fix_rounds` → spawn fixer (the phase actor), passing the report file PATH (`specs/<id>/verification/<phase>-report.md`) so the fixer reads the findings itself — do NOT inline the report body into the fixer prompt. Then record the fix-round bump with a history note. Loop to step 4.
     ```bash
     python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/state_json_mutator.py append-history-note \
       --state .claude/specs/<id>/state.json --note "fix round <n>: <verifier finding>"
     ```
   - If `fix_round == max_fix_rounds` → `AskUserQuestion` Pattern C from `communication.md`.
7. If `status: pass`:
   - Compute the next phase AND the gate decision in one call. `_scripts/workflow_phase_next.py` is the authoritative phase/lane AND gate-existence table — it emits one line `next gate=<true|false> phase=<p>`:
     ```bash
     OUT=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/workflow_phase_next.py \
       --type "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["type"])' .claude/specs/<id>/state.json)" \
       --complexity "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["complexity"])' .claude/specs/<id>/state.json)" \
       --phase "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["phase"])' .claude/specs/<id>/state.json)")
     NEXT=$(printf '%s\n' "$OUT" | sed -n 's/.*phase=\([a-z]*\).*/\1/p')
     GATE=$(printf '%s\n' "$OUT" | sed -n 's/.*gate=\([a-z]*\).*/\1/p')
     ```
     A non-zero exit means the current phase is `deliver` (terminal) — there is nothing to advance.
   - The `GATE` value from the script is the authoritative gate-existence decision (`workflow_phase_next.py` derives it from `workflow/phases.md` "Surviving gates per complexity lane", so do NOT re-read `phases.md` here).
   - If `GATE == true` AND `state.autonomous == false` → `AskUserQuestion` Pattern A. Wait for response.
     - `Stop` → set status to paused, then exit:
       ```bash
       python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/state_json_mutator.py set-status \
         --state .claude/specs/<id>/state.json --status paused
       ```
     - `Revise` → spawn fixer with user feedback as input; loop to step 4.
     - `Advance` → continue to step 8.
   - If `state.autonomous == true` OR `GATE == false` → continue.
8. Advance the phase. This closes the open `phase_history` entry (with `verifier_pass`/`fix_rounds`), sets `phase` to the next phase from the lane table, and appends the new open entry — one atomic write:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/state_json_mutator.py advance \
     --state .claude/specs/<id>/state.json \
     --type <type> --complexity <complexity> \
     --verifier-pass <true|false> --fix-rounds <n>
   ```
   Then mirror the new phase into `active.json` (same batch):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/active_json_mutator.py mirror-phase \
     --active .claude/active.json --id <id> --phase "$NEXT"
   ```
9. If new phase is `deliver` → spawn `git-engineer` (terminal phase).
10. Else → spawn the next phase's primary actor with the delegation template from `workflow/communication.md`.
