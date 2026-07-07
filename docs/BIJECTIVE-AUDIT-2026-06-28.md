# Bijective supply-chain audit — canonical `.claude/` ↔ `workflow-shell` plugin

**Date:** 2026-06-28
**Method:** 12-agent orchestrated audit (5 subtree auditors → 5 adversarial verifiers → 1 referential-integrity checker → 1 synthesizer). ~620K tokens, 147 tool uses.
**Scope:** every path in canonical `/Users/rohitseelam/Projects/scratchpad-priv/.claude` classified A/B/C against the target end-state (single `workflow-shell` plugin @ 0.3.0 shipping the FULL contract including memory + full hook parity).
**Counts:** Class A = 67 · Class C = 26 · **gaps = 46 (16 high)**.

## Why this audit exists

The earlier `WORKFLOW-INVESTIGATION-2026-06-19.md` was narrative-driven — it reasoned about *which concepts to port*. Narrative porting has one signature failure: **silent omission**. You port what you're thinking about; anything else falls through with no error. The 350K hook, the entire memory pipeline, and the `claude-code-docs-fetch` skill were never *decided against* — they were never enumerated. This audit replaces reasoning with a **total, bijective accounting**: every canonical path lands in exactly one bucket with a written reason, so "what are we missing" becomes a finite, reviewed list instead of a feeling.

## Executive summary

The `workflow-shell` plugin as currently cut is a **partial delivery that silently honors only the "happy path"** of the contract:

- The **entire memory pipeline** (`sdk_memory_pipeline.py` + its 8 sibling helpers, `sdk-memory-pipeline.sh`, `capture-session.sh`, `compile-session.sh`, `memory-write-guard.sh`) and **six of the eight settings-wired hooks** are absent.
- The **`research/claude-code-docs-fetch` skill that a SHIPPED agent declares as its sole tool** is missing — a registered agent whose core capability is inert.
- The authoritative **`workflow/sdk-pipeline.md`** contract doc (cited by 9 shipped docs) is unshipped — every link dead-ends.
- `constitution.md` + 7 contract docs ship a `conditionalize_crux` **"crux-only / memory writer is INERT" banner that is flatly FALSE** for the one-shell-ships-everything 0.3.0 target — and the constitution is injected **every session**, so the false guarantee is always-on.

### Systemic root cause

`repackage.sh` is a **hand-maintained allow-list pipeline** — it copies only explicitly named docs/rules/skills and treats `hooks/` as a frozen Class-B directory it refuses to touch — so anything not on the allow-list is dropped without warning. `report_unmapped.py` then **rubber-stamps the omission** via stale blanket `EXCLUDED` globs (`hooks/*`, `skills/memory/*`, `skills/research/*`, `settings.sdk-memory.json`) whose "it's a hook / it's per-project" comments were never reconciled to the merged target. **Unknown silently became excluded.**

Two transforms additionally **corrupt Class-A content that IS shipped**: `conditionalize_crux.py` re-injects the false memory-split banner on every cut, and the python/bash `REPO_ROOT` assumption (`.claude/hooks/` → two-levels-up is repo root) breaks the instant the code is relocated under `${CLAUDE_PLUGIN_ROOT}/hooks/`.

## ⚠️ Two findings that exceed packaging (design work, not copy-paste)

1. **Memory-pipeline interpreter provisioning is unsolved for the plugin form.** Canonical runs the pipeline from `${REPO_ROOT}/.claude/.venv/bin/python` with `claude-agent-sdk` installed. The plugin ships **no `.venv`** (correctly — a venv is Class C build noise), so even after fixing `REPO_ROOT` to resolve CODE via `$CLAUDE_PLUGIN_ROOT` and DATA via `$CLAUDE_PROJECT_DIR`, **there is no interpreter to run it.** Provisioning (e.g. `workflow-init` builds a per-project `.claude/.venv`) is an open design decision.
2. **`compile-session.sh` → `skills/memory/compile/scripts/run.py` does not exist *even in canonical*.** The SessionEnd compile invocation dangles at the source of truth, not just in packaging. This is a canonical bug to fix (author `run.py`) or a contract to correct before the pipeline can ship functional.

## Gaps & actions — by severity

### HIGH (16)

