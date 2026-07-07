# SDK memory pipeline — contract

The single authoritative contract for the `claude-agent-sdk` subprocess that
updates project memory at every `deliver`. This is an orchestrator/verifier
contract — a sibling of `phases.md` and `artifacts.md`, not a model-discovered
skill. It SUPERSEDES the scattered description previously split across
`specs/012-workflow-contract-v2/design/03-sdk-memory-pipeline.md` and the earlier
mirror ripple (Constitution Rule 7: one source of truth).

Runtime code: `.claude/hooks/sdk-memory-pipeline.sh` (launcher) +
`.claude/hooks/sdk_memory_pipeline.py` (entry) + the pure helpers
`_proposal_schema.py` (proposal validator), `_memory_writer.py` (deterministic
writer), `_orphan_check.py`, `_budget_check.py`, `_silo_shape_check.py`.

## Architecture: propose → write (spec 038)

The pipeline is split into two halves so that file writes are DETERMINISTIC and
leak-proof, not LLM-driven (the 035/036 lesson: a live LLM that both reads
everything AND writes every file is slow, unbounded, and leak-prone):

1. **LLM half — ONE bounded read-once pass.** The entry issues a SINGLE SDK
   `query()` whose `allowed_tools` are **Read / Glob / Grep ONLY** (no Write /
   Edit). The agent reads the just-completed spec + session transcript + existing
   memory ONCE and EMITS a single structured **proposal** object — which
   decisions, project topics, per-agent-silo entries, and shared topics to record.
   It writes ZERO files: structurally, the LLM half has no write tool.

2. **Deterministic writer — `_memory_writer.write_proposal`.** A pure-ish Python
   step consumes the proposal and OWNS every written path, the `MEMORY.md`
   index-line shape, the per-store **TRUNCATING CAP** (writes the first N per
   store, drops + logs the excess), the canonical-vs-repo split, and personal-line
   filtering. Same proposal in → byte-identical files out. This is in-process
   Python invoked by the SDK-actor subprocess — NOT a Write/Edit tool call — so the
   SDK actor remains the **sole memory writer** (Constitution Rule 5;
   `memory-write-guard.sh` does not intercept it).

The proposal is schema-validated by the pure `_proposal_schema.validate_proposal`
BEFORE the writer sees it (exit 31 on any STRUCTURAL violation — missing keys,
wrong types, a nested `/` in a slug; an unresolved silo `topic_slug` is NOT
structural — it is a recoverable writer-drop, see "Proposal schema" and the
exit-code table). This is the same
propose/validate split the validation helpers already use, moved UPSTREAM from
"LLM writes then mechanically check" to "LLM proposes then mechanically write" —
so the silo→repo leak and the mirror personal-line leak are STRUCTURALLY
impossible (the writer has no code path that targets a repo-side silo path, and it
filters personal entries before mirroring) rather than asserted-after.

## Trigger

The LAST step of every `deliver` phase (every workflow type). The orchestrator
spawns the launcher; the subprocess runs against the just-completed spec. Memory
updates are **best-effort** — a launcher failure does NOT block deliver
completion (the orchestrator logs the exit code and a one-line warning).

NOT triggered by `/compact`, `PreCompact`, `SessionEnd`, or any other event.

## Identity

- Engine: `claude-agent-sdk`, OAuth-only (`CLAUDE_CODE_OAUTH_TOKEN`; spec 026).
- Model: `opus` (env override `SDK_MEMORY_MODEL`). The 035 timeout was workload
  volume, not model access — `haiku` is NOT specced as a fallback.
- `max_turns`: 100 (env override `SDK_MEMORY_MAX_TURNS`).
- Proposal-pass tool allowlist: **Read / Glob / Grep** only (no Write/Edit).
- The subprocess runs from the repo **ROOT** with absolute paths (see "cwd" below).

## Stores the pipeline writes

There are four memory stores. `<project-slug>` is the cwd with `/` rewritten to
`-` (e.g. `-Users-rohitseelam-Projects-scratchpad-priv`).

