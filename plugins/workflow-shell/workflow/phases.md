# Phases

The outer state machine every work item moves through. The orchestrator owns advancement; subagents act within a single phase.

## Vocabulary

- **Phase** — one of the six stages below. Tracked in `state.json.phase`.
- **Milestone** — a subdivision *inside* `plan.md` (e.g. "Milestone 1: schema migration"). **Do not write "Phase 1: …" inside `plan.md`** — the plan-verifier flags this as a vocabulary violation.

## The six phases

```
spec  →  plan  →  tasks  →  implement  →  verify  →  deliver
```

Phases are linear. Skip-forward is not allowed. Roll-back is allowed — see "Rollback" below. Workflow types skip phases at the *start* (e.g. `bugfix` skips `plan`); `routing.md` defines per-type subsets.

**Lane-legal phase-jump carve-out (cross-checker contract).** A complexity-lane-driven jump is NOT a skip-forward violation. When `state.json.complexity` selects a lane (`workflow/routing.md` section `#complexity-lane`) that drops `plan`/`tasks` — e.g. a `small`-lane spec advancing `spec → implement` with no intervening `plan`/`tasks` — `cross-checker` MUST NOT flag that jump as a "skip-forward is not allowed" violation. The carve-out is scoped ONLY to jumps authorized by the lane table; it is NOT a blanket skip-forward permission. Any jump that the lane does not authorize remains a violation. The `active.json.<entry>.phase` mirror (`artifacts.md:169-173`) still tracks the lane jump: both `state.json.phase` and the mirror reflect `spec → implement`. The single-active (`artifacts.md:167`) and queue-vs-queued (`artifacts.md:167`) invariants are UNCHANGED by lanes.

For `docs`, the `spec` phase is OPTIONAL — required for major redesigns (uses `templates/spec-docs.md`), skipped for trivial doc edits. For `prd`, the subset is `spec → implement → verify → deliver` (no plan, no tasks; single-author; produces `PRD/<NNN-slug>/prd-vN.md` per `specs/012-workflow-contract-v2/design/01-prd-workflow-type.md`).

On top of the per-type subset, `state.json.complexity` selects a LANE that further right-sizes the phase set. The lane mapping (`trivial`/`small`/`medium`/`epic` → effective phase set) is defined ONCE canonically in the lane table in `workflow/routing.md` (section `#complexity-lane`; Rule 7); this file cites it by path and does not restate it.

## Per-phase contract

