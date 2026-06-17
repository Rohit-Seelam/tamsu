---
name: workflow-rules-review
description: Periodic review of `.claude/rules/` for drift. Triggered every N specs (default N=5) at deliver. Outputs candidate amendments to `.claude/rules/_candidates-<YYYY-MM-DD>.md` for the user to accept via a `docs` workflow.
allowed-tools: Read, Grep, Glob, Write
argument-hint: "[--n <count>] [--force]"
---

# Workflow: Rules Review

Periodic candidate-amendment generator for `.claude/rules/`. Surfaces drift, does NOT auto-apply changes.

## Trigger

At the `deliver` phase of the Nth completed spec since the last rules-review. Default `N = 5`, configurable via `CLAUDE.md`'s `rules_review_every_n_specs:` key (or by invoking with `--force` to run immediately).

The orchestrator (or the SDK memory pipeline at `deliver` — `workflow/sdk-pipeline.md`) invokes this skill.

## Inputs

- `.claude/rules/*.md` — current rules.
- `.claude/retrospectives/*.md` from the last N completed specs.
- `.claude/memory/topics/decisions.md` entries from the last review period.
- `.claude/active.json.archived[]` for the spec-count check.

## Output

`.claude/rules/_candidates-<YYYY-MM-DD>.md` — a markdown file with candidate amendments. Each candidate has:

```markdown
### Candidate <N>: <one-line summary>

**Category:** drift / new-convention / contradiction

**Current rule (if any):** <path:line> — <quote>

**Evidence:**
- spec <NNN>: <observation>
- spec <MMM>: <observation>
- decisions.md <date>: <quote>

**Proposed amendment:**
<rule text or "remove rule X" or "add new rule">

**Disposition:** [ ] accept  [ ] reject  [ ] defer
```

## Steps

1. Count completed specs since last `_candidates-*.md` (or since baseline). If < N AND not `--force`, exit no-op.
2. Read all of `.claude/rules/*.md` into memory.
3. Read the last N retrospectives + recent `decisions.md` entries.
4. For each rule, scan retrospectives/decisions for:
   - **Drift** — the rule says X, but the last N specs consistently did Y.
   - **New convention** — the last N specs consistently followed Y, but it's not in the rules.
   - **Contradiction** — `decisions.md` records a choice that conflicts with an existing rule.
5. Write candidates to `_candidates-<YYYY-MM-DD>.md` using the shape above.
6. Surface a one-line summary to the orchestrator: `"Rules review complete; N candidate amendments at _candidates-<date>.md. Review and decide."`

## User action

1. Read `_candidates-<date>.md`.
2. For each candidate, tick `accept` / `reject` / `defer`.
3. For accepted candidates, file a `docs` workflow that edits the relevant `rules/*.md` file. The `docs` workflow runs normally through `spec → implement → verify → deliver` per `workflow/phases.md`.
4. Delete `_candidates-<date>.md` once all candidates are dispositioned.

## No automatic application

This skill ONLY surfaces candidates. Edits to `rules/` happen via the standard `docs` workflow, with verifier-fixer loops engaged. Constitutional rule (Rule 6 — verifier authority) is honored.

## Why a skill, not a workflow type

A workflow type would force a `rules-review` workflow run every N specs. Too much ceremony for a periodic check that's usually a no-op. A skill is invokable from any deliver-phase context, produces a file the user can ignore or act on, and stays low-friction.

## Failure modes

- No retrospectives in the lookback window → exit no-op with a one-line note.
- `_candidates-<date>.md` already exists from a prior unfinished review → do not overwrite; append "(continued)" to the existing file with new candidates.

## Out of scope (scaffolding note)

The actual scanning heuristics (regex patterns for "rule says X but reality is Y") are scaffolding-grade for spec 012's implement phase. The live runtime (full retro-parsing, semantic conflict detection) lands in a follow-up `feature` workflow per `specs/012-workflow-contract-v2/spec.md`'s out-of-scope list.
