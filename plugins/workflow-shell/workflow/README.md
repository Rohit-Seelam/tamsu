# Workflow

This folder defines how work gets done in this repo. The orchestrator agent and every subagent reads it. `CLAUDE.md` imports `README.md` and `constitution.md` so they auto-load every session; the rest loads on demand.

## Files

| File | What it is | When read |
|---|---|---|
| `README.md` | This index | Every session (via `CLAUDE.md` `@import`) |
| `constitution.md` | Non-negotiable principles for this project | Every session |
| `phases.md` | The 6-phase state machine each work item moves through | When orchestrator advances a phase or verifier reviews one |
| `routing.md` | How an incoming prompt is classified into a workflow type | Session start; on every new top-level request |
| `artifacts.md` | Folder, file, `state.json`, and `active.json` conventions | When agents read or write artifacts |
| `communication.md` | Triangle: orchestrator ↔ user ↔ subagents. `AskUserQuestion` patterns. HITL-gate behavior. | When orchestrator pauses for input |
| `evaluation.md` | Verification framework — who verifies what, when, with which agent | When orchestrator triggers a verifier |
| `migration.md` | Onboarding guide for adopting `.claude/` shell in an existing project | When bootstrapping into a new repo |
| `templates/` | `spec.md` / `plan.md` / `tasks.md` templates per workflow type (incl. `spec-docs.md`) | When an agent authors an artifact |
| `queue.md` | Pending workflow items — slug-based, readiness-bucketed; staging before `active.json` | When user reviews next-steps; when promoting a queued item to a spec |

`communication.md`, `evaluation.md`, `constitution.md`, and `templates/` are second-pass; the four core docs (`README`, `phases`, `routing`, `artifacts`) are authored first.

## Memory vs queue boundary

- `.claude/memory/topics/*.md` — landed decisions and characterization findings. Written by the SDK memory pipeline at every `deliver`. Never holds pending lists, numbered TODOs, or "items to do later."
- `.claude/workflow/queue.md` — **pre-spec slug brainstorming**, hand-edited. Slug-based, readiness-bucketed. An item lives here until it is authored as a real spec (single-spec routing OR batch intake); at that point its slug exits the bucket and a spec folder appears under `specs/<NNN-slug>/`.
- `.claude/active.json` `queued[]` field (introduced by spec 024) — **post-spec, pre-promotion** workflow items. Each entry already has a `specs/<NNN-slug>/` folder authored from batch intake; the spec waits at `status: "queued"`, `phase: "spec"` until the user issues a promotion prompt and it moves into `active[]`. See `workflow/artifacts.md` `active.json schema` for the entry shape and `specs/024-batch-spec-planning/design/02-active-json-schema.md` for the full backward-compat rule.

This split keeps memory's job clean (what was decided and why) and gives planning two distinct surfaces: `queue.md` is the brainstorming pad (no spec authored yet), and `active.json.queued[]` is the post-authoring holding pen (spec written, awaiting user promotion). Spec 024 (`batch-spec-planning`) landed `queued[]` as the contract surface; `queue.md` remains the brainstorming surface and is NOT replaced.

## Core vocabulary

- **Workflow type** — one of `feature`, `bugfix`, `refactor`, `spike`, `docs`, `prd`. `freeform` (Q&A with no artifact) is the default fallback and does not engage the workflow.
- **Phase** — outer state-machine stage: `spec → plan → tasks → implement → verify → deliver`. Tracked in `state.json.phase`. Defined in `phases.md`.
- **Milestone** — subdivision *inside* `plan.md` (e.g. "Milestone 1: schema migration"). **Never call these "phases."** Verifier flags vocabulary violations.
- **HITL gate** — a phase boundary where the orchestrator must ask the user before advancing. Three exist: `spec→plan` (or `spec→tasks`/`spec→implement` for types that skip plan), `tasks→implement`, `verify→deliver`.
- **Verifier** — read-only subagent that reviews an artifact after a phase produces it. One per phase. Models default to `haiku` for spec/plan/task verifiers and `sonnet` for cross-checker (per `evaluation.md` "Verifier model defaults").
- **Fixer** — read-write subagent that addresses verifier findings. Verifier and fixer are always different agents (no self-approval).
- **Team** — Agent Teams subagents that run concurrently during `implement` for `feature` / `bugfix` / `refactor` / `spike` (MUST). Sequential single-author for `docs` and `prd`. Protocol in `specs/012-workflow-contract-v2/design/07-team-lifecycle.md`.
- **Orchestrator** — the main session agent (`.claude/agents/orchestrator.md`); coordinates state and delegation, never writes domain code itself.
- **SDK memory pipeline** — the SOLE memory writer; a `claude-agent-sdk` subprocess that runs at every `deliver`. Not a subagent in the triangle. Contract in `workflow/sdk-pipeline.md`; mirror classification in `workflow/artifacts.md#selective-mirror-policy`.
- **Autonomous mode** — `state.json.autonomous: true` skips HITL gates. Always-pause events (constitutional violation, max_fix_rounds, BLOCKED, NEEDS_USER, team-crash, teammate `task create`) are not skippable — see `phases.md` Rule B. Off by default.

## How a typical run starts

1. User pastes a cleaned prompt (run through external `improve_prompt` first).
2. Orchestrator reads `routing.md` → classifies workflow type. If `freeform`, answers directly and stops.
3. Otherwise creates `.claude/specs/<NNN-slug>/` with `state.json` (and optionally `.claude/PRD/<NNN-slug>/` for epic-level work).
4. Phase agents run sequentially per `phases.md`; the matching verifier runs after each; HITL gates pause at the three boundaries.
5. State is durable on disk. Resume = re-read `active.json` + the active feature's `state.json`.

## Where to look first

- **New here?** Read `constitution.md`, then this file, then `phases.md`.
- **Bootstrapping into an existing project?** Read `migration.md` first.
- **Got a prompt?** Go to `routing.md`.
- **Writing an artifact?** `templates/` + `artifacts.md`.
- **Verifying?** `evaluation.md`.
- **Need user input?** `communication.md`.
- **What's next?** Read `queue.md`.

## Skills

Skills are discoverable in `.claude/skills/<category>/<name>/SKILL.md`. Categories used in this repo:

- `skills/workflow/` — `advance`, `new`, `rollback`, `status`, `rules-review` (periodic rules drift check at every Nth deliver; default `N=5`).
- `skills/memory/` — `compile`, `extract`, `jsonl-format` (self-updating schema map for session JSONLs; read by the SDK memory pipeline).
- `skills/research/` — `claude-code-docs-fetch` (owned by `agents/research/claude-code-docs.md`; self-updating docs map).
- `skills/media/` — domain-specific.

## What is NOT in this folder

- Per-feature work → `.claude/specs/<NNN>/`
- PRDs → `.claude/PRD/<NNN>/`
- Captured sessions → `.claude/sessions/`
- Memory → `.claude/memory/` (shared repo mirror) and `.claude/agent-memory/<agent>/` (per-agent silos); both written solely by the SDK memory pipeline at `deliver` (`constitution.md` Rule 5). Mirror classification and silo carve-out: `workflow/artifacts.md#selective-mirror-policy`.
- Code rules → `.claude/rules/`
- Hooks → wired in `settings.json`; scripts under `.claude/hooks/`
- Agents → `.claude/agents/<category>/<name>.md`
- Skills → `.claude/skills/<category>/<name>/SKILL.md`