| Path | Kind | Action |
|---|---|---|
| `hooks/sdk_memory_pipeline.py` | broken-dependency | Package into plugin `hooks/` AND port path resolution: `REPO_ROOT`/`CLAUDE_ROOT` (lines 42-43) must resolve CODE via `$CLAUDE_PLUGIN_ROOT`, DATA/venv via `$CLAUDE_PROJECT_DIR`; extend the `SDK_MEMORY_REPO_OVERRIDE` branch (line 1052) to the real non-smoke deliver path. |
| `hooks/sdk-memory-pipeline.sh` | broken-dependency | Package + rewrite `REPO_ROOT`/`VENV_PYTHON`/`ENTRY_SCRIPT` (lines 4-6): `ENTRY_SCRIPT` → `$CLAUDE_PLUGIN_ROOT/hooks/...`, interpreter from host project `.venv`, pass `SDK_MEMORY_REPO_OVERRIDE` into the non-smoke run. |
| `hooks/memory-write-guard.sh` | dropped-capability | Package + wire `PreToolUse(Write\|Edit\|MultiEdit)`. Without it, the constitution's "enforced mechanically by memory-write-guard.sh" (asserted by 6 agents + phases.md) is **false**. |
| `hooks/capture-session.sh` | dropped-capability | Package + wire `SubagentStop`/`Stop`/`PreCompact` — the pipeline's sole transcript source. |
| `hooks/_budget_check.py` | dropped-capability | Package as atomic sibling — imported at module-import time (`from _budget_check import SILO_AGENTS`, line 60); missing → `ModuleNotFoundError`. |
| `hooks/_memory_writer.py` | dropped-capability | Package alongside the pipeline (the actual store writer; imports `_budget_check`). |
| `skills/research/claude-code-docs-fetch/SKILL.md` | broken-dependency | Package as `skills/claude-code-docs-fetch/`; add `skills/research/` to repackage hoist; drop `skills/research/*` from EXCLUDED. The shipped `claude-code-docs` agent invokes it on every consultation. |
| `skills/research/claude-code-docs-fetch/links.json` | broken-dependency | Package alongside (seeded docs map; delta detection impossible without it). |
| `skills/memory/compile/SKILL.md` | dropped-capability | Package as `skills/memory-compile/`; drop `skills/memory/*` blanket. Invoked by SessionEnd `compile-session.sh`. |
| `skills/memory/extraction-learnings/SKILL.md` | dropped-capability | Package — the pipeline appends to it each deliver. |
| `skills/memory/jsonl-format/SKILL.md` | dropped-capability | Package — pipeline reads it (lines 191-192) before parsing transcripts. |
| `agents/research/claude-code-docs.md` | broken-dependency | Agent ships faithfully but its sole tool is missing — fixed by shipping the fetch skill above. No change to the agent file. |
| `workflow/sdk-pipeline.md` | dropped-capability | Add to repackage doc loop AND move EXCLUDED→MAPPED. Cited by README/phases/artifacts/communication/migration/orchestrator — every link dead-ends. |
| `constitution.md` | stale-plugin-file | Retire `conditionalize_crux.py` for 0.3.0 — current copy rewrites Rule 5 to "INERT … no writer and no guard hook", the **opposite** of the target. Re-injected every cut, so a one-time edit won't hold. |
| `hooks/hooks.json` | dropped-capability | Wire the 7 missing entries for full parity (memory-write-guard, enforce-budget, lint-on-write, context-budget-check.py, capture-session ×3 events, compile-session, active-status SessionStart). |
| `agents/orchestrator.md` | broken-dependency | Reconcile project-relative invocations: deliver step (l.122) runs `bash .claude/hooks/sdk-memory-pipeline.sh`; step 0 (l.21) calls `.claude/hooks/detect_batch_intent.py` — after relocation these live under `$CLAUDE_PLUGIN_ROOT/hooks/` and the literal paths won't resolve. |

### MEDIUM (selected)

| Path | Kind | Action |
|---|---|---|
| `hooks/load-active.sh` | dropped-capability | Package + wire SessionStart alongside `session-context.sh` — emits active/archived feature-count + phase summary that `session-context.sh` does NOT reproduce. |
| `hooks/context-budget-check.py` | dropped-capability | Package (standalone) + wire `PostToolUse('*')` — the **350K context-occupancy `/compact` warning** (`DEFAULT_THRESHOLD=350000`). |
| `hooks/compile-session.sh` | dropped-capability | Package + wire SessionEnd; body is a placeholder (the `run.py` call is commented) — resolve the `run.py` contract first. |
| `hooks/_session_scope.py` `_actor_map.py` `_phase_ledger.py` `_proposal_schema.py` `_orphan_check.py` `_silo_shape_check.py` | dropped-capability | Package all 6 as atomic siblings of the pipeline (each imported by `sdk_memory_pipeline.py`). |
| `hooks/detect_batch_intent.py` | dropped-capability | Package — orchestrator step-0 batch-intake gate depends on it. |
| `skills/memory/extract/SKILL.md` | dropped-capability | Package as `skills/memory-extract/` (deferred stub, but part of the set). |
| `rules/migrations.md` + `workflow/{README,phases,evaluation,communication,artifacts,migration,routing}.md` | stale-plugin-file | Retire `conditionalize_crux.py` BANNER_TARGETS — injects the false "memory-pipeline plugin not installed" banner into 7 shipped contract docs; also fabricates `sdk-pipeline.md`/guard refs into `evaluation.md` canonical never had. |
| `settings.json` (hook wiring) | dropped-capability | Canonical's 8-hook wiring is the parity source `hooks.json` must mirror (6 truly dropped). |
| `settings.sdk-memory.json` | dropped-capability | Merge its allow-list (`Write/Edit ./.claude/memory/**`, `./.claude/agent-memory/**`, `Bash jq/find/ls/stat/…`) into the `workflow-init` PATCH; drop from EXCLUDED — without it the sole memory writer is denied/prompted on every store write. |
| `agent-memory/` (silo seeding) | judgment-call | Decide a seeder for the 6 actor silos (pipeline `mkdir -p` on first write, or `workflow-init` seeds the dirs). Today neither happens. |
| `compile-session.sh → skills/memory/compile/scripts/run.py` | broken-dependency | **`run.py` doesn't exist even in canonical** — author it or fix the contract. |
| docs → `skills/workflow/<x>/SKILL.md` | stale-plugin-file | Shipped prose references pre-flatten nested skill paths; capability works by registered name but documented `${CLAUDE_PLUGIN_ROOT}` paths 404. |

