# Evaluation

<!-- crux-only:conditional (workflow-memory-pipeline absent) -->
> **Crux-only note — the `workflow-memory-pipeline` plugin is NOT part of this crux.**
> Wherever this document refers to the SDK memory pipeline, `memory-write-guard.sh`,
> `workflow/sdk-pipeline.md`, the `agent-memory/` silos, or memory “written at every
> `deliver`”, those statements hold **only when the `workflow-memory-pipeline` companion
> plugin is installed**. In a default crux-only install there is **no memory writer and no
> guard hook**: `deliver` writes no memory, the memory stores are empty or hand-seeded, and
> nothing is auto-captured. Treat any memory/pipeline reference below as dormant unless that
> plugin is installed.

How verification works. The single highest-leverage thing in the workflow — verification is what catches bad output before it becomes bad code.

## Two roles

- **Verifier** — read-only. Reads the artifact, writes a report, never edits the artifact.
- **Fixer** — read-write. Reads the verifier report, edits the artifact, never approves itself.

Verifier and fixer are **always different agents**. Same model is fine; same agent file is not.

## Why two roles

A single agent that can both judge and fix tends to:

- silently fix-and-pass instead of surfacing what was wrong (no audit trail)
- under-report severity to avoid extra work
- collude with the upstream actor (same agent often verifies its own kind of work)

Splitting forces every problem through a written report, which builds the audit trail and gives the user / orchestrator a chance to override.

## The loop

```
actor ──► artifact
            │
            ▼
         verifier (read-only)
            │
            ▼
   verification/<phase>-report.md
            │
       ┌────┴────┐
     pass        fail
       │           │
       ▼           ▼
   advance     fixer (read-write, distinct agent)
                   │
                   ▼
                revised artifact
                   │
                   ▼
            ┌──── back to verifier
            │
   max rounds = state.json.max_fix_rounds (default 3)
            │
            ▼
   escalate to user (Pattern C in communication.md)
```

## Severity ladder

| Severity | Meaning | Effect |
|---|---|---|
| `critical` | Wrong, unsafe, or violates a constitutional rule | Verifier returns `fail` |
| `major` | Missing required content, internal contradiction, ambiguity that blocks downstream | Verifier returns `fail` |
| `minor` | Style, redundancy, polish, suggestion | Verifier returns `pass` with notes |

`pass` requires zero `critical` and zero `major` findings. `minor` findings are recorded but don't block.

## Per-phase verifier responsibilities

| Verifier | Inputs | Checks |
|---|---|---|
| `spec-verifier` | `spec.md` + matching template (by type: `spec-feature.md`, `spec-bugfix.md`, `spec-refactor.md`, `spec-spike.md`, `spec-docs.md`) + `constitution.md` | Required sections present; acceptance criteria testable; no `TBD` / `TKTK`; vocabulary (e.g. "milestone" not "phase"); constitution match |
| `plan-verifier` | `plan.md` + `spec.md` | Milestones cover all spec acceptance criteria; risks identified; rollback plan if destructive; budget ≤200 lines |
| `task-verifier` | `tasks.md` + `plan.md` (or `spec.md` for bugfix) | Every task has a deliverable; tasks map back to plan milestones (or to spec ACs for bugfix); estimates present; ordering is sane; no orphan tasks |
| `qa-engineer` (verifier role in `verify` phase) | code + tests + `spec.md` | Tests exist for every acceptance criterion; tests actually fail without the code; types pass; no skipped tests without justification. Verifier behavior is unchanged whether `implement` was teamed or single-author |
| `cross-checker` | every artifact in the feature folder | Spec ↔ plan ↔ tasks ↔ code coherence; vocabulary consistency; no stale references; every AC has a passing test cited by name; MEMORY.md shape compliance (line format, 200-line / 25KB cap, no narrative paragraphs); selective-mirror-policy COMPLIANCE (NOT exact equality) between `~/.claude/projects/<project-slug>/memory/` and `<repo>/.claude/memory/`, with the `agent-memory/` silos (canonical-only) carved out — per `workflow/artifacts.md` "Selective mirror policy" |

`cross-checker` runs once at the start of `verify` phase and is the gating verifier for the final HITL gate.

## Test-selection strategy

This is the single source of truth (Constitution Rule 7) for which tests run when. The engineering working-agreements (`.claude/agents/engineering/*.md`) and the qa-engineer agreement (`.claude/agents/review/qa-engineer.md`) cite this section by reference; they do NOT restate it.

