---
name: workflow-status
description: Print a one-screen status summary of all active features and recent archives. Read-only. Useful at session start or for the user to check progress.
allowed-tools: Read, Bash
argument-hint: "(no args)"
---

# Workflow: status

Read-only status report.

## Steps

1. Read `active.json`.
2. For each entry in `active[]`, read `specs/<id>/state.json`.
3. Print a table:
   ```
   ID                          TYPE       PHASE      STATUS         STARTED      LAST ACTIVITY
   NNN-example-feature         feature    tasks      in_progress    May 5        2 hours ago
   NNN-example-refactor        refactor   implement  paused         May 1        6 days ago
   ```
4. Print recent archives (last 5 entries from `archived[]`):
   ```
   Recently completed:
   - 011-agent-teams-experimental-audit (spike, 2026-05-09)
   - 010-agent-teams-claude-code-currency-audit (spike, 2026-05-07)
   - ...
   ```
5. If any active feature has `status: blocked` → highlight in red.

## No state mutation