### LOW (selected)

| Path | Kind | Action |
|---|---|---|
| `hooks/protect-secrets.sh` | stale-plugin-file | Bring the divergent plugin python rewrite under the pipeline (or document the fork) — `repackage.sh` freezes `hooks/`, so canonical edits silently won't propagate. |
| `hooks/enforce-budget.sh`, `hooks/lint-on-write.sh` | dropped-capability | Package + wire `PostToolUse(Write\|Edit\|MultiEdit)`. |
| `workflow/evaluation.md` | stale-plugin-file | Self-heals on next verbatim re-cut (canonical HEAD postdates the package — "permissionMode" → "tool allowlists"). Proof the package was cut from an older canonical revision. |
| `scripts/lib/report_unmapped.py` (nested `.pytest_cache`) | pipeline-misclassified | When de-blanketing `hooks/*`, add `*/.pytest_cache/*` (anchored `.pytest_cache/*` misses `hooks/.pytest_cache/`). |
| `workflow/routing.md` (bundled memory-path rewrite) | stale-plugin-file | `conditionalize_crux` also rewrites the memory index `memory/MEMORY.md` → `~/.claude/projects/<slug>/memory/MEMORY.md` — decide whether to preserve that correction in canonical. |
| `workflow/templates/` (unfiltered `cp -R`) | pipeline-misclassified | Add a stray-file guard — dir is clean today (13 files) but future cruft would copy silently. |

## Broken references (referential-integrity checker)

- **`agents/research/claude-code-docs.md` → `skills/research/claude-code-docs-fetch/{SKILL.md,links.json}`** (HIGH) — shipped registered agent; "you own skills/research/claude-code-docs-fetch/SKILL.md … invoke it on every consultation." Skill absent entirely.
- **`agents/orchestrator.md` deliver step → `hooks/sdk-memory-pipeline.sh`** (HIGH) — runs `bash .claude/hooks/sdk-memory-pipeline.sh`; script not shipped AND project-relative path won't resolve from the plugin. The sole-memory-writer deliver action is a no-op.
- **`agents/orchestrator.md` step 0 → `hooks/detect_batch_intent.py`** (HIGH) — batch-intake gate; module not shipped, path project-relative.
- **`constitution.md` (always-on) → `hooks/memory-write-guard.sh`** (HIGH) — "enforced mechanically by …memory-write-guard.sh"; guard not shipped/wired. Restated by 6 agents + phases.md — all asserting a mechanical block that does not exist.
- **`constitution.md` + `workflow/README.md` (always-on) → `workflow/sdk-pipeline.md`** (HIGH) — named authoritative by 10 shipped docs; not shipped.
- **canonical `settings.json` wiring → plugin `hooks/hooks.json`** (HIGH) — canonical wires 9 hook entries; plugin wires only `protect-secrets.sh` + `session-context.sh`. 7 wirings + all scripts + 8 helper modules absent.
- **`sdk-memory-pipeline.sh` / `sdk_memory_pipeline.py` → `.venv` + `sessions/` + CODE paths on relocation** (HIGH) — `REPO_ROOT='../..'` assumes `<repo>/.claude/hooks/`; relocated to `${CLAUDE_PLUGIN_ROOT}/hooks/` it points at the plugin's parent, not the user's project. Plus no interpreter ships. **Provisioning is unsolved.**
- **`sdk_memory_pipeline.py` → 8 `_*.py` helpers** (HIGH) — bare sibling imports; must ship as one atomic set or every import raises `ModuleNotFoundError`.
- **shipped docs → `skills/workflow/<x>/SKILL.md`** (MEDIUM) — pre-flatten paths; works by name, documented paths 404.
- **`compile-session.sh` → `skills/memory/compile/scripts/run.py`** (MEDIUM) — referenced script absent in canonical.
- **`workflow/README.md` (always-on) → `skills/memory/*` + `skills/research/...`** (MEDIUM) — advertises capabilities the package doesn't contain.

