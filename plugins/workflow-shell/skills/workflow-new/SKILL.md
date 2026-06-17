---
name: workflow-new
description: Create a new feature folder. Resolves next ID, creates folder structure, seeds state.json, copies the matching spec template, updates active.json — all via the deterministic scaffold script. Spawns product-manager to author spec.md.
allowed-tools: Read, Write, Bash(python3:*), Agent
argument-hint: "<type> <slug> [--prd <prd-id>]"
---

# Workflow: new

Bootstrap a new feature. The scaffold (next-ID resolution, folder creation, `state.json` seeding, spec-template copy, and `active.json` append) is performed by `_scripts/workflow_state_init.py` in one deterministic call rather than by hand-editing files.

## Steps

1. Parse `$ARGUMENTS`: type (feature | bugfix | refactor | spike | docs), slug, optional parent PRD.
2. Scaffold the spec folder in one deterministic call. The script resolves the next monotonic 3-digit ID across BOTH `.claude/specs/` and `.claude/PRD/`, seeds `state.json` from `workflow/templates/state.json`, copies `spec-<type>.md` to `spec.md` (skipped for `docs`), and appends the `active[]` entry:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/_scripts/workflow_state_init.py \
     --repo-root "$(pwd)" --type <type> --slug <slug> \
     --started "$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')" \
     [--parent-prd PRD/<prd-id>]
   ```
   The script prints one `key=value` line naming the created spec id (e.g. `scaffolded spec=NNN-slug phase=spec`). ID collisions cannot occur through normal scanning — the monotonic scan always bumps past the highest existing ID; a defensive guard additionally refuses (non-zero exit) rather than overwrite if the target folder somehow already exists.
3. Spawn `product-manager` (or skip to `engineering/frontend-engineer` if `docs`) with the delegation template, passing the user's initial intent as the input.
