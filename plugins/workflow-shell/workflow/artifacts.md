# Artifacts

<!-- crux-only:conditional (workflow-memory-pipeline absent) -->
> **Crux-only note — the `workflow-memory-pipeline` plugin is NOT part of this crux.**
> Wherever this document refers to the SDK memory pipeline, `memory-write-guard.sh`,
> `workflow/sdk-pipeline.md`, the `agent-memory/` silos, or memory “written at every
> `deliver`”, those statements hold **only when the `workflow-memory-pipeline` companion
> plugin is installed**. In a default crux-only install there is **no memory writer and no
> guard hook**: `deliver` writes no memory, the memory stores are empty or hand-seeded, and
> nothing is auto-captured. Treat any memory/pipeline reference below as dormant unless that
> plugin is installed.

Folder layout, file naming, and the two state files (`state.json`, `active.json`) every agent reads and writes.

## `.claude/` folder layout

```
.claude/
├── CLAUDE.md                     # imports README.md + constitution.md
├── settings.json                 # shared, committed (canonical baseline)
├── settings.local.json           # gitignored, personal (machine-specific overrides)
│
├── workflow/                     # this folder — the contract
│   ├── README.md
│   ├── phases.md
│   ├── routing.md
│   ├── artifacts.md
│   ├── communication.md
│   ├── evaluation.md
│   ├── migration.md              # onboarding guide for adopting the shell
│   └── templates/                # spec-*, plan-*, tasks-*, findings.md, state.json
│
├── constitution.md               # principles (loaded every session)
│
├── PRD/                          # `prd` workflow output (first-class workflow type)
│   └── <NNN-slug>/
│       ├── prd-v1.md             # initial version; never overwritten
│       ├── prd-v2.md             # update lands as a NEW file (same folder, NOT a sub-folder)
│       └── verification/         # cross-check-report.md
│
├── specs/                        # per-feature work
│   └── <NNN-slug>/
│       ├── state.json            # required, every feature
│       ├── spec.md               # all types (optional for docs trivial edits)
│       ├── plan.md               # feature, refactor only
│       ├── tasks.md              # feature, bugfix, refactor
│       ├── findings.md           # spike only
│       ├── design/               # sub-files when spec.md > 150 lines (e.g., 012)
│       │   └── <NN>-<topic>.md
│       ├── teams/                # team audit copy (when implement ran as a team)
│       │   └── <team-name>/      # cp -r of ~/.claude/teams/<team-name>/
│       ├── verification/         # per-phase verifier reports
│       │   ├── spec-report.md
│       │   ├── plan-report.md
│       │   └── …
│       └── notes.md              # optional, agent scratch
│
├── active.json                   # cross-feature pointer; orchestrator reads first
│
├── sessions/                     # local capture archive (SUPPLEMENTARY; not auto-loaded)
│   ├── mainagent/
│   │   ├── raw/<session-id>.jsonl
│   │   └── raw/<session-id>-segment-N.jsonl   # PreCompact archive
│   ├── teammates/                # per-teammate raw JSONLs (when implement is teamed)
│   │   └── <team-name>/<teammate-name>/raw/...
│   ├── subagents/<agent>/raw/    # non-team subagent invocations
│   └── .counters/                # <session-id>.json — segment counters
│
├── memory/                       # git-tracked MIRROR; not the canonical auto-load
│   ├── MEMORY.md                 # mirror of ~/.claude/projects/<project-slug>/memory/MEMORY.md
│   └── topics/
│
│   (agent-memory/<agent>/ — per-agent silos: active & SDK-written, guarded; see CLAUDE.md)
│
├── retrospectives/               # post-spec retros + index.md
│
├── rules/                        # always-on (general.md, claude-code.md) + path-scoped
├── agents/                       # categorized; orchestrator.md + product/engineering/review/research/ops/
├── skills/                       # categorized; memory/, research/, workflow/, media/
└── hooks/                        # scripts; wired in settings.json
```

**Note on the auto-loaded memory path.** The CANONICAL auto-loaded outer memory directory is `~/.claude/projects/<project-slug>/memory/` (user-side, machine-local), NOT `<repo>/.claude/memory/`. `autoMemoryDirectory` is honored at project/local scope only behind the workspace-trust dialog (NOT silently rejected — corrected spec 033; authoritative explanation in `rules/claude-code.md` "Auto-memory canonical location"); we keep the default canonical location and do not redirect it. The repo-side `<repo>/.claude/memory/` is a git-tracked MIRROR, kept in sync by the SDK memory pipeline at every `deliver`. The per-subagent silos at `<repo>/.claude/agent-memory/<agent>/` are ACTIVE for the 6 silo agents under the single-writer model (spec 034; `frontend-engineer` dormant since spec 047): each auto-loads via `memory: project`, the SDK memory pipeline is the SOLE writer, and `memory-write-guard.sh` blocks non-SDK actors. These silos are canonical-only (a per-agent store, not part of the workflow `MEMORY.md` mirror class).