## Fix posture

### Move C→A (must be packaged for the merge)

- `hooks/sdk_memory_pipeline.py`, `hooks/sdk-memory-pipeline.sh`
- `hooks/_*.py` — the 8 helpers (`_budget_check, _memory_writer, _session_scope, _actor_map, _phase_ledger, _proposal_schema, _orphan_check, _silo_shape_check`) — must ship atomically in the same `hooks/` dir
- `hooks/memory-write-guard.sh`, `capture-session.sh`, `compile-session.sh`, `load-active.sh`, `enforce-budget.sh`, `lint-on-write.sh`, `context-budget-check.py`, `detect_batch_intent.py`
- `hooks/protect-secrets.sh` — already shipped; move under the pipeline so it's no longer a frozen, drift-prone Class-B file
- `skills/research/claude-code-docs-fetch/*` (SKILL.md + links.json) — drop `skills/research/*` blanket
- `skills/memory/*` (compile/extract/extraction-learnings/jsonl-format) — drop `skills/memory/*` blanket; hoist/flatten like the workflow skills
- `workflow/sdk-pipeline.md` — add to repackage doc loop AND EXCLUDED→MAPPED
- `settings.sdk-memory.json` — content folds into the `workflow-init` PATCH allow-list

### Narrow reasoned EXCLUDED (replaces the stale blankets) — the gate's allow-list

`hooks/tests/*` · `*/__pycache__/*` · `*.pyc` · `*/.pytest_cache/*` · `.pytest_cache/*` · `.venv/*` · `.DS_Store` · `*/.DS_Store` · `*/.gitignore` · `memory/*` · `agent-memory/*` · `sessions/*` · `retrospectives/*` · `specs/*` · `dynamic-workflows/runs/*` · `rules/_candidates-*.md` · `workflow/queue.md` · `workflow/queue-archive-*.md` · `active.json` · `settings.local.json` · `CLAUDE.md` · `.gitignore`

> **Caveat:** if the shell ships the pipeline's `--smoke` self-test gate, `hooks/tests/fixtures/smoke-corpus` becomes a runtime dependency and must be re-included.

### The systemic hardening (retires this whole class of worry)

Make `report_unmapped.py` a **failing gate**: enumerate 100% of canonical, and **fail the build (non-zero) on any path that is neither MAPPED nor on the explicit reasoned EXCLUDED allow-list.** Unknown ≠ excluded. After this, a file added to canonical can never silently vanish again — it trips the build.

## Judgment calls (genuine product decisions)

1. **`skills/media/image-generator/`** — ship the Gemini media skill into the stack-agnostic shell? No agent/hook references it; target is silent on media.
2. **`rules/backend-go.md`** — ship Go backend rules into stack-agnostic projects (e.g. a Swift project), or gate stack rules off by default? (`rules/_candidates` flags this exact mismatch.)
3. **`rules/frontend-tsx.md`** — same question for TS/React rules.
4. **`agent-memory/` silo seeding** — pipeline `mkdir -p` on first write, or `workflow-init` seeds the 6 dirs at adopt time?
5. **`settings.json permissions.allow`** — do any of canonical's go/npm/git allows belong in the universal shell — specifically read-only git (`status`/`diff`/`log`)?
6. **`hooks/tests/fixtures/smoke-corpus`** — if the shell ships the `--smoke` gate, ship the corpus as a runtime dependency?

## The complete bijective table

Every classified path, grouped by subtree (Path | Bucket | Pipeline belief | Shipped | Gap | Sev | Reason). This is the artifact that proves total coverage.

> _The full per-subtree table is reproduced verbatim from the synthesizer output below._

### hooks/ (subtree: hooks)