| Phase | Input | Output | Primary actor | Verifier | HITL gate after |
|---|---|---|---|---|---|
| `spec` | user prompt (+ PRD if any) | `spec.md` (per type's template) | `product-manager` | `spec-verifier` | **YES** — lock requirements |
| `plan` | `spec.md` | `plan.md` | `architect` (for `feature` and `refactor`; see `agents/planning/architect.md`) | `plan-verifier` | no |
| `tasks` | `plan.md` | `tasks.md` | engineer or task-decomposer | `task-verifier` | **YES** — last chance before code |
| `implement` | `tasks.md` | code + tests | engineers — **MUST run as an Agent Team** for `feature` / `bugfix` / `refactor` / `spike` (see "Teams in implement" below) | continuous PostToolUse hooks + `qa-engineer` agent † | no |
| `verify` | code + tests | `verification/*.md` reports | `qa-engineer` + cross-check verifier | (terminal verifier) | **YES** — final review |
| `deliver` | verified artifacts | spec branch pushed + PR to `main` (direct commit only as the no-remote fallback — see "Deliver: branch and PR" / `phases.md#deliver-branch-and-pr`), updated docs, memory pipeline run (see "Deliver: SDK memory pipeline" below) | `orchestrator` | — | (terminal) |

† **No-code workflows** (`spike`, `docs`, `prd`) have no continuous verifier in `implement` — there are no `Write|Edit` events on production code, so PostToolUse hooks don't fire and `qa-engineer` has nothing to verify. For these workflows, `cross-checker` at the `verify` phase is the sole gate. State.json's `phase_history[].verifier_pass: null` for `implement` in a spike, docs, or prd workflow is **intentional**, not an unfilled field.

The HITL gate fires *between* phases — after the named phase's verifier passes, before the next phase begins.

**Verifier chain per complexity lane.** A verifier runs only for a phase that runs; the lane (`workflow/routing.md` section `#complexity-lane`) drops phases and therefore drops their verifiers. For the **`small`** lane (`spec → implement → verify → deliver`), the verifier set is exactly `spec-verifier` (after `spec`) → `qa-engineer` + cross-checker (at `verify`). `plan-verifier` and `task-verifier` do NOT fire, because `plan` and `tasks` are skipped — the SAME mechanism by which `bugfix` already skips `plan-verifier` today. No running phase is left without its verifier, and no verifier is invented for a skipped phase. `medium` runs the type's full verifier chain unchanged; `trivial` runs no phases and therefore no verifiers.

## Teams in implement

For `feature` / `bugfix` / `refactor` / `spike`, the `implement` phase **MUST** run as an Agent Team. `docs` and `prd` stay sequential single-author.

The full lifecycle protocol (5 implement-start steps + 5 implement-end steps + crash recovery + capture cases) lives in `specs/012-workflow-contract-v2/design/07-team-lifecycle.md` — the SINGLE source of truth (Constitution Rule 7). Do NOT duplicate the protocol here.

Supersession of spike 011's `defer` recommendation is recorded in `memory/topics/decisions.md` (2026-05-09); under the constrained scope (Teams in implement only, team-per-spec lifetime), 3 of 5 spike-011 rejection reasons evaporate. The two that remain (no session resumption with in-process teammates, 3–5× token cost) are mitigated by accepting mid-implement crash → restart-from-tasks.md, and scoping team usage to the bottleneck phase only.

## Deliver: branch and PR

Every spec is developed on its own branch and delivered as a pull request to `main` that the workflow does **not** merge. This section is the single source of truth for the branch-and-PR delivery procedure (Constitution Rule 7); other docs (`agents/orchestrator.md`, `agents/ops/git-engineer.md`, the "Termination" step, the per-phase table row) cite it by `path#heading` and do not restate it.

1. **Branch at init.** When a new workflow item is initialized, a spec branch named `<NNN>-<slug>` (e.g. `051-branch-and-pr-deliver`) is created. The `<NNN>-<slug>` branch-naming format is DEFINED here and nowhere else.
2. **All phase commits land on that branch.** Every commit produced across `spec → … → deliver` lands on the spec branch, not on `main`. This includes the SDK memory pipeline's commit (see "Deliver: SDK memory pipeline" — `phases.md#deliver-sdk-memory-pipeline`): the pipeline still runs at deliver, but ON the spec branch, and its memory commit is part of the same PR — NOT an independent `main` commit.
3. **Deliver pushes and opens a PR.** At `deliver`, the branch is pushed to `origin` and a PR targeting `main` is opened via `gh pr create`, titled `[<NNN-slug>] <one-line description>`.
4. **The workflow does NOT merge.** The PR is left open for the user's external review / coroutine. Merging is a deliberate human step; the workflow never auto-merges.
5. **No-remote fallback (graceful degradation).** If no git `origin` remote is configured, deliver commits directly instead of pushing and opening a PR. This is the ONLY case in which a direct commit is acceptable — a fallback, not a co-equal default path.

## Deliver: SDK memory pipeline

At the end of every `deliver` phase (every workflow type), a `claude-agent-sdk` subprocess updates project memory. Inputs include the just-completed spec's artifacts, canonical session JSONLs at `~/.claude/projects/<project-slug>/`, subagent transcripts, and current memory state. The pipeline is a **propose→write** split: the LLM half does ONE bounded read-once pass and EMITS a structured proposal (writing no files), then a deterministic Python writer turns the proposal into files — owning every path, the write-budget TRUNCATING cap (writes top-N per store, drops + logs the excess), the `MEMORY.md` shape, the canonical-vs-repo split, and the personal-line filter. The writer writes the CANONICAL store `~/.claude/projects/<project-slug>/memory/` and mirrors the non-personal subset into the `<repo>/.claude/memory/` git audit copy; the per-agent `agent-memory/<agent>/` silos are canonical-only and are NOT mirrored. Full contract: `workflow/sdk-pipeline.md`; mirror classification: `workflow/artifacts.md` "Selective mirror policy".

Memory updates are best-effort and do NOT block deliver completion. On subprocess crash, orchestrator logs the failure and surfaces a one-line warning. Full contract (stores, paths, write budget, depth rule, model, timeout model, all exit codes, tool allowlist, failure modes) lives in `workflow/sdk-pipeline.md`. Do NOT duplicate here.

The `deliver` phase MAY also invoke the `workflow:rules-review` skill on the Nth completed spec (default `N=5`, configurable via `CLAUDE.md`'s `rules_review_every_n_specs:`). The skill produces a candidate-amendments file at `.claude/rules/_candidates-<YYYY-MM-DD>.md` for the user to review. See `skills/workflow/rules-review/SKILL.md`.

## Deliver: retrospective

At every Nth completed spec (default `N=3`, configurable via `CLAUDE.md`'s `retrospectives_every_n_specs:`), the orchestrator authors a retrospective using `workflow/templates/retrospective.md`. The retro file path is `.claude/retrospectives/<NNN>-<spec-slug>.md` — retro id equals spec id (convention adopted 2026-05-18; legacy 001-004 retained as-is).

A retrospective is ALSO mandatory — regardless of the Nth-counter position — when EITHER of these threshold-trigger conditions holds for the just-completed spec:

- any phase in `state.json.phase_history` has `verifier_pass: false`, OR
- any phase reached `max_fix_rounds`.

The Nth counter starts from retro 021 (the first retrospective under the "retro id == spec id" convention). With `N=3`, the next mandatory retro under the cadence rule is spec 024. Specs 012-020 are intentionally not backfilled; their durable decisions live in `memory/topics/spec-NNN-*.md` (forward-only).

As part of the deliver action that writes the retro, the orchestrator also appends a row to `.claude/retrospectives/INDEX.md`. Retros land in `.claude/retrospectives/`; do not write retro content into memory or into the spec folder.

## Compact = context-clearing only

`/compact` is a pure context-clearing operation:

- It does NOT trigger memory updates.
- It does NOT trigger workflow phase changes.
- It does NOT trigger the SDK memory pipeline.

The canonical record of a compaction is an INLINE `compact_boundary` line in the same `~/.claude/projects/<project-slug>/<session-uuid>.jsonl` — NOT a separate file. The `PreCompact` hook continues to save a supplementary archive at `<repo>/.claude/sessions/mainagent/raw/<session-id>-segment-N.jsonl` for redundancy / debugging. The SDK reads the canonical in-file marker, not the segment.

The orchestrator does NOT auto-trigger `/compact`. Trigger is manual — invoked by the user, typically after 2–3 full feature flows' worth of context. Full rationale in `specs/012-workflow-contract-v2/design/06-compact-strategy.md`.

## Verifier ↔ fixer loop

After a phase produces its artifact:

1. Orchestrator triggers `<phase>-verifier` (read-only subagent).
2. Verifier writes `verification/<phase>-report.md`: `{status: pass|fail, findings: [...]}`.
3. **Pass** → if a HITL gate follows, orchestrator pauses for user; else updates `state.json.phase` and starts next phase.
4. **Fail** → orchestrator spawns `<phase>-fixer` (read-write, distinct from verifier — no self-approval) with the report. Fixer revises the artifact. Loop back to step 1.
5. **Max rounds** = `state.json.max_fix_rounds` (default `3`). After max, orchestrator escalates to user with the latest report and findings.

Verifier and fixer agent files live under `.claude/agents/review/` (defined in `evaluation.md`).

## HITL gates

Three per-spec boundaries pause for the user. The **batch-intake gate** (introduced by spec 024 — see `agents/orchestrator.md` "Batch intake") is ADDITIVE to these three and fires once at the end of a batch authoring run, before any spec enters `active.json.queued[]`; it does not replace the per-spec gates, which still fire after promotion.

At each per-spec gate:

1. The just-completed phase's verifier has passed.
2. Orchestrator calls `AskUserQuestion` with structured options:
   ```
   "<phase> is complete and verified. Advance to <next-phase>?"
   options: [Advance, Revise, Stop]
   ```
3. **Advance** → `state.json.phase` updates; next phase begins.
4. **Revise** → orchestrator asks an open follow-up; spawns a fixer with the user's feedback as input.
5. **Stop** → `state.json.status: paused`; session ends; `active.json` retains the feature as paused.

### Surviving gates per complexity lane

The complexity lane (`workflow/routing.md` section `#complexity-lane`) drops phases, and a gate cannot fire for a phase that does not run. The surviving gate set per lane is:

- **`small`** — TWO gates: `spec→implement` (the surviving "lock requirements before code" gate, analogous to the `prd`/`spike` `spec→implement` gate noted under "The six phases") and `verify→deliver`. The `tasks→implement` gate CANNOT fire because the `small` lane has no `tasks` phase. The gate-light alternative (only `verify→deliver`) was considered and REJECTED — `spec→implement` survives for `small`.
- **`medium`** — all THREE gates, unchanged (`spec→plan`/`spec→tasks`/`spec→implement` family, `tasks→implement`, `verify→deliver`), exactly as the type would fire them today.
- **`trivial`** — ZERO gates: a direct edit with no spec, no folder, and no phases, so no gate boundary exists.

## Autonomous mode

`state.json.autonomous: true` skips all HITL gates. Verifier failure still escalates after max rounds. Use for trusted, low-risk work (small refactors, docs). Default is `false`.

### Autonomous mode interaction rules

**Rule A — `autonomous: true` skips HITL gates only.** No other workflow event is affected. Verifiers still run; verifier-fixer loop is unchanged; max_fix_rounds still escalates.

**Rule B — Always-pause events (cannot be skipped by autonomous).** The orchestrator MUST pause for the user regardless of `autonomous` setting on:

- Constitutional violation flagged (per `constitution.md`).
- Verifier-fixer loop reached `max_fix_rounds` (Pattern C escalation).
- Subagent returned `BLOCKED` that the orchestrator cannot resolve (Pattern E).
- Subagent returned `NEEDS_USER` (Pattern D).
- Team-related: teammate crashed mid-task with no available replacement; lead crashed mid-`cp -r` audit copy.
- Team-related: a `task create` event from a teammate (workflow violation per `specs/012-workflow-contract-v2/design/02-agent-teams-implement.md`).

**Rule C — Teams + autonomous interaction.** Autonomous mode is COMPATIBLE with Teams in implement. The lead's team-management actions (`team create`, pre-populate tasks, monitor, `cp -r` audit copy, `team delete`) are mechanical and don't require HITL approval. If autonomous AND a team crashes or hangs, surface via Rule B's always-pause events.

**Rule D — PRD + autonomous interaction.** Same handling as `feature` / `bugfix` / `refactor`. PRD has three HITL gates (`spec → implement`, `implement → verify`, `verify → deliver`); autonomous skips all three. Implement phase still authors `prd-vN.md`; verify still runs `cross-checker`; Rule B still applies.

## Rollback

User-initiated only. To revert:

1. User says "go back to <earlier phase>" (or types a `/workflow-rollback` skill if available).
2. Orchestrator updates `state.json.phase` to the named phase.
3. Appends a `phase_history` entry in the standard shape (see `workflow/artifacts.md` "state.json schema"), with `completed: null` and a `note` recording the rollback reason — performed by `state_json_mutator.py rollback` (see `skills/workflow/rollback/SKILL.md`).
4. Stale artifacts in later phases stay on disk (audit trail); they are overwritten as phases re-run.

## Resumption

After a `/clear` or session restart:

1. Read `.claude/active.json` → list of active feature dirs from `active[]` AND queued spec dirs from `queued[]` (the third top-level array introduced by spec 024). Both surface in the resumption summary; queued specs are listed alongside the active spec so the user sees the full batch state. Per `workflow/artifacts.md` `active.json` schema, missing `queued` key reads as `[]`.
2. For each active feature, read `state.json` to find `phase` and `phase_history`.
3. If the active phase's primary artifact exists but no verification report → re-run verifier.
4. If verification failed → re-run fixer.
5. If clean → check the HITL gate and either pause or proceed.

Queued specs do NOT trigger verifier/fixer runs at resumption — they sit at `status: "queued"`, `phase: "spec"` until the user issues a promotion prompt (see `agents/orchestrator.md` "Promotion handler").

This means phases survive context loss. `phase_history` is the source of truth for "what already happened."

## Phase advancement — implementation surface

Implemented as a skill `.claude/skills/workflow/advance/SKILL.md` (drafted in second pass). Body:

1. Read `state.json` for the active feature.
2. Verify primary artifact for the current phase exists.
3. If no verification report yet → run verifier.
4. Read latest verification report.
5. If pass + HITL gate + not autonomous → `AskUserQuestion`; await reply.
6. Update `state.json.phase`, append to `phase_history`, save.
7. Trigger the next phase's primary actor with a templated handoff prompt.

User can call `/workflow-advance` directly for a manual override. Orchestrator calls the same skill autonomously when conditions are clear.

## Termination

When `verify` HITL gate returns "Advance":

1. `deliver` phase runs: orchestrator pushes the spec branch and opens a PR targeting `main` (committing directly only as the no-remote fallback), per "Deliver: branch and PR" (`phases.md#deliver-branch-and-pr`), and updates `CHANGELOG.md` / docs as needed. Project memory is updated by the SDK memory pipeline — the SOLE memory writer — per "Deliver: SDK memory pipeline" above, with its commit riding the same spec branch. The orchestrator does NOT write `.claude/memory/` itself (`constitution.md` Rule 5; mechanically blocked by `.claude/hooks/memory-write-guard.sh`).
2. `state.json.status: completed`, `state.json.phase: deliver`, `phase_history` entry recorded.
3. `active.json` is updated to drop this feature from the active list (history kept in `active.json.archived[]`).
