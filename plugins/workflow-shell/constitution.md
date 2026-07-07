# Constitution

The non-negotiable principles for work in this repo. Loaded every session via `CLAUDE.md`. The orchestrator and every subagent reads this. Verifiers cite it when flagging findings.

## What goes here

Rules that hold regardless of the immediate task. If a user instruction contradicts a constitutional rule, the orchestrator surfaces the conflict via `AskUserQuestion` instead of silently overriding.

Examples:
- Test requirements (every new behavior gets a test)
- Architecture invariants (e.g. no business logic in controllers)
- Security rules (e.g. never log secrets, never write user PII to disk unencrypted)
- Definition-of-done (e.g. PR description, CHANGELOG entry, types pass)

## What does NOT go here

- Project-specific conventions (stack choices, repo layout) → `CLAUDE.md`
- Code style (lint rules, formatting) → `rules/`
- Workflow contract (phases, routing, artifacts) → `workflow/`
- Per-feature decisions → `specs/<NNN>/`

## Starter principles

These are opinionated defaults. Edit or delete each per project needs.

### 1. Tests are part of every change
Every new behavior or bug fix lands with a test that fails before the change and passes after. Refactors land with the existing tests still green and no coverage loss.

### 2. No silent suppression
Errors are handled explicitly or surfaced. Catch-all blocks that swallow exceptions, ignored linter warnings, and skipped tests are constitutional violations. If something is intentionally skipped, the reason is in a comment AND in the relevant artifact.

### 3. Reversibility first
Prefer changes that can be reverted in one commit. Migrations, schema changes, and destructive operations require a `plan.md` with explicit rollback steps before `tasks` can begin.

### 4. Boundary discipline
Public APIs (HTTP, CLI, library exports, persisted data shapes) require a `spec.md`. Internal helpers do not. The line is "would another human or system call this directly?"

### 5. Memory hygiene
Decisions worth referring back to land in `.claude/memory/topics/<topic>.md` (architectural choices, incidents, conventions, "why we did it this way"). Ephemera does not — current task state lives in `state.json` / `tasks.md`, not memory.

The SDK memory pipeline is the SOLE writer of memory. The orchestrator and every subagent MUST NOT write `.claude/memory/`, `.claude/agent-memory/`, or the canonical `~/.claude/projects/<slug>/memory/` — enforced mechanically by `.claude/hooks/memory-write-guard.sh`. These project instructions override Claude Code's built-in auto-memory behavior; the auto-memory-disable setting's scope is covered in `specs/029-memory-sdk-sole-writer/design/auto-load-mechanics.md` (fact 5).

### 6. Verifier authority
Verifier failure blocks phase advance. The orchestrator does NOT override a verifier — it can only spawn a fixer (within `max_fix_rounds`), escalate to the user, or roll back. A passing verifier with `minor` findings can advance; `critical` or `major` cannot.

### 7. One source of truth per fact
Every fact lives in exactly one file. If `spec.md` says "we use Postgres" and `plan.md` says "we use SQLite", `cross-checker` flags the contradiction. Cross-references via path:line, not duplication.

## Amendments

To change this file, run a `docs` workflow. The amendment lands with reasoning in the commit message and a one-line entry in `memory/topics/decisions.md`. Constitutional changes are uncommon — if you're amending more than once a quarter, the rules are too specific and should move to `rules/` or `CLAUDE.md`.