| Path | Bucket | Pipeline belief | Shipped | Gap | Sev | Reason |
|---|---|---|---|---|---|---|
| hooks/protect-secrets.sh | A | excluded | yes | yes | low | Shipped+wired security guard, but plugin copy is a divergent python rewrite; repackage freezes hooks/ so canonical edits will drift. |
| hooks/load-active.sh | A | excluded | no | yes | medium | SessionStart active-status summary; canonical-wired. session-context.sh occupies the slot but does NOT reproduce the summary — dropped, not replaced. |
| hooks/memory-write-guard.sh | A | excluded | no | yes | high | PreToolUse guard blocking non-SDK writes to memory silos; constitution+6 agents assert it mechanically. Not shipped, not wired. |
| hooks/enforce-budget.sh | A | excluded | no | yes | low | PostToolUse soft-flag artifact line caps. Canonical-wired; plugin missing. |
| hooks/lint-on-write.sh | A | excluded | no | yes | low | PostToolUse per-ext lint (gofmt/npm). Canonical-wired; plugin missing. |
| hooks/context-budget-check.py | A | excluded | no | yes | medium | 350K context-occupancy /compact warning (PostToolUse *). Standalone. Not shipped/wired. |
| hooks/capture-session.sh | A | excluded | no | yes | high | Pipeline transcript source; wired on SubagentStop/Stop/PreCompact canonical. Plugin wires/ships none. |
| hooks/compile-session.sh | A | excluded | no | yes | medium | SessionEnd compile trigger (currently a placeholder; run.py call commented). Not shipped/wired. |
| hooks/sdk-memory-pipeline.sh | A | excluded | no | yes | high | Pipeline launcher; REPO_ROOT/VENV/ENTRY (../..) break on relocation; override only on smoke path. |
| hooks/sdk_memory_pipeline.py | A | excluded | no | yes | high | Sole memory writer; REPO_ROOT/CLAUDE_ROOT (lines 42-43) break under plugin path; module-level helper import. |
| hooks/_budget_check.py | A | excluded | no | yes | high | Pipeline helper imported at module-import time (line 60); must co-ship atomically. |
| hooks/_memory_writer.py | A | excluded | no | yes | high | The store writer; imports _budget_check; co-ship required. |
| hooks/_session_scope.py | A | excluded | no | yes | medium | Pipeline helper (line 397); co-ship. |
| hooks/_actor_map.py | A | excluded | no | yes | medium | Pipeline helper (398/1375); co-ship. |
| hooks/_phase_ledger.py | A | excluded | no | yes | medium | Pipeline helper (399/1390); co-ship. |
| hooks/_proposal_schema.py | A | excluded | no | yes | medium | Proposal-schema validator (1175/1409, exit 31); co-ship. |
| hooks/_orphan_check.py | A | excluded | no | yes | medium | Orphan/dead-link check (1448, exit 27); co-ship. |
| hooks/_silo_shape_check.py | A | excluded | no | yes | medium | Silo-shape/nested-path check (1429, exit 30); co-ship. |
| hooks/detect_batch_intent.py | A | excluded | no | yes | medium | Standalone batch-intake heuristic; orchestrator step-0 gate depends on it. |
| hooks/tests/ | C | excluded | no | no | none | Pytest suite + fixtures only (ls-confirmed no stray capability). Needs explicit hooks/tests/* once hooks/* blanket is removed. |
| hooks/__pycache__/ | C | excluded | no | no | none | Compiled .pyc build noise; covered by */__pycache__/* + *.pyc. |
| hooks/.pytest_cache/ | C | excluded | no | no | none | pytest run cache; anchored .pytest_cache/* misses nested — add */.pytest_cache/*. |
| hooks/.DS_Store | C | excluded | no | no | none | macOS cruft; */.DS_Store. |
| hooks/hooks.json (plugin-only) | B | n/a | yes | no | none | Intentional-native wiring manifest, but DANGEROUSLY incomplete vs full-parity (wires only protect-secrets + session-context). |
| hooks/session-context.sh (plugin-only) | B | n/a | yes | no | none | Intentional-native SessionStart (injects README+constitution); does NOT cover load-active.sh's status summary. |

### skills/ (subtree: skills)