## ID and naming rules

- **ID** is a zero-padded 3-digit number, **project-monotonic across `PRD/` and `specs/` combined**. So if `PRD/003-billing` exists, the next thing — PRD or spec — is `004-…`. Prevents collision; trades neat sub-numbering for global uniqueness.
- **Slug** is kebab-case, lowercase ASCII, ≤30 chars. Reflects the work, not implementation detail. Stable: rename folder freely; `state.json.id` doesn't change.
- **Files inside a feature folder** use canonical names (`spec.md`, `plan.md`, etc.). Never timestamp them; the folder-level numeric prefix is the only ordering primitive.
- **PRD versioning** — files inside `PRD/<NNN-slug>/` use `prd-vN.md` shape. `N` is monotonic, starts at 1, never overwritten. NEVER create `PRD/<NNN-slug>/v2/` sub-folder. The current "live" version is the highest-N file in the folder. Updates route as a new `prd` workflow run that adds the next version file alongside its predecessors.
- **Team audit copy** — when `implement` runs as a team for `feature` / `bugfix` / `refactor` / `spike`, the orchestrator `cp -r ~/.claude/teams/<team-name>/ specs/<NNN>/teams/<team-name>/` at implement-end. `<team-name>` = `<project-slug>-<spec-id>-<spec-slug>` (project-prefixed to avoid collision in the global `~/.claude/teams/` namespace). Retained indefinitely. See `specs/012-workflow-contract-v2/design/07-team-lifecycle.md`.
- **Never delete** a feature folder. Mark archived in `active.json`. (Audit trail.)

## `state.json` schema

```json
{
  "id": "NNN-slug",
  "type": "feature",
  "phase": "plan",
  "status": "in_progress",
  "complexity": "medium",
  "autonomous": false,
  "max_fix_rounds": 3,
  "parent_prd": null,
  "started": "2026-04-26T10:00:00Z",
  "completed": null,
  "phase_history": [
    {
      "phase": "spec",
      "started": "2026-04-26T10:00:00Z",
      "completed": "2026-04-26T10:42:00Z",
      "verifier_pass": true,
      "fix_rounds": 0
    }
  ],
  "active": true,
  "tags": []
}
```

| Field | Values | Notes |
|---|---|---|
| `id` | `NNN-slug` | matches folder name |
| `type` | `feature \| bugfix \| refactor \| spike \| docs \| prd` | from `routing.md` |
| `phase` | one of the six in `phases.md` | current phase |
| `status` | `in_progress \| paused \| completed \| blocked \| queued` | overall. `queued` is the post-batch-intake, pre-promotion state; pairs with `phase: "spec"`. See `specs/024-batch-spec-planning/design/02-active-json-schema.md`. |
| `complexity` | `trivial \| small \| medium \| epic` | from `requirement-analyzer`; selects the lane (see the lane mapping in `workflow/routing.md`). `trivial` is a transient classifier verdict that routes to the no-folder direct-edit path and never persists to a `state.json` on disk. |
| `autonomous` | bool | when true, HITL gates skipped |
| `max_fix_rounds` | int (default 3) | verifier-fixer loop cap |
| `parent_prd` | path or `null` | e.g. `"PRD/003-billing"` |
| `phase_history` | append-only array | one entry per phase completion or rollback |
| `active` | bool | mirrored in `active.json` |
| `tags` | string[] | optional categorization |

## `active.json` schema

Lives at `.claude/active.json`. Orchestrator's first read on every session.

```json
{
  "active": [
    {
      "id": "NNN-slug",
      "path": "specs/NNN-slug",
      "type": "feature",
      "phase": "plan",
      "started": "2026-04-26T10:00:00Z"
    }
  ],
  "queued": [
    {
      "id": "PPP-other-slug",
      "path": "specs/PPP-other-slug",
      "type": "feature",
      "phase": "spec",
      "queued_at": "2026-04-26T10:30:00Z"
    }
  ],
  "archived": [
    {
      "id": "MMM-other-slug",
      "path": "specs/MMM-other-slug",
      "completed": "2026-04-25T18:00:00Z"
    }
  ],
  "prds": []
}
```

