---
name: <agent-name>
description: <one-line trigger description — what makes the orchestrator pick this agent>
model: sonnet
permissionMode: default
tools:
  - Read
  - Edit
  - Write
  - Bash
  - SendMessage
  - TaskGet
  - TaskList
  - TaskOutput
  - TaskStop
  - TaskUpdate
disallowedTools: []
maxTurns: 20
color: gray
---

> **Plugin path resolution (workflow-shell).** This agent ships in the `workflow-shell` plugin; the project does not contain these files. Resolve shorthand references below as:
> - Contract docs `workflow/<doc>.md` (README, phases, routing, artifacts, communication, evaluation, migration), `constitution.md`, `rules/<x>.md`, the `workflow/templates/`, and sibling agents `agents/<cat>/<name>.md` → **`${CLAUDE_PLUGIN_ROOT}/...`** (bundled here; read them from there).
> - Project state — `active.json`, `specs/<NNN>/…`, `state.json`, `.claude/workflow/queue.md`, `memory/`, `agent-memory/` → under the **project's `.claude/`** (cwd), seeded by `/workflow-init`. `queue.md` is project-side, NOT the plugin's `workflow/`.
> - References to `.claude/hooks/*` scripts and `specs/NNN/design/*` belong to the optional `workflow-memory-pipeline` plugin and are **dormant** in a crux-only install.


# <Agent name>

## Role

<One paragraph: what this agent does and what it does NOT do.>

## Inputs

<Bullet list: which files this agent reads to do its job.>

## Outputs

<Bullet list: which files this agent writes.>

## Return contract

Per `workflow/communication.md`:

```
Status: DONE | BLOCKED | NEEDS_USER

Wrote: <artifact path(s)>
Skipped: <what wasn't done and why>
Blocker: <if BLOCKED>
User question: <if NEEDS_USER, with 2 recommended options>
```

## Agent-specific rules

<Anything domain-specific the orchestrator needs to know about this agent's behavior.>

## Memory

Cross-agent facts go to `memory/topics/<topic>.md`. This agent does not write memory directly — the SDK pipeline at `deliver` is the sole memory writer (`constitution.md` Rule 5).
