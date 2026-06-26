# Routing

How an incoming prompt becomes (or doesn't become) a workflow run. The orchestrator runs this on every fresh top-level request.

## First question: does this need an artifact?

If the answer is *no*, do not engage the workflow. **Freeform mode** = direct conversational answer; no folder, no `state.json`, no phase machine. The session-capture pipeline still records the conversation, but no workflow artifact is created.

Examples of freeform: "explain how X works", "what does this function do", "walk me through the auth flow", "show me where Y is defined", quick Q&A, code reading.

If the answer is *yes*, classify into one of six workflow types.

## Workflow types

| Type | One-liner | Primary artifact |
|---|---|---|
| `feature` | New user-visible behavior | `spec.md` describing what to build |
| `bugfix` | Fix existing behavior | `spec.md` describing reproduction + expected |
| `refactor` | Improve code without changing behavior | `spec.md` describing scope + boundaries |
| `spike` | Answer a written question with a written answer | `findings.md` |
| `docs` | Update project documentation | (the docs themselves; optional `spec.md` for major redesigns) |
| `prd` | Multi-feature / platform / system-level requirements | `PRD/<NNN-slug>/prd-vN.md` |

## Decision tree

```
Incoming prompt
  │
  ├─ Pure Q&A or explanation, no artifact needed
  │     └→ freeform
  │       (For "does Claude Code do X?" questions, delegate to
  │        `agents/research/claude-code-docs.md` without engaging a workflow.)
  │
  ├─ "System / platform / redesign / rebuild / multi-feature / multi-user-facing"
  │     └→ prd  (NEW in v2; see "PRD workflow" below)
  │
  ├─ "Build / add / implement X" (new behavior)
  │     └→ feature
  │
  ├─ "Fix / X is broken / wrong output"
  │     └→ bugfix
  │
  ├─ "Refactor / clean up / restructure" (no behavior change)
  │     └→ refactor
  │
  ├─ "Investigate / can we / why does / is X feasible"
  │     └→ spike
  │
  └─ "Update README / write docs / document Y"
        └→ docs
```

## Per-type phase subset

> **Machine-readable authoritative form:** `skills/workflow/_scripts/workflow_phase_next.py` encodes this per-type subset (intersected with the complexity lane below) and is the single source of truth for the table (Rule 7). The tables in this section are illustrative/derived — keep them readable, but the script is what the workflow advances against.

Phase names are the canonical six from `phases.md`. Each type uses a subset:

| Type | Phases |
|---|---|
| `feature` | `spec → plan → tasks → implement → verify → deliver` |
| `bugfix` | `spec → tasks → implement → verify → deliver` (skip `plan` — fix path is usually direct) |
| `refactor` | `spec → plan → tasks → implement → verify → deliver` (full; `spec` defines scope, not behavior) |
| `spike` | `spec → implement → verify → deliver` (implement = investigate; output is `findings.md`, not code) |
| `docs` | `(spec) → implement → verify → deliver` (spec phase OPTIONAL — required for major redesigns, skipped for trivial doc edits) |
| `prd` | `spec → implement → verify → deliver` (no plan, no tasks; single-author) |
| `freeform` | none — direct answer, no folder |

For `feature` / `bugfix` / `refactor` / `spike`, the `implement`-phase mode (sequential single-author by default; an Agent Team as a gated opt-in) is defined canonically in `phases.md#teams-in-implement` — see also `specs/012-workflow-contract-v2/design/07-team-lifecycle.md` for the lifecycle protocol. `docs` and `prd` stay sequential single-author.

Bugfix escalates to `feature` or `refactor` if scope reveals design work mid-flight (orchestrator detects this when `tasks.md` would touch >5 files in unrelated areas).

## Complexity lane

`state.json.complexity` (`artifacts.md:118`) selects a LANE that right-sizes the phase set on TOP of the per-type subset above. This table is the canonical human-readable source of the lane mapping (Rule 7); `phases.md`, `agents/orchestrator.md`, and every other surface cite it BY PATH and never restate it. The machine-readable composed form — per-type subset INTERSECTED with this lane — is `skills/workflow/_scripts/workflow_phase_next.py`, which the workflow advances against; the tables here remain illustrative/derived.

| Complexity | Effective outcome |
|---|---|
| `trivial` | Direct edit — NO spec, NO folder, NO `state.json`. Routes to the orchestrator's edit-in-place path (`routing.md` "When to refuse a workflow"). Distinct from `freeform` (`routing.md:5-9`): `freeform` is pure Q&A / no real change; `trivial` is a real edit below workflow overhead. |
| `small` | `spec → implement → verify → deliver` — the lane drops `plan` AND `tasks` from the type's subset. |
| `medium` | The type's full subset (`routing.md:57-65`) — UNCHANGED. The lane is a strict no-op for `medium` (see "`medium` no-op regression" below). |
| `epic` | Route as `prd` — reuses the existing `needs_prd` bridge (`agents/product/requirement-analyzer.md:43-47` → `routing.md:71-93,99-110`); does not add a `prd` value to the analyzer's `type` enum. |

### Composition rule (INTERSECTION, not override)

The lane composes WITH the per-type subset by INTERSECTION, never override: the effective phase set = **the type's subset (`routing.md:57-65`) MINUS the phases the lane drops**. The lane NEVER adds a phase the type does not already have. This is what makes `medium` a provable no-op: dropping nothing from an unchanged subset is identity.

Worked examples at `small` (the lane drops `plan` + `tasks`):

- **`feature` at `small`:** type subset is `spec → plan → tasks → implement → verify → deliver`; drop `plan` + `tasks` → **`spec → implement → verify → deliver`**.
- **`bugfix` at `small`:** type subset is `spec → tasks → implement → verify → deliver` (the type ALREADY lacks `plan`); the lane drops the remaining `tasks` → **`spec → implement → verify → deliver`**. Dropping a `plan` the type never had is a no-op — INTERSECTION, not a forced removal.
- **`refactor` at `small`:** type subset is `spec → plan → tasks → implement → verify → deliver`; drop `plan` + `tasks` → **`spec → implement → verify → deliver`**.

All three `small` examples resolve to the same `spec → implement → verify → deliver` because the lane only removes phases that are present; it cannot remove a phase the type already skipped, and it cannot add one back.

### `medium` no-op regression

`medium` is identity over the per-type subset. For EACH type, the `medium` effective phase set is byte-identical to that type's row in `routing.md:57-65` — the lane drops nothing. This is the safety property (the lane only ever removes ceremony for `trivial`/`small` or reroutes `epic`, never alters `medium`):

| Type | `medium` effective set | Source row | Delta |
|---|---|---|---|
| `feature` | `spec → plan → tasks → implement → verify → deliver` | `routing.md:59` | none |
| `bugfix` | `spec → tasks → implement → verify → deliver` | `routing.md:60` | none |
| `refactor` | `spec → plan → tasks → implement → verify → deliver` | `routing.md:61` | none |
| `spike` | `spec → implement → verify → deliver` | `routing.md:62` | none |
| `docs` | `(spec) → implement → verify → deliver` | `routing.md:63` | none |
| `prd` | `spec → implement → verify → deliver` | `routing.md:64` | none |

Each `medium` row above is `medium` applied to that type with zero phases dropped, and matches the cited source row verbatim. qa-engineer diffs each row against `routing.md:57-65` to confirm zero delta per type.

## PRD workflow

`prd` is a first-class workflow type alongside `feature` / `bugfix` / `refactor` / `spike` / `docs`. It is the only workflow that produces a `PRD/<NNN-slug>/prd-vN.md` artifact.

**Triggers (any one):**

- Prompt mentions "system", "platform", "redesign", "rebuild", "from scratch"
- Multiple distinct user-facing capabilities in one ask
- Cross-cutting concern (auth, billing, observability, permissions)
- Multi-feature or multi-user-facing change
- Touches ≥6 files anticipated, OR ≥2 distinct components/services
- Update to an existing PRD ("revise PRD 003", "v2 of the billing PRD")

**Versioning:**

- Initial PRD lands at `PRD/<NNN-slug>/prd-v1.md`.
- Updates route as a new `prd` workflow run (same `<NNN-slug>` folder); implement phase authors `prd-v2.md` as a NEW file alongside v1.
- Never edit `prd-v1.md` after deliver. Never create `PRD/<NNN-slug>/v2/` (no per-version sub-folder). Never overwrite.
- The current "live" version is the highest-N file in the folder.

**Child specs:** When a PRD finalizes, child workflow runs (`feature`, `refactor`, `bugfix`) reference the PRD via `state.json.parent_prd: "PRD/<NNN-slug>"`. Child specs file **manually by the user** as separate workflow runs after the PRD's deliver phase completes — never auto-created. The PRD's deliver retro SUGGESTS first child specs to file; creation requires the user's trigger via normal prompt routing.

See `specs/012-workflow-contract-v2/design/01-prd-workflow-type.md` for the full sub-design.

## Classification mechanics

1. Orchestrator reads the cleaned prompt + relevant context (`active.json`, `constitution.md`, top-200 of `memory/MEMORY.md`).
2. **Batch-intake branch.** If `.claude/hooks/detect_batch_intent.py`'s `detect_batch_intent(prompt)` returns `True`, divert to the orchestrator's "Batch intake" subsection (see `agents/orchestrator.md`) instead of single-spec routing. The heuristic is defined in `specs/024-batch-spec-planning/design/01-detection-heuristic.md`. PRD-shape prompts are explicitly refused at the batch-intake handler.
3. If classification confidence is high (≥80%) → assign type, create folder, set initial `state.json`.
4. If ambiguous → spawn `requirement-analyzer` subagent (under `.claude/agents/product/`). It returns deterministic JSON:
   ```json
   {
     "type": "feature|bugfix|refactor|spike|docs|prd|freeform",
     "complexity": "trivial|small|medium|epic",
     "scope_files_estimate": 3,
     "needs_prd": false,
     "ambiguities": ["..."],
     "recommended_questions": ["..."]
   }
   ```
5. If `ambiguities` is non-empty → `AskUserQuestion` with the recommended questions (multi-choice with "Other (specify)" fallback).
6. Once classified, orchestrator creates folders and seeds `state.json` per `artifacts.md`.

## When to refuse a workflow

The orchestrator should **not** create a feature folder for:

- Questions that are pure explanation ("how does X work")
- Trivial edits where workflow overhead exceeds the change (single-file typo, one-line comment fix) — orchestrator edits directly
- Read-only operations ("show me where Y is defined")

When unsure, default to `freeform`. The user can always say "actually let's make this a feature" — orchestrator promotes by creating the folder retroactively.

## First-time adoption (existing project, no `.claude/` shell yet)

For projects with no prior workflow infrastructure, do not engage routing on the first prompt. Run the migration bootstrap first per `workflow/migration.md` (installs the shell side-by-side with any existing `.claude/`, or fresh), then resume normal routing. Greenfield (no code) starts with a `prd` workflow; migration starts with a `docs` workflow to install the shell.

## Refuse-and-substitute pattern

Sometimes a user proposes a workflow type that doesn't fit the content (e.g., framing an audit question as a "bugfix" when it's really a `spike`). The orchestrator must:

1. **Flag the mismatch** clearly — name why the proposed type doesn't fit (no reproduction → not bugfix; no broken behavior → not bugfix; etc.).
2. **Propose the correct type** with a one-line justification.
3. **Optionally substitute** a real candidate of the requested type from the retrospective backlog (`retrospectives/INDEX.md`) so the user's intent to test that workflow type isn't lost.
4. **Park the user's original content** as the right type (e.g., file as a spike) — never silently drop it.

Example: user said "let's test a bugfix" with content that was actually a spike. Orchestrator flagged, substituted a real bug from the retrospective backlog (`009-fix-orchestrator-delegation-doc`), AND queued the user's original content as spike `010-agent-teams-claude-code-currency-audit`. Both got run; nothing was lost. (Lesson from the bugfix 009 / spike 010 sequence.)

## Examples

| Prompt | Type | Notes |
|---|---|---|
| "Add a cancel button to the checkout page" | `feature` | single feature, small |
| "Why is login throwing 500s on Safari?" | `bugfix` | spec includes reproduction |
| "Refactor the auth middleware" | `refactor` | scope = auth middleware |
| "Can we use Postgres LISTEN/NOTIFY here?" | `spike` | output = findings.md |
| "Walk me through the auth flow" | `freeform` | no artifact |
| "Update CLAUDE.md with new test strategy" | `docs` | trivial; no spec needed |
| "Redesign the workflow contract across 12 files" | `docs` | major; spec phase REQUIRED (uses `spec-docs.md` template) |
| "Build a complete user-permissions system" | `prd` | multi-feature; produces `PRD/<NNN-slug>/prd-v1.md`; child specs filed manually after deliver |
| "Does Claude Code support nested subagents?" | freeform → `claude-code-docs` agent | no workflow; direct delegate |
| "What's wrong with the order form?" | ambiguous → orchestrator asks | likely `bugfix` after reproduction |
| "Fix this typo in README" | `freeform` (orchestrator edits directly) | trivial |