Orchestrator writes here on workflow-init (add to `active`), on batch-intake (append to `queued`), on promotion (move from `queued` to `active`), on completion (move to `archived`), and on rollback (status update only).

**`queued[]` field (added by spec 024).** Holds specs that were authored via batch-intake and approved at the batch HITL gate, but have not yet been user-promoted to `active`. Each entry shape: `{id, path, type, phase: "spec", queued_at}`. The `phase` value is always literal `"spec"` (queued entries sit at spec-phase post-authoring). Full schema, examples (v1- and v2-shape), and the backward-compat missing-key rule live in `specs/024-batch-spec-planning/design/02-active-json-schema.md` — that file is the source of truth; this section cross-references it.

**Backward-compat (missing-key-equals-empty).** An `active.json` lacking the `queued` key is treated as `queued: []`. Readers MUST use `data.get("queued", [])` (or equivalent). No on-disk migration is required; the first batch-intake invocation introduces the key by writing the updated `active.json`.

**Invariants.** (a) `len(active) ≤ 1` — single-active invariant, enforced by `cross-checker`; flagged `critical` when violated. (b) A slug present in `workflow/queue.md` MUST NOT also appear in `queued[]` — once a slug promotes to a spec via batch-intake, the same tool batch that creates the spec folder removes the slug from `queue.md`; flagged `major` when violated. Both invariants are documented in `specs/024-batch-spec-planning/spec.md` AC-7 and AC-11 respectively.

### Invariant: `active.json.<entry>.phase` mirrors `state.json.phase`

Whenever `state.json.phase` advances (or rolls back), the matching `active.json.active[i].phase` MUST be updated in the same tool batch. The two values are mirror copies; the SessionStart resume hook reads `active.json` for status display, while subagents read `state.json` for the contract — divergence produces stale display but does NOT corrupt the workflow.

