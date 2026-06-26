# shell-audit — strategic shell-review mechanism

A saved, **re-invocable** strategic review of the workflow shell's architecture. Run it on demand or on the cadence documented in `workflow/README.md` "Recurring strategic review (`shell-audit`)". It fans out read-only auditors over five strategic dimensions, applies an adversarial skeptic pass per dimension, and emits **ranked, queue-ready findings the orchestrator hand-files** to `workflow/queue.md`.

This artifact is the **definition document** the orchestrator reads to drive the review. It is NOT a native Claude Code `Workflow` script.

## Substrate

**Orchestrator-driven Agent-Team fan-out reading this Markdown definition.** Selected from the Milestone-1 capability probe (`specs/052-dynamic-workflow-review/verification/probe-workflow-tool.md`): the native `Workflow` tool returned `conditional` for structured/schema'd return and `conditional` for cross-session resume, so it was NOT selected. The Agent-Team substrate is the shell's proven, already-permissioned fan-out; no `settings.json` change is required to run this review.

The orchestrator spawns one auditor per dimension as an **inline read-only role prompt** (the role text lives in this file — see each dimension below), reusing existing read-only agents where natural (e.g. `agents/research/claude-code-docs.md` for the cc-config-correctness dimension). **No `agents/**` file is created or edited by this mechanism** — auditors are inline prompts, so the self-modification classifier is not engaged.

**One-shot exception:** the *saved, re-invocable* mechanism uses the Agent-Team fan-out (above), since native `Workflow` is only `conditional` for structured-return and cross-session resume. A **one-shot** run driven directly from the main session MAY instead use the native `Workflow` tool — the 2026-06-17 dogfood did exactly this, and both fan-out and per-agent `schema` structured returns worked for a single, non-resumable run. This does not change the selected substrate for the saved mechanism.

## Read-only contract

This review is **read-only**. It transports findings; it never decides and never writes.

- **No auditor is granted `Write` or `Edit`.** Auditors receive `Read`, `Grep`, `Glob` (and `WebFetch` for the cc-config-correctness dimension only). The fan-out grants no write tool to any auditor.
- Auditors are **forbidden** from writing any of:
  - `memory/` and `agent-memory/` — Rule 5; the SDK memory pipeline is the sole memory writer. This review is never a memory writer.
  - contract docs — `workflow/*`, `CLAUDE.md`, `constitution.md`, `rules/*`.
  - `state.json` / `active.json` — workflow state stays orchestrator-owned.
- Findings are emitted to the orchestrator for **hand-filing only**. The review produces text; the orchestrator (not the review) files ranked slugs to `workflow/queue.md`.

The boundaries this review may NOT cross — HITL gates, Rule 6 verdict arbitration, Rule B always-pause events, Rule 5 memory writes, and `state.json`/`active.json` mutations — are documented in `workflow/README.md` "Recurring strategic review (`shell-audit`)" and stay orchestrator-owned.

## Dimensions (fan-out)

The review fans out over **exactly these five strategic dimensions**, no more and no fewer. Each auditor runs independently and returns the [findings schema](#findings-schema).

### 1. memory-architecture

**Scope:** the SDK memory pipeline's scaling architecture — single-subprocess sufficiency, proposer/writer split, chunking, silo shape enforcement, mirror policy. Reads `hooks/sdk_memory_pipeline.py`, `hooks/_memory_writer.py`, the proposal schema, and `workflow/sdk-pipeline.md`. Surfaces scaling/insufficiency findings; does NOT re-architect the pipeline (that is the `memory-pipeline-multiagent` queue slug).

### 2. hook-utility

**Scope:** every wired hook under `.claude/hooks/` and `settings.json` — is each hook still earning its place, firing on the right events, and free of dead/duplicated logic? Reads `settings.json` hook wiring and the `hooks/*.sh` / `hooks/*.py` sources.

### 3. legacy-methodology-reconcile

**Scope:** diff `_legacy/` against the current shell — identify methodology that regressed, was dropped silently, or should be re-adopted. The auditor compares the `_legacy/` snapshot of prior workflow methodology against the live contract docs and flags regressions. (If `_legacy/` is absent at run time, the auditor records that as a `healthy_aspects` note, not a finding.)

### 4. cc-config-correctness

**Scope:** active Claude Code config fields (`settings.json`, frontmatter `memory:`/`permissionMode:`/`tools:`, output styles) checked against **live Claude Code docs**. This dimension uses `agents/research/claude-code-docs.md` and `WebFetch` (read-only) to confirm each config field is real, correctly named, and used as documented — catching invented or stale config (the refuted-`parallel()` class).

### 5. contract-freshness-governance

**Scope:** `workflow/*`, `CLAUDE.md`, and `constitution.md` checked against reality — do the contract docs still describe what the shell actually does? Flags stale governance, vestigial rules, and drift between the documented contract and the implemented mechanism.

## Out of scope — excluded dimensions

This review **explicitly excludes** the per-merge cross-review coroutine's four tactical drift categories. They are named here as **out-of-scope** so the two reviews never overlap (Rule 7):

- **stale citations** — line-number citation drift.
- **dead links** — broken `path` / `path#heading` references.
- **stack drift** — agent/rule files describing a stack the repo does not have.
- **contradictions** — one-source-of-truth violations across artifacts.

These are covered by the per-merge `cross-checker` coroutine and are not re-litigated by `shell-audit`.

## Findings schema

Each dimension auditor returns a capped findings list — **≤5 per dimension** — plus a `healthy_aspects` list. Every finding carries exactly these fields:

| Field | Meaning |
|---|---|
| `title` | one-line finding name |
| `problem` | what is wrong or at risk |
| `evidence` | `path:line` or a cited upstream URL (with retrieval date) |
| `proposal` | the suggested change |
| `effort` | `S` / `M` / `L` |
| `impact` | expected value of acting (qualitative + relative) |
| `confidence` | `0`–`100` — how sure the auditor is the finding is real |

- `findings` — list, **≤5 per dimension** (capped; the strongest five if more are found).
- `healthy_aspects` — list of things the dimension checked and found sound (so a clean dimension is not silent).

## Skeptic pass

After the fan-out, an **adversarial skeptic pass runs per dimension**. For each finding the skeptic records one of:

- `confirmed` — evidence holds; the finding stands.
- `weak` — partially supported; ranks last.
- `refuted` — evidence does not hold; ranks last, retained with the reason (Rule 2 — nothing is silently swallowed).

Every `weak` and `refuted` mark carries a recorded reason.

**This skeptic pass is per-dimension skepticism feeding the orchestrator — it is NOT a merged verdict and NOT a phase verifier.** It does not arbitrate, it does not replace any phase verifier, and it does not merge per-dimension labels into a single verdict (Rule 6: verifier authority stays single and orchestrator-arbitrated). The skeptic labels travel with each finding to the orchestrator.

## Ranking and filing

Confirmed findings are ranked by:

```
impact × confidence ÷ effort
```

(`weak` and `refuted` findings rank last regardless of score.) Effort `S`/`M`/`L` maps to a small/medium/large divisor so cheap high-impact findings rise.

Before emitting, the review runs a **dedupe diff against `workflow/queue.md`**: each ranked finding is either **mapped** to an existing `queue.md` slug (if it restates a known item) or proposed as a **NEW slug**. The output is a ranked list of mapped-or-new slugs in hand-fileable form.

The orchestrator — not this review — hand-files the ranked slugs to `workflow/queue.md`. This review writes nothing.