| Path | Bucket | Pipeline belief | Shipped | Gap | Sev | Reason |
|---|---|---|---|---|---|---|
| skills/workflow/_scripts/_state_common.py | A | mapped | yes | no | none | Hoisted to skills/_scripts/; byte-identical (diff -q). |
| skills/workflow/_scripts/active_json_mutator.py | A | mapped | yes | no | none | Hoisted; identical. |
| skills/workflow/_scripts/state_json_mutator.py | A | mapped | yes | no | none | Hoisted; identical. |
| skills/workflow/_scripts/workflow_phase_next.py | A | mapped | yes | no | none | Hoisted; identical. |
| skills/workflow/_scripts/workflow_state_init.py | A | mapped | yes | no | none | Hoisted; identical. |
| skills/workflow/advance/SKILL.md | A | mapped | yes | no | none | Flattened->workflow-advance; 5 CLAUDE_PLUGIN_ROOT path rewrites verified. |
| skills/workflow/new/SKILL.md | A | mapped | yes | no | none | Flattened->workflow-new; rewrite verified. |
| skills/workflow/rollback/SKILL.md | A | mapped | yes | no | none | Flattened->workflow-rollback; 2 rewrites verified. |
| skills/workflow/rules-review/SKILL.md | A | mapped | yes | no | none | Flattened->workflow-rules-review; diff zero (no script refs). |
| skills/workflow/status/SKILL.md | A | mapped | yes | no | none | Flattened->workflow-status; diff zero. |
| skills/research/claude-code-docs-fetch/SKILL.md | A | excluded | no | yes | high | Shipped claude-code-docs agent's sole tool; EXCLUDED by skills/research/*; broken dependency. |
| skills/research/claude-code-docs-fetch/links.json | A | excluded | no | yes | high | Seeded docs map (required for delta detection); part of same dropped skill. |
| skills/memory/compile/SKILL.md | A | excluded | no | yes | high | memory-compile invoked by SessionEnd compile-session.sh; EXCLUDED by stale skills/memory/*. |
| skills/memory/extract/SKILL.md | A | excluded | no | yes | medium | Deferred stub but part of the memory skill set; EXCLUDED by skills/memory/*. |
| skills/memory/extraction-learnings/SKILL.md | A | excluded | no | yes | high | Pipeline subprocess appends to it each deliver; EXCLUDED by skills/memory/*. |
| skills/memory/jsonl-format/SKILL.md | A | excluded | no | yes | high | Pipeline reads it before parsing transcripts; EXCLUDED by skills/memory/*. |
| skills/media/image-generator/SKILL.md | judgment | excluded | no | yes | low | Gemini media skill; no agent/hook references it; product decision. |
| skills/media/image-generator/scripts/generate.py | judgment | excluded | no | yes | low | CLI entrypoint; bound to media decision. |
| skills/media/image-generator/scripts/_gemini_client.py | judgment | excluded | no | yes | low | Gemini client helper; bound to media decision. |
| skills/.DS_Store | C | excluded | no | no | none | macOS cruft; */.DS_Store. |
| skills/workflow/_scripts/__pycache__/ | C | excluded | no | no | none | Build noise; */__pycache__/* + *.pyc. |
| skills/media/image-generator/scripts/__pycache__/ | C | excluded | no | no | none | Build noise; */__pycache__/* + *.pyc. |

### contract: agents/ rules/ dynamic-workflows/ (subtree: contract)

| Path | Bucket | Pipeline belief | Shipped | Gap | Sev | Reason |
|---|---|---|---|---|---|---|
| agents/_template.md | A | mapped | yes | no | none | Relocated to templates/agent-template.md; byte-identical. |
| agents/orchestrator.md | A | mapped | yes | no | none | Preamble-transform faithful. (Carries broken downstream deps: research skill, sdk-memory-pipeline.sh, detect_batch_intent.py — tracked as their own gaps.) |
| agents/engineering/backend-engineer.md | A | mapped | yes | no | none | Faithful; native tools only. |
| agents/engineering/frontend-engineer.md | A | mapped | yes | no | none | Faithful; native tools only. |
| agents/engineering/task-decomposer.md | A | mapped | yes | no | none | Faithful; wired workflow-advance ships. |
| agents/ops/git-engineer.md | A | mapped | yes | no | none | Faithful; native tools only. |
| agents/planning/architect.md | A | mapped | yes | no | none | Faithful; native tools only. |
| agents/product/product-manager.md | A | mapped | yes | no | none | Faithful; wired workflow-advance ships. |
| agents/product/requirement-analyzer.md | A | mapped | yes | no | none | Faithful; native tools only. |
| agents/research/claude-code-docs.md | A | mapped | yes | yes | high | Ships faithfully but its declared sole tool (claude-code-docs-fetch skill) is not packaged — capability inert. |
| agents/review/cross-checker.md | A | mapped | yes | no | none | Faithful; native tools only. |
| agents/review/plan-verifier.md | A | mapped | yes | no | none | Faithful; bypassPermissions read-only. |
| agents/review/qa-engineer.md | A | mapped | yes | no | none | Faithful; empty skills[]. |
| agents/review/spec-verifier.md | A | mapped | yes | no | none | Faithful; read-only verifier. |
| agents/review/task-verifier.md | A | mapped | yes | no | none | Faithful; read-only verifier. |
| agents/.DS_Store | C | excluded | no | no | none | macOS cruft; */.DS_Store. |
| rules/general.md | A | mapped | yes | no | none | Allow-list copy; byte-identical. |
| rules/claude-code.md | A | mapped | yes | no | none | Allow-list copy; byte-identical. |
| rules/tests.md | A | mapped | yes | no | none | Allow-list copy; byte-identical. |
| rules/migrations.md | A | mapped | yes | yes | medium | Shipped but conditionalize_crux INLINE rewrite asserts a non-existent memory-plugin split; false for merged target. |
| rules/backend-go.md | judgment | mapped | yes | no | low | Ships via INCLUDE_STACK_RULES; Go rules in a stack-agnostic shell is a product call. |
| rules/frontend-tsx.md | judgment | mapped | yes | no | low | Ships via INCLUDE_STACK_RULES; TS/React rules in a stack-agnostic shell is a product call. |
| rules/_candidates-2026-06-11.md | C | excluded | no | no | none | Per-project rules-review output; rules/_candidates-*.md. |
| dynamic-workflows/shell-audit.md | A | mapped | yes | no | none | Verbatim copy; byte-identical; untouched by conditionalize_crux. |
| dynamic-workflows/runs/20260617-shell-audit-run.md | C | excluded | no | no | none | Per-project run log (65KB transcript); dynamic-workflows/runs/*. |
| dynamic-workflows/.DS_Store | C | excluded | no | no | none | macOS cruft; */.DS_Store. |
| output-styles/workflow-orchestrator.md (plugin-only) | B | n/a | yes | no | low | Intentional-native delivery mechanism (no canonical source); CAVEAT: lines 62-64 hard-code the stale crux-only split — hand-edit at 0.3.0. |