- **Rule (a) — scoped runs during `implement` (red→green).** When an engineer iterates on a change, they run ONLY the changed / new test file, by name: `pytest <specific_test_file>`. Do NOT run `pytest tests/` (the full suite) on every task. Running the whole suite at each implement checkpoint inflates the Bash-call count and is a direct contributor to the `maxTurns` cutoffs that spec 027 tuned around — scope the run to the file under iteration instead.
- **Rule (b) — the full suite is mandatory exactly ONCE, at the `qa-engineer` verify gate.** The full suite (`pytest tests/`) is MANDATORY at exactly one gate: the terminal `qa-engineer` verify phase, where it runs as the cross-area regression gate. Running the full suite earlier (during `implement`) is optional and discouraged. This terminal gate is never skippable.

The full suite is never omitted entirely — it is **relocated** to exactly one mandatory gate, not removed. Cross-area regressions are still caught before `deliver`; only the redundant intermediate full runs go away. If the verify gate is ever reached without a prior full run during the spec, that single terminal run is the whole regression catch, so it must never itself be skipped.

## Verifier model defaults

Each verifier agent declares an explicit `model:` in its frontmatter. Current defaults (per `specs/012-workflow-contract-v2/design/10-agent-model-config.md`):

| Agent | Model | Rationale |
|---|---|---|
| `spec-verifier` | `haiku` | Structural check (sections, AC testability, vocabulary). 3-run shadow trial against Sonnet baseline. |
| `plan-verifier` | `haiku` | Same — milestone coverage, risks, rollback, budget. |
| `task-verifier` | `haiku` | Same — task deliverables, plan coverage, estimates, ordering. |
| `cross-checker` | `sonnet` | Synthesis across artifacts; mechanical greppable checks at our scale. |
| `qa-engineer` | `sonnet` | Test coverage + type checks — middle of the road. |

**Trial criteria for the Haiku downgrades** (spec/plan/task verifiers): monitor 3 consecutive runs. Pass criteria: (1) verifier writes the report cleanly (no mid-thought stalls); (2) verdict matches a Sonnet baseline shadow on the same input; (3) false-pass rate = 0; (4) false-fail rate ≤ 1 per 3. If any criterion fails, upgrade back to Sonnet and record in a retro. Full rationale + per-agent stakes in the sub-design.

`maxTurns` is a separate tuned per-agent knob. Current values live in each verifier's frontmatter (`.claude/agents/review/<verifier>.md` line 8); see that file for the authoritative value. Spec 027 documents the tuning rationale (raised after empirical observation of silent mid-flight cutoffs under the original ceilings).

## Fixer assignments

Fixers map 1:1 to phase actors, not to verifiers:

| Phase | Actor (also fixer) | Verifier |
|---|---|---|
| `spec` | `product-manager` | `spec-verifier` |
| `plan` | domain engineer | `plan-verifier` |
| `tasks` | `task-decomposer` | `task-verifier` |
| `implement` | engineers | `qa-engineer` |
| `verify` | (n/a — terminal) | `cross-checker` |

Same agent that wrote the artifact fixes it (carries context and intent). Different agent verifies it (independence).

## Verifier prompt template

```
You are <verifier-name>. Read-only.
Allowed tools: Read, Grep, Glob.
Forbidden tools: Edit, Write, Bash that mutates state.

Inputs:
- artifact: specs/<NNN>/<artifact>.md
- prior phase artifact: specs/<NNN>/<previous>.md
- template: workflow/templates/<template>.md
- constitution: constitution.md

Job:
1. Confirm artifact follows the template's required sections.
2. Compare artifact against prior-phase content for coverage and consistency.
3. Apply constitutional rules.
4. Flag findings by severity.

Output: write specs/<NNN>/verification/<phase>-report.md following the
format in workflow/artifacts.md.

Return contract:
PASS | FAIL
critical: <count>
major: <count>
minor: <count>
```

## Fixer prompt template

```
You are <actor-name> running as fixer for <phase>.
Round: <N> of <max_fix_rounds>.

Inputs:
- your previous artifact: specs/<NNN>/<artifact>.md
- verifier report: specs/<NNN>/verification/<phase>-report.md
- prior phase artifact: specs/<NNN>/<previous>.md

Job:
1. Address every critical and major finding.
2. Update the artifact in place.
3. Do NOT edit the verifier report.
4. Do NOT mark anything resolved — verifier re-runs to confirm.
5. If a finding is wrong (verifier mistake), explain in a "Disputed findings"
   section at the bottom of the artifact. Verifier reads this on re-run.

Return contract: DONE / BLOCKED / NEEDS_USER per workflow/communication.md.
```

## When to escalate to the user

Always:

1. After `max_fix_rounds` failures (Pattern C in `communication.md`).
2. When fixer returns `BLOCKED` or `NEEDS_USER`.
3. When verifier flags a constitutional violation that the fixer disputes.
4. When the verifier itself fails to run twice (infrastructure issue, not verdict).

Never:

- After a single fixer round.
- When verdict is `pass` with `minor` findings.
- When a fixer chooses to defer a `minor` (allowed; record in artifact).

## What verifiers do NOT do

- Run tests (that's `qa-engineer` in `implement` / `verify`).
- Edit code or artifacts.
- Approve their own previous output (each verifier run is fresh).
- Spawn other agents.
- Communicate with the user (only the orchestrator does that).

If a verifier needs to test something dynamic, the report says so and `qa-engineer` is invoked separately by the orchestrator.

## Cross-checker — the final gate

Before the `verify → deliver` HITL gate, `cross-checker` runs across the entire feature folder:

1. Read `spec.md`, `plan.md`, `tasks.md`, all `verification/*-report.md`.
2. Grep code for symbols mentioned in `spec.md` to confirm they exist.
3. Verify every acceptance criterion in `spec.md` has a passing test (cited by test name).
4. Verify every plan milestone is covered by tasks.
5. Verify every task is either complete or explicitly deferred with reason.
6. Verify vocabulary consistency across artifacts.
7. Write `verification/cross-check-report.md`.

If `cross-checker` passes, orchestrator presents the HITL gate. If it fails, fixer loop — but the fixer is whichever phase owner the finding traces back to (`spec-verifier` finding → `product-manager` fixer, etc.).

### Cross-checker also verifies deferred-minors didn't surface as substance

Earlier verifiers (spec-verifier, plan-verifier, etc.) may have raised `minor` findings that were deferred per Constitution Rule 6 (`pass` with notes). The cross-checker's job at the verify gate includes one extra pass: read each `verification/<phase>-report.md`, find the deferred minors, and check that none of them actually surfaced as substance in the implement output. If a deferred-minor's risk fired (e.g., a vague conditional in the spec produced ambiguity in the findings), the cross-checker escalates that finding to `major` and the verify phase fails forward to fixer-loop. (Lesson from spike 011: the spec-verifier's M-1 advisory about a conditional in the OOS section was deferred; cross-checker did not re-validate. Could have masked a real issue. Now part of the cross-checker contract.)

## Disputed findings

Fixers can mark findings as disputed in the artifact:

```markdown
## Disputed findings

### Finding 3 (verifier said "missing rollback plan")
Disputing: this refactor has no destructive operations; rollback is `git revert`.
No additional rollback plan needed.
```

The verifier on the next round MUST address each disputed finding — either accept the dispute (mark `minor` or remove) or reaffirm with explanation. Three disputes in a row on the same finding → escalate to user; orchestrator never breaks the tie.

## Verifier independence guard

A verifier agent file MUST NOT also appear in any phase's actor or fixer slot. If you find yourself wanting to reuse an agent across roles, split it into two agent files with different `permissionMode` (verifier: `default` with read-only tools; fixer: `default` with full tools). The split is the whole point.

## Renames and downstream cleanup

When a verifier raises a `minor` finding that suggests a **rename, terminology change, or enum-value change**, the change MUST land in BOTH the artifact under review AND any downstream artifacts that already reference the original term.

Two acceptable resolutions:

1. **Re-spawn the same phase's fixer** for the rename only — cheap, single round, ensures the canonical artifact is correct before downstream actors run.
2. **Have the next-phase actor adopt the rename** during their normal work AND reach back to update the originating artifact in the same workflow run.

What's NOT acceptable: folding the rename only into the next phase's task design while leaving the prior artifact unchanged. That produces drift between phases (caught in spike 010 when `phased-migration` enum in `spec.md` and `staged-migration` in `findings.md` diverged because the spec verifier's rename suggestion was honored downstream but never reflected upstream).

For non-rename minor findings (style, polish, redundancy), the original "fold-or-fix" guidance applies: a fixer can address them, OR the next-phase actor can fold them into task design — but no upstream rewrite is required because the finding doesn't create cross-artifact drift.

## Cost note

Verification roughly doubles the per-phase agent cost. This is the explicit tradeoff for catching errors before they compound. To lower cost on low-risk work, set `state.json.autonomous: true` (skips HITL gates but still runs verifiers) — never disable verifiers. The "always-pause" events that the autonomous flag CANNOT skip are defined in `phases.md` ("Autonomous mode interaction rules", Rule B) — verifier-fixer-loop escalation is one of them.