| Store | Canonical path | Repo mirror | Mirrored? |
|---|---|---|---|
| Outer project memory | `~/.claude/projects/<project-slug>/memory/` | `<repo>/.claude/memory/` | YES (selective) |
| Per-agent silos | `~/.claude/projects/<project-slug>/memory/agent-memory/<agent>/MEMORY.md` | — | NO (canonical-only) |
| Shared cross-agent topics | `~/.claude/projects/<project-slug>/memory/agent-memory/topics/<slug>.md` | — | NO (canonical-only) |

- **Outer memory** = `MEMORY.md` index + `topics/*.md` bodies. The deterministic
  writer writes the CANONICAL store, then a mechanical in-process `shutil` mirror
  (`_mirror_canonical_to_repo`, folded into the writer step) copies the
  **non-personal subset** into the repo. Personal-profile entries (role,
  communication style, personal feedback/preferences — `_PERSONAL_EXCLUDE`) are
  canonical-only and never committed, excluded as both FILES **and** `MEMORY.md`
  INDEX LINES (spec 038 M5 closed the 036 gap where the file was dropped but its
  dead index line was mirrored through). The mirror is root-locked to the outer
  `memory/` store AND, source-agnostic, SKIPS any individual source path whose
  parts contain `agent-memory` — so a nested `memory/agent-memory/` (the spec 038
  leak, where a malformed silo path landed UNDER the mirrored `memory/` root and
  was copied through despite the root lock) can no longer be mirrored. The skip is
  per-path, not per-root, so it holds wherever `agent-memory` appears in the tree.
- **Silos** are ACTIVE for the 6 agents carrying `memory: project` frontmatter
  (`product-manager`, `architect`, `backend-engineer`, `task-decomposer`,
  `qa-engineer`, `cross-checker`; `frontend-engineer` dormant since spec 047).
  The canonical list is `_budget_check.SILO_AGENTS`. Each agent folder holds
  ONLY `MEMORY.md`. There is NEVER a nested `agent-memory/<agent>/topics/` path —
  all topic bodies live at the ROOT shared store and are referenced (not
  duplicated) from each relevant silo index. The writer constructs ONLY canonical
  silo paths.

The authoritative classification of what is mirrored vs canonical-only lives in
`workflow/artifacts.md` "Selective mirror policy"; this doc references it, does
not restate it.

## Proposal schema

The LLM half emits a single JSON object (the writer consumes ONLY this):

```json
{
  "decisions":      [{"title", "hook", "body"}],
  "project_topics": [{"slug", "title", "hook", "body", "append"}],
  "silos":          {"<agent>": [{"title", "topic_slug", "hook"}]},
  "shared_topics":  [{"slug", "title", "hook", "body"}]
}
```

`silos` keys SHOULD be in the 6-agent set (`_budget_check.SILO_AGENTS`); an unknown
key is a recoverable writer-drop, not a hard failure (spec 047 AC-4). Each silo entry's `topic_slug` MUST be a
BARE slug (no `/`) referencing a ROOT `agent-memory/topics/<slug>.md`. A silo
`topic_slug` resolves ONLY against an existing `agent-memory/topics/` slug OR a
`shared_topics[]` slug emitted in the SAME proposal — NEVER against an outer
`memory/topics/*.md` slug. These are two DISTINCT pools; the proposer prompt names
both namespaces explicitly and surfaces the silo-resolvable `agent-memory/topics/`
slug-set as a positive enumerated signal (spec 042) so the LLM does not conflate
them.

The pure `_proposal_schema.validate_proposal` gates the object → exit **31** on
any STRUCTURAL violation (missing keys, wrong types, a non-dict entry, a nested
`/` in a slug; a missing/malformed proposal is treated the same). An *unresolved*
silo `topic_slug` is NOT a structural violation — it is a recoverable writer-drop
(see the exit-code table below), not exit 31.

## Per-deliver write budget (TRUNCATING cap at write time)

The pipeline produces a **bounded, predictable** set of files — a curated
decision log, not a transcript. 035 wrote ~100 files for one spec; the budget
caps that. The writer enforces each per-store cap as a **TRUNCATING ceiling at
write time** (user decision 2026-06-01): it writes the first N (= the cap) entries
per store, **DROPS the excess**, and **LOGS** exactly which entries were dropped (a
`writer-cap: truncated <store> to N; dropped: <titles>` line per truncated store —
Constitution Rule 2: surfaced, never silent). Truncation is a **normal bounded
write — the run exits 0**, it is not a failure. The cap numbers are unchanged; the
writer truncates rather than raises. (The prior exit-32 ABORT and the 036 post-run
budget check / exit 29 are both retired.)