### workflow/ docs + templates (subtree: workflow-docs)

| Path | Bucket | Pipeline belief | Shipped | Gap | Sev | Reason |
|---|---|---|---|---|---|---|
| workflow/sdk-pipeline.md | A | excluded | no | yes | high | Authoritative pipeline contract cited by 9 shipped docs; EXCLUDED + omitted from repackage doc loop. |
| workflow/README.md | A | mapped | yes | yes | medium | Shipped but conditionalize_crux injects the false crux-only banner; also advertises unshipped memory/research skills. |
| workflow/phases.md | A | mapped | yes | yes | medium | Shipped; false crux banner; references mechanical guard that does not ship. |
| workflow/routing.md | A | mapped | yes | yes | medium | Shipped; INLINE crux caveat + bundled memory-path rewrite (memory/MEMORY.md -> ~/.claude/projects/<slug>/...). |
| workflow/artifacts.md | A | mapped | yes | yes | medium | Shipped; false crux banner. |
| workflow/communication.md | A | mapped | yes | yes | medium | Shipped; false crux banner. |
| workflow/migration.md | A | mapped | yes | yes | medium | Shipped; false crux banner. |
| workflow/evaluation.md | A | mapped | yes | yes | medium | Shipped; false crux banner (fabricates sdk-pipeline/guard refs) + stale 'permissionMode (default)' wording (canonical HEAD = 'tool allowlists', self-heals on re-cut). |
| workflow/templates/ (13 files incl state.json) | A | mapped | yes | no | none | cp -R whole dir; diff -rq clean (13/13 identical). Latent risk: unfiltered copy would ship future stray files. |
| workflow/queue.md | C | excluded | no | no | none | Per-project hand-edited backlog; workflow-init seeds blank. |
| workflow/queue-archive-2026-06-15.md | C | excluded | no | no | none | Per-project frozen queue history. |
| workflow/.DS_Store | C | excluded | no | no | none | macOS cruft; */.DS_Store. |

### top level (subtree: toplevel)