The T1.2 tool-batching rule (don't batch `state.json` Edits with `Agent` calls) does NOT apply to `active.json`; the two json edits should be issued together. (Lesson from spike 011: phase advance touched only state.json; resume hook surfaced a stale active.json — caught at recovery, no real harm, but a real workflow gap.)

## Verification report format

`specs/<NNN>/verification/<phase>-report.md`:

```markdown
---
phase: spec
verifier: spec-verifier
artifact: spec.md
date: 2026-04-26
status: pass | fail
fix_round: 0
---

## Findings

- **severity:** critical | major | minor
  **section:** AC-Rule
  **issue:** <what's wrong>
  **suggestion:** <fix>
```

Status `pass` means no `critical` or `major` findings. `minor` findings can pass.

## File budgets

Soft caps; verifier flags overflow.

| Artifact | Cap |
|---|---|
| `spec.md` | 150 lines |
| `plan.md` | 200 lines |
| `tasks.md` | no cap (task list) |
| `findings.md` | 300 lines |
| `prd-vN.md` | 300 lines |
| Per verification report | 100 lines |
| `state.json` | tiny |
| `MEMORY.md` (any) | 200 lines OR 25KB, whichever first |

If exceeded, the authoring agent must split into linked sub-files (e.g. `spec.md` references `design/<NN>-<topic>.md`).

## MEMORY.md shape

Every `MEMORY.md` file in the project follows the same shape contract — both at `~/.claude/projects/<project-slug>/memory/MEMORY.md` (canonical auto-load) and at the `<repo>/.claude/memory/MEMORY.md` mirror.

**Two physical locations for outer MEMORY.md:**

- **Canonical (auto-loaded by Claude Code):** `~/.claude/projects/<project-slug>/memory/MEMORY.md`. Anthropic auto-loads this on session start. Project-scope `autoMemoryDirectory` is honored only behind the workspace-trust dialog (not rejected — corrected spec 033; see `rules/claude-code.md`); we do not redirect it.
- **Audit mirror (git-tracked):** `<repo>/.claude/memory/MEMORY.md`. Written by the SDK memory pipeline alongside the canonical, but holds only the workflow/mirrored class per the "Selective mirror policy" below — it is not a verbatim copy of the canonical.

The per-subagent silos at `<repo>/.claude/agent-memory/<agent>/MEMORY.md` are ACTIVE for the 6 silo agents under the single-writer model (spec 034; `frontend-engineer` dormant since spec 047): each silo agent auto-loads its own index via `memory: project`, and the SDK memory pipeline is the SOLE writer. `.claude/hooks/memory-write-guard.sh` blocks any non-SDK actor from writing the path. These silos are canonical-only (a per-agent store), not part of the workflow `MEMORY.md` mirror class.

### Selective mirror policy

The two outer stores are NOT verbatim copies of each other. Outer memory is classified into two mutually exclusive classes, and only one is mirrored to the repo:

- **Personal / canonical-only** — user-profile entries: the user's role, communication style, and personal feedback/preferences. These live ONLY in the canonical store (`~/.claude/projects/<project-slug>/memory/`) and are NEVER committed to the (shareable-template) repo.
- **Workflow / mirrored** — decisions, conventions, per-spec characterization, and routing/process facts. These are present in BOTH stores with matching content.

This is the single authoritative definition of the policy (Constitution Rule 7); `agents/review/cross-checker.md` and `CLAUDE.md` reference it by path and do NOT restate the classification. "Matching content" for a mirrored file means the memory body matches; the repo mirror may omit machine-local frontmatter attribution (e.g. `originSessionId`, `node_type`) that must not be committed to the shareable template. Consequence for the indexes: a canonical `MEMORY.md` indexes personal + workflow entries; a repo `MEMORY.md` indexes workflow entries only. Neither index may contain a dead link (a line resolving to a file absent from that same store), and neither store may hold an unindexed orphan topic file.

**Line shape.** Each non-blank, non-heading line follows:

```
- [Title](topics/file.md) — one-line hook ≤80 chars
```

- `Title` ≤40 chars, human-readable.
- `topics/file.md` relative to the MEMORY.md's directory.
- Em-dash separator is literal ` — ` (space, em-dash, space).
- Hook ≤80 chars including the dash.

**Hard cap.** 200 lines OR 25KB per file, whichever first (per Anthropic docs: "The first 200 lines of MEMORY.md, or the first 25KB, whichever comes first" load at session start). Headings (`#`, `##`) are allowed but don't count against the cap.

**No narrative paragraphs.** MEMORY.md contains ONLY: optional h1 title, optional ≤3-line preamble, headings, and index lines. Narrative content lives in the topic files. Narrative ≥2 consecutive non-bullet lines in MEMORY.md is an automatic `major` finding for cross-checker.

**Topic file overflow.** When a topic file exceeds ~300 lines (mirrors `findings.md` cap), the SDK memory pipeline splits it on sub-topic boundaries and updates the parent MEMORY.md with one new index line per split file.

**Mirror-policy compliance** between canonical and audit-copy is verified by `cross-checker` during every workflow's `verify` phase, per the "Selective mirror policy" above (not exact equality). Three sub-checks: every workflow-class topic file exists in both stores with matching content; every personal-class file is canonical-only and absent from the repo; and neither store holds an unindexed orphan topic file nor a dead index link. The `agent-memory/` silos are CARVED OUT of this check (canonical-only, not in the mirror class). A policy violation is a `major` finding (repo-side divergence is recoverable by re-running the SDK).

The SDK memory pipeline (`workflow/sdk-pipeline.md`) is the canonical writer of both `~/.claude/projects/<project-slug>/memory/` AND `<repo>/.claude/memory/` post-v2 via a **propose→write** split: the LLM half EMITS a structured proposal (writing no files), then a deterministic Python writer turns the proposal into files — it writes the canonical store and mirrors the non-personal subset into the repo audit copy (no LLM file write at all). Agents do NOT edit memory files mid-workflow; only the SDK subprocess at `deliver` does. This single-writer contract is now ENFORCED mechanically by the `PreToolUse` guard `.claude/hooks/memory-write-guard.sh` (spec 029), which blocks any non-SDK actor from writing the three memory roots.

## Cross-references between artifacts

- `state.json.parent_prd` → relative path to PRD folder
- `plan.md` opens with a "Spec coverage" section listing which spec sections it addresses
- `tasks.md` opens with a "Plan coverage" section mapping tasks to plan milestones
- Verifier reports cite `artifact:line` ranges where possible

## Templates folder

`.claude/workflow/templates/` (drafted in second pass):

```
templates/
├── spec-feature.md
├── spec-bugfix.md
├── spec-refactor.md
├── spec-spike.md
├── plan-feature.md
├── plan-refactor.md
├── tasks-feature.md
├── tasks-bugfix.md
├── tasks-refactor.md
├── findings.md
└── state.json
```

Phase-actor agents copy the template at the top of their work and fill in. Verifier reads template alongside artifact and flags missing required sections (cheap structural check before semantic review).