The proposal prompt carries these same per-store budget numbers (single-sourced
from `_budget_check`) and instructs the model to propose **within budget,
most-important-first per store**, so the only entries ever dropped are the
least-important tail.

**Depth rule — append over create.** When a durable note belongs to an existing
topic/silo surface, the proposal sets `append: true` so the writer extends that
surface rather than creating a new file: one durable decision per surface.

**Per-store limits (exact, reused from `_budget_check`):**

| Store | Limit per deliver |
|---|---|
| `memory/topics/decisions.md` | ≤ 1 new entry |
| project spec-topics (new `memory/topics/*.md` other than `decisions.md`) | ≤ 2 |
| each WORKED-agent silo (`agent-memory/<agent>/`) | ≤ 1 new craft-note |
| a silo for an agent that did NOT work the spec | 0 |
| shared `agent-memory/topics/` | ≤ 1 new note |
| **total touches** | **≤ 12** |

"Worked agents" is resolved **deterministically** from the spec's phase ledger
(`_phase_ledger` → `_budget_check.resolve_worked_agents`, phase→agent map), NOT by
LLM judgement: an agent is "worked" iff a phase it owns appears in
`state.json.phase_history`. A non-worked agent's silo cap is 0, so any silo entry
proposed for it is dropped + logged (the conservative default for an unresolved
ledger is likewise 0 silo writes).

## Post-write guards

The deterministic writer makes most failure modes structurally impossible; these
belt-and-suspenders guards run AFTER the write and surface a distinct non-zero
exit (never swallowed — Constitution Rule 2). One exception since spec 055: the
topic-slug recurrence check also runs a **pre-write** primary layer (see its
bullet), so it is not post-write-only:

- **Silo-shape** (`_silo_shape_check.py`) → exit **30** on any nested
  `agent-memory/<agent>/topics/` path (on-disk scan).
- **Topic-slug recurrence** (`run_topic_guard`) → exit **26** on cross-spec slug
  drift. Since spec 055 this is the post-write **backstop**: the primary check
  runs PRE-write (`_prewrite_cross_spec_disposition`, same exit **26**) and
  rejects a bare cross-spec `project_topics` slug from the proposal's INTENT with
  **nothing written**, so a clobber is now prevented rather than detected only
  after the destructive overwrite has landed. An `append:true` closure note stays
  advisory at both sites.
- **Repo-side silo leak** (`_assert_no_repo_silo_leak`) → exit **33**: any `.md`
  under `<repo>/.claude/agent-memory/` or a malformed nested
  `<repo>/.claude/memory/agent-memory/` FAILS the run (silos are canonical-only).
  (Empty placeholder silo dirs auto-created by Claude Code frontmatter are
  benign; the scan keys on `.md` CONTENT, not bare directory existence.) This
  check runs BEFORE the orphan/dead-link check, matching `_run`'s order — a
  leaked silo file is a structural fault that should surface ahead of a
  link-integrity finding.
- **Orphan / dead-link** (`_orphan_check.py`) → exit **27**, run over BOTH outer
  `memory/` stores AND the silo stores (each silo index's `topics/` links resolve
  against the ROOT shared store).
- **No nested `.claude`** (`_assert_no_nested_claude`) → exit **30**: after the
  run, no `.claude/.claude/` or `.claude/hooks/.claude/` dir may exist.

## cwd