| Path | Bucket | Pipeline belief | Shipped | Gap | Sev | Reason |
|---|---|---|---|---|---|---|
| constitution.md | A | mapped | yes | yes | high | Shipped but conditionalize_crux inserts crux-only banner + rewrites Rule 5 to 'INERT'; opposite of full-parity target; re-injected every cut. |
| settings.json | A | excluded | no | yes | medium | Content Class-A in two destinations; canonical 8-hook wiring is the parity source — 6 hooks dropped vs plugin hooks.json. Also drops permissions.allow (judgment). |
| settings.sdk-memory.json | A | excluded | no | yes | medium | Memory allow-list (the SDK writer's permission to write the stores) not folded into init PATCH; blanket-EXCLUDED. |
| CLAUDE.md | C | excluded | no | no | none | Per-project manifest; workflow-init seeds a fresh template. |
| active.json | C | excluded | no | no | none | Per-project state; init seeds empty. |
| settings.local.json | C | excluded | no | no | none | Personal gitignored overrides. |
| memory/ | C | excluded | no | no | none | Per-project memory DATA (MEMORY.md, 71 topics); written by Class-A pipeline; no stray capability. |
| agent-memory/ | C | excluded | no | no | none | Per-project DATA; 6 empty actor silos + .DS_Store; no capability file. |
| agent-memory/ (silo seeding) | judgment | excluded | n/a | yes | medium | No plugin mechanism seeds the 6 silos; decide pipeline mkdir-on-write vs workflow-init seeding. |
| sessions/ | C | excluded | no | no | none | Local gitignored capture DATA; writer code is Class A in hooks. |
| retrospectives/ | C | excluded | no | no | none | Per-project narrative DATA (20 retros + INDEX). |
| specs/ | C | excluded | no | no | none | Per-project spec artifacts (state/spec/tasks + per-spec probes/fixtures under 015/020/024); '*' spans '/'. |
| .gitignore | C | excluded | no | no | none | Per-project ignore file. |
| .DS_Store | C | excluded | no | no | none | macOS cruft. |
| .pytest_cache/ | C | excluded | no | no | none | Test-suite build noise; .pytest_cache/*. |
| .venv/ | C | excluded | no | no | none | Python virtualenv build noise; .venv/*. |

### cross-cutting / pipeline (newFindings)

| Path | Bucket | Pipeline belief | Shipped | Gap | Sev | Reason |
|---|---|---|---|---|---|---|
| scripts/lib/report_unmapped.py (nested .pytest_cache) | C-pattern | n/a | n/a | yes | low | Anchored '.pytest_cache/*' misses nested hooks/.pytest_cache/*; add '*/.pytest_cache/*' when de-blanketing hooks/*. |
| hooks/compile-session.sh -> skills/memory/compile/scripts/run.py | A | excluded | no | yes | medium | run.py does not exist even in canonical; SessionEnd compile step dangles pre-relocation. |
| docs -> skills/workflow/<x>/SKILL.md (nested paths) | A | mapped | yes | yes | medium | Shipped prose references the pre-flatten nested skill paths; capability works by name but documented ${CLAUDE_PLUGIN_ROOT} paths 404. |

---

## Resolution — stabilize phase (2026-06-28, workflow-shell 0.3.0, uncommitted)

**Landed (the systemic fix + design-free gaps):**
- `report_unmapped.py` is now a **failing gate** (`--strict`), run by `repackage.sh` before any plugin mutation. `EXCLUDED` de-blanketed into narrow reasoned patterns; `MAPPED` enumerates the new Class-A. Gate green (0 unmapped). **Unknown ≠ excluded, mechanically.**
- `conditionalize_crux.py` **deleted**; constitution + 7 contract docs revert to canonical (unconditional Rule 5). Also fixed `agent-preamble.md` (injected into all 14 agents) which carried the same crux falsehood — the audit's banner scan missed it. **Zero crux residue package-wide.**
- Shipped the dropped capabilities: `workflow/sdk-pipeline.md`, the `claude-code-docs-fetch` skill (broken-agent fix), the 4 memory skills, the full hook surface (19 files + 8 helpers) merged into a **hybrid** `hooks/` (canonical files merged, plugin-native `hooks.json`/`session-context.sh`/`protect-secrets.sh` fork preserved; orphan-prune self-heals deletions).
- `hooks.json` wires **full canonical parity** (7 events). `jq` documented as a prerequisite (the memory/advisory hooks parse stdin with it; `protect-secrets.sh` + the injector are python3-only).
- Bumped to 0.3.0; de-listed `workflow-memory-pipeline` from the marketplace.

**Adversarial review (9 agents, fix-then-ship): 8 findings confirmed / 1 refuted.** Fixed: preamble false "wired via hooks.json" (#3); `protect-secrets.sh` MAPPED→EXCLUDED so the fork drift isn't masked (#6); `hooks/` orphan-prune + gate-scope docstring (#5); README jq prereq + deliver-time caveat (#1 doc / #4). Accepted as-is per user (jq installed manually, full wiring kept) — which makes the constitution's "mechanically guarded" claim **true** this release (guard is wired).

**Deferred to the memory-runtime step (explicit user decision):**
- Port `sdk_memory_pipeline.py` + `sdk-memory-pipeline.sh` `REPO_ROOT` (`../..` → resolve CODE via `$CLAUDE_PLUGIN_ROOT`, DATA/venv via `$CLAUDE_PROJECT_DIR`); these ship **inert** (not wired as settings hooks).
- Interpreter provisioning (`.venv` + `claude-agent-sdk`) — likely `workflow-init` builds a per-project venv.
- Author the missing `skills/memory/compile/scripts/run.py` (dangles even in canonical).
- Reconcile `orchestrator.md` deliver step (`bash .claude/hooks/sdk-memory-pipeline.sh`) + step-0 `detect_batch_intent.py` to the plugin path.
- Fold `settings.sdk-memory.json` allow-list into the `/workflow-init` PATCH; seed `memory/` + `agent-memory/` silos.
- **From the review:** make `memory-write-guard.sh` fail-**closed** if `jq` absent, and **anchor** its `\.claude/projects/[^/]+/memory/` regex to the project (avoid colliding with home `~/.claude` auto-memory) — do both when porting the guard.

**Known latent (low):** `MAPPED` glob `skills/workflow/_scripts/*.py` is broader than repackage's non-recursive copy — a future nested `_scripts` helper would classify MAPPED yet not stage (#7). No current instance; harden with a staged-vs-classified reconciliation when convenient.