The launcher `cd`s to the repo ROOT before invoking the entry script. The Python
entry derives `project_slug` from `os.getcwd()` and the SDK uses cwd as its
working dir; running from `.claude/hooks/` (the hook's default cwd) both broke the
slug AND scaffolded nested `.claude/.claude/` / `.claude/hooks/.claude/` dirs
(035). A post-run assertion verifies no nested `.claude` dir remains.

## Timeout model

**WHOLE-RUN wall-clock budget**, NOT a per-attempt or per-segment watchdog. The
propose→write flow is ONE read-once pass + a deterministic write — there is
nothing to re-run per segment. A SINGLE background watchdog is armed ONCE in the
launcher around the whole `invoke_subprocess` and records one deadline at
`start + SDK_MEMORY_TIMEOUT` (default **600s**), sending TERM then KILL to the
Python PID tree on expiry. This replaces the 036 per-attempt watchdog that
re-armed each retry (per-attempt × 4 attempts ≈ 80-min path) and is macOS-safe
(no `timeout(1)` dependency). A timeout maps to exit **22** and is NOT
whole-pipeline-retried.

## Retry policy

Only transient network/rate-limit outcomes retry: **20** (rate-limit) and **21**
(network) retry once each. Every other outcome is terminal — a deterministic
failure (24/25/26/27/30/31/33) would re-produce the same result on a re-run, and a
timeout (22) would burn the whole-run budget. The 036 exit-28 whole-run retry
storm is ABANDONED (there are no segments to re-run).

## Exit codes

The complete set the launcher can emit (`emit_exit_message`). Codes marked
**terminal** are NOT retried by `invoke_subprocess`.

| Code | Meaning | Terminal? |
|---|---|---|
| 0 | success | — |
| 2 | prior run still active (live lock) | terminal |
| 10 | `CLAUDE_CODE_OAUTH_TOKEN` not set | terminal |
| 11 | `claude-agent-sdk` not installed | terminal |
| 12 | venv Python < 3.10 | terminal |
| 13 | `jq` missing | terminal |
| 14 | venv missing | terminal |
| 20 | rate-limited (429) | retried |
| 21 | network / connection failure | retried |
| 22 | whole-run wall-clock timeout | terminal |
| 23 | mirror write failed | terminal |
| 24 | hit `max_turns` ceiling | terminal |
| 25 | `CLAUDE_SESSION_ID` empty (unscoped input) | terminal |
| 26 | topic-slug recurrence: genuine cross-spec drift → **terminal**; an `append:true` closure note to an existing topic → **advisory WARN (exit 0, already written)** | SPLIT (spec 047 AC-5) |
| 27 | orphan / dead-link check failed | terminal |
| 30 | silo-shape / nested-`.claude` violation | terminal |
| **31** | **proposal STRUCTURAL schema-validation failed** (LLM half: missing keys, wrong types, non-dict entry, nested `/` in a slug) | **terminal** |
| **33** | **post-run repo-side silo leak** | **terminal** |
| **34** | **smoke-only all-store assertion failed** (proposal omitted a silo entry or a shared_topic) | **terminal** |
| **35** | **post-write silo landing absent** (writer reported a silo path not present at the auto-load location) | **terminal** |

Exit **31** is reserved for STRUCTURAL invalidity only (spec 042). An *unresolved*
silo `topic_slug` — a well-formed bare slug with no backing shared-topic body in
this proposal nor on disk — is NOT a structural failure: it is a recoverable
**writer-drop** (the writer's `_drop_dead_silo_lines` drops that one silo index
line with a `writer-dead-link:` WARN and writes the rest of the proposal). This
preserves spec 041's "no silo dead link ever reaches disk" guarantee while keeping
the good content that rode alongside the slip, rather than discarding the whole
proposal at exit 31.

Exit **34** fires ONLY under `--smoke` (`SDK_MEMORY_SMOKE=1`): the smoke proposal
must walk EVERY store, so a missing silo entry or shared_topic fails the gate. A
real deliver — whose proposal legitimately may omit a store — never runs the
assertion (anti-over-gating).

Exit **28** (the old chunk-fail), **29** (the old post-run budget cap), and **32**
(the old writer-cap ABORT) are RETIRED. The chunk-fail and segment retry are gone
with the propose→write pivot; the budget is now a TRUNCATING cap (write top-N,
drop + log the excess, exit 0), so there is no over-budget failure code at all.

## Lock discipline

The launcher holds `.claude/sessions/.sdk-memory.lock` for the run duration. A
`trap release_lock EXIT TERM INT HUP` releases it on normal exit or a signalled
kill (including the whole-run watchdog's TERM). A SIGKILL cannot be trapped, so
the next run's `acquire_lock` checks the owner PID's liveness (`kill -0`): a
dead-PID lock is **overridden** with a clear message; a live-PID lock skips with
exit 2.

## Pre-deliver real-run smoke gate

No SDK-pipeline behaviour AC is declared met on `tmp_path` unit evidence alone —
035's 170 green units gave false confidence; every real failure lived in
live-LLM/launcher behaviour the units never exercised. The launcher's `--smoke`
mode runs the REAL launcher + live LLM against a committed scratch corpus
(`hooks/tests/fixtures/smoke-corpus/`) into a **tmp** canonical dir + tmp repo
root (NEVER the real store). It is self-contained: a synthetic session transcript
(`smoke-corpus/session/smoke-900-session.jsonl`) grounded in the trivial 900-smoke
corpus is pointed at via `SDK_MEMORY_SESSION_OVERRIDE`, so the proposal pass never
reads the real live session.

The smoke gate validates the **write path** end to end: read-once propose →
schema-validate (31) → deterministic write → truncating cap → and the post-write
repo-silo-leak (33), no-nested-`.claude` (30), and orphan/dead-link (27) checks
against the tmp tree, plus the "writer wrote N files" success path. It does NOT
run the **cross-spec topic-slug recurrence guard** (exit 26): that guard is
inherently a real-deliver-only check — a synthetic-spec run inside the real repo
cannot avoid reading the real repo's workflow docs, so the live LLM proposes a
topic slug for the REAL in-flight spec, which the guard would (correctly, for a
real deliver) flag as cross-spec drift. The `--smoke` mode sets `SDK_MEMORY_SMOKE=1`,
which gates OUT that cross-spec recurrence check — both its pre-write
(`_prewrite_cross_spec_disposition`) and post-write (`run_topic_guard`) layers
since spec 055 (each skip is logged, not silent); the check remains fully active
for every real deliver.

**The smoke proposal ALWAYS walks every store.** The 038 lesson: a green smoke
that exercised no silo and no shared_topic never touched the agent-memory write
path, so it could not catch agent-memory bugs. The seeded corpus names a worked
agent + a cross-agent lesson, and a smoke-only post-proposal assertion
(`_assert_smoke_all_store`, gated on `SDK_MEMORY_SMOKE=1`) FAILS the gate (exit
**34**) unless the parsed proposal carries ≥1 silo ENTRY AND ≥1 shared_topic. The
on-disk write path then walks every store — outer `memory/` plus each silo and the
shared `agent-memory/topics/` store — so the agent-memory write path is exercised
end to end on every smoke run.

The orchestrator runs `sdk-memory-pipeline.sh --smoke` at the `verify→deliver`
gate, BEFORE the deliver commit; a non-zero smoke exit blocks the gate.

## Programmatic spend capture

Every run records its cost/token spend to gitignored markers under
`.claude/sessions/sdk-memory/` (the `LOG_DIR`), so "what did the last run cost?" is
a one-file read instead of a log-hunt. The capture is split across the two halves,
because only the Python entry holds the SDK `ResultMessage`:

1. **Python writes a cost sidecar.** On the `ResultMessage`, the entry writes
   `_last-run-cost.json` — `{cost_usd, tokens_in, tokens_out, model}` — from
   `total_cost_usd` + the `usage` mapping. A missing field is recorded as `null`
   (recorded-as-absent, Rule 2). The write is best-effort: a sidecar failure is
   logged, never fatal.
2. **The launcher composes the per-run marker.** On EVERY terminal exit, the
   launcher's `compose_last_run` writes `_last-run.json` with exactly **7 fields**:
   `exit_code`, `duration_s`, `cost_usd`, `tokens_in`, `tokens_out`, `model`,
   `timestamp`. It merges the sidecar's cost/token half with the launcher-known
   fields; when no sidecar exists (a pre-LLM terminal exit 10–14 never reached
   Python's `ResultMessage` handler), the cost/token fields are written as `null`.
3. **The launcher rolls up cumulative spend.** A read-add-write merge folds each
   `_last-run.json` into `_spend-total.json` (cumulative cost + tokens across
   runs).

All three files live under the already-gitignored `.claude/sessions/`, so the
markers are never committed. Under `--smoke`, `LOG_DIR` points at the tmp tree, so
smoke runs never touch the real markers.
