# Workflow-shell marketplace — drift investigation (2026-06-19)

**Subject:** the `workflow-shell` plugin package (v0.1.0) vs the canonical contract (`scratchpad-priv/.claude`, HEAD spec 053 / 2026-06-19), and the state of ~13 surveyed projects that do or should adopt it.  
**Method:** Phase-0 inventory of the marketplace package + per-project `.claude/` audits, lensed through a four-drift model (temporal / adoption / internal-truth / design-gap).  
**Output:** confirmed findings, root-cause failure classes, and four implementation-ready deliverables plus a recommended execution order. The reserved `workflow-memory-pipeline` plugin is intentionally left untouched throughout.

## Contents

1. Executive summary
2. The drift model and the version-stamp scheme
3. Confirmed findings
4. Failure classes (shared root cause)
5. Deliverable 1 — `/workflow-init` hardening (idempotent patches)
6. Deliverable 2 — `workflow-refresh` plugin spec (project↔plugin drift reconciler)
7. Deliverable 3 — repackage / version-stamp spec (canonical→plugin re-sync)
8. Deliverable 4 — contract-patch list (crux-only truth fixes)
9. Recommended execution order

---

## 1. Executive summary

- **The plugin is a frozen, un-stamped snapshot of canonical that has already drifted.** `workflow-shell` v0.1.0 was hand-cut from the canonical contract (`scratchpad-priv/.claude`) circa **2026-06-17** (~spec 051) and never re-synced; canonical has since advanced to HEAD **spec 053 (2026-06-19)** and lands roughly 19 `.claude/` commits per week. No field anywhere records which canonical commit the package was cut from, so the gap is **structurally invisible** — you cannot tell the plugin is stale without manually diffing two repos.

- **Two temporal regressions already shipped.** The three Haiku review verifiers (`spec/plan/task-verifier.md`) carry `permissionMode: default` — the exact bug spec 053 (2026-06-19) fixed by switching to `bypassPermissions` — so the packaged verifiers stall on per-call permission prompts during autonomous verification (F0-4, confirmed). Spec 052's `dynamic-workflows/shell-audit.md` (2026-06-18) is absent entirely (F0-5), and the stack rules `backend-go.md`/`frontend-tsx.md` were dropped while the shipped agents still assume Go/pytest/React (F0-7, confirmed).

- **Secrets protection is the single largest failure surface (12 findings).** Canonical's `protect-secrets.sh` PreToolUse guard — which blocks (exit 2) `.env*`/credentials/service-account/SSH-keys for **both** file tools **and** Bash commands — was dropped from the package. The only remaining mechanism is the `settings.json` deny-list, and it is structurally weak everywhere: the seeded baseline is narrow (no SSH keys, `*.pem`, `*.key`, tokens, nested `**/.env`), it cannot gate Bash-arg reads (`cat .env` bypasses it), it frequently lives only in the un-committed `settings.local.json`, and in un-adopted projects it is missing entirely — leaving real `.env` files (`YOUTUBE_API_KEY`, `PERPLEXITY_API_KEY`) fully exposed to tool calls.

- **The shipped docs assert a memory pipeline that the crux does not contain (11 findings).** `constitution.md` Rule 5 and the `workflow/` docs unconditionally state that an SDK memory pipeline is the SOLE memory writer, mechanically enforced by `memory-write-guard.sh`, writing memory at every `deliver`. None of that ships in the crux: there is no guard hook, no pipeline runtime, and `README/phases/migration` point to a 404 `workflow/sdk-pipeline.md`. In a crux-only install Rule 5 is honor-system, `deliver` writes no memory, and decisions silently vanish while the constitution implies hygiene is satisfied.

- **Most surveyed projects were never adopted at all (11 findings).** Many projects have a bare `.claude/` (often only `settings.local.json`, or a parallel hand-rolled command system). `/workflow-init` was never run, the plugin is not enabled at project scope (user `enabledPlugins` is `{}`), and `session-context.sh` gates on a missing `active.json` — so the SessionStart hook never fires and the contract is dark. There is no double-load risk (no copy-based duplicates); the risk is **non-load**.

- **The four-drift model classifies every finding.** Each finding is exactly one of: **temporal** (the package is frozen while canonical moves), **adoption** (the contract was never installed/enabled in a project), **internal-truth** (a shipped doc asserts something untrue in a crux-only install), or **design-gap** (a capability the package structurally lacks). Mapped to fix targets, these resolve at four chokepoints — `repackage` (re-cut from canonical), `workflow-init` (adopt/seed), `contract-patch` (edit shipped docs), and `refresh` (reconcile an adopted project) — with several spanning `multiple`.

- **A two-point version-stamp scheme makes all drift visible.** The supply chain is `canonical → (repackage) → plugin → (refresh) → project`. Today no hop is stamped. The fix: stamp **provenance at package time** (the canonical sha + spec in `plugin.json`) and an **adopted-version at adopt time** (a `.claude/workflow/.workflow-version` dotfile), so a refresh check can deterministically diff installed-vs-adopted and flag staleness end-to-end.

- **Prioritized roadmap — four deliverables, `workflow-memory-pipeline` left untouched.** (1) Harden `/workflow-init`: broaden + commit the secrets deny-list, add `enabledPlugins` self-activation, write the version stamp, gate the CLAUDE.md placeholder edit. (2) Ship a new third plugin, `workflow-refresh`, that detects and idempotently repairs project↔plugin drift. (3) Build a repeatable canonical→plugin `repackage.sh` pipeline with a provenance stamp and re-ship `protect-secrets.sh`. (4) Conditionalize every crux-only memory/pipeline doc assertion across the constitution and `workflow/` docs.

## 2. The drift model and the version-stamp scheme

### 2.1 The four-drift model

Every confirmed finding is one of four drift types, and each drift type has a natural repair chokepoint:

| Drift type | What it means | Root signal | Primary fix target |
|---|---|---|---|
| **temporal** | The package is a frozen snapshot; canonical moved ahead and the package carries stale/missing files. | Packaged file differs from canonical HEAD; capability added to canonical after the cut is absent. | `repackage` |
| **adoption** | The contract was never installed/enabled in a given project, so it never loads. | Bare `.claude/`; no `active.json`; plugin not in `enabledPlugins`; SessionStart hook gated off. | `workflow-init` |
| **internal-truth** | A shipped doc asserts as a standing fact something that is false in a crux-only install. | Doc references a hook/pipeline/store/doc that the crux package does not ship (e.g. `memory-write-guard.sh`, `workflow/sdk-pipeline.md`). | `contract-patch` |
| **design-gap** | The package structurally lacks a capability the design assumes (independent of canonical's current state). | A whole mechanism is missing from the package (e.g. the `protect-secrets.sh` runtime guard; any version-stamp at all). | `repackage` / `workflow-init` |

The model is deliberately orthogonal to **severity** and to **fix target**: a single design-gap (the missing guard hook) can manifest as many `high` adoption-scoped findings across projects, and several drift types converge on the same chokepoint. The seven failure classes in section 4 group findings by **shared root cause** so that one systemic fix retires many findings at once.

### 2.2 The supply chain and where the stamps go

The contract flows through four hops. Two of them are transformations that today leave **no trace**:

```
canonical  ──(repackage)──▶  plugin  ──(refresh)──▶  project
(scratchpad-priv/.claude)    (workflow-shell        (adopted .claude/
 HEAD = spec 053              v0.1.0, frozen          seeded by
 2026-06-19,                  ~spec 051,              /workflow-init)
 ~19 commits/week)            2026-06-17)
```

- **`canonical → (repackage) → plugin`** is a manual hand-cut today. No field records which canonical commit produced the package, so the temporal gap (section 2.1) is invisible from the package's own contents.
- **`plugin → (refresh) → project`** does not exist as a mechanism today. `/workflow-init` adopts (seeds the project once) but nothing reconciles an already-adopted project against a newer plugin, and the project records nothing about which plugin version it was adopted against.

### 2.3 The version-stamp scheme

The fix is a **two-point stamp** plus a **drift check**, one per transformation hop:

1. **Package-time provenance stamp (the `(repackage)` hop).** At package time, write the canonical lineage into the package itself: `plugin.json.packagedFrom = { commit, committedAt, canonicalSpec, packagedAt, options }`, mirrored in a human-readable `PROVENANCE.md`. With `packagedFrom.commit` present, temporal drift becomes computable: `git -C canonical rev-list --count <packagedFrom.commit>..HEAD`, filtered to the packaged surface. (Deliverable 3.)

2. **Adopt-time version stamp (the `(refresh)` hop, write side).** At adoption, `/workflow-init` writes `.claude/workflow/.workflow-version` recording `{ plugin, adoptedVersion, adoptedAt, lastInitVersion, lastInitAt }`. A dedicated dotfile is used (not an `active.json` key) so it does not break the asserted 4-array `active.json` schema. (Deliverable 1.)

3. **Refresh-time drift check (the `(refresh)` hop, read side).** A new `workflow-refresh` plugin reads the project stamp, resolves the **currently installed** plugin version/sha/provenance, and compares the two — flagging staleness deterministically and repairing the safe, idempotent deltas. Because refresh always targets the installed package, it stays correct as the plugin moves. (Deliverable 2.)

The two stamps together make the whole supply chain auditable: from any project you can answer "which plugin version am I on, and how far is that plugin behind canonical?" — the question that is unanswerable today.

---

## 3. Confirmed findings

**55 findings** across the package and surveyed projects: by severity — 14 high, 13 medium, 28 low; by drift type — 17 design-gap, 17 internal-truth, 14 adoption, 7 temporal; by verdict — 26 confirmed, 27 partial, 2 dormant-by-design.

### 3.1 Summary table

| ID | Severity | Drift type | Fix target | Verdict | Title |
|----|----------|-----------|-----------|---------|-------|
| F0-0 | high | design-gap | repackage | partial | Secrets/protect PreToolUse guard hook (protect-secrets.sh) is entirely dropped from the plugin |
| F0-4 | high | temporal | repackage | confirmed | Verifier permissionMode fix (spec 053, 2026-06-19) not in plugin — shipped verifiers stall on per-call permission prompts |
| F1-0 | high | internal-truth | contract-patch | partial | Constitution Rule 5 asserts the SDK memory pipeline is the SOLE writer and that a guard hook mechanically enforces it — both false in crux-only |
| F1-6 | high | internal-truth | contract-patch | confirmed | workflow/README.md core-vocabulary and boundaries describe the SDK pipeline / memory-write split as standing facts and point to a nonexistent sdk-pipeline.md |
| F8-2 | high | design-gap | workflow-init | confirmed | No secrets deny-list — .env with YOUTUBE_API_KEY is unprotected (only line of defense, and it is absent) |
| F9-0 | high | adoption | workflow-init | confirmed | Project never adopted the workflow-shell contract — bare .claude/ with only settings.local.json |
| F11-0 | high | adoption | workflow-init | confirmed | Project never adopted the workflow shell — contract is entirely absent and never loads |
| F11-1 | high | adoption | workflow-init | confirmed | SessionStart hook does not fire: plugin not installed for this project AND active.json gate fails |
| F11-2 | high | adoption | workflow-init | confirmed | Secrets deny-list absent — real .env with PERPLEXITY_API_KEY is unprotected (only protection in crux) |
| F13-3 | high | design-gap | workflow-init | confirmed | Secrets deny-list lives only in settings.local.json and omits workflow-init's broader defaults — and there is NO guard hook anywhere as backstop |
| F14-2 | high | design-gap | workflow-init | confirmed | No committed secrets deny-list in settings.json — only an un-shared settings.local.json protects .env, and a real .env sits at repo root |
| F16-3 | high | design-gap | workflow-init | confirmed | Secrets deny-list lives in settings.local.json (untracked) and is narrow/repo-relative — fragile single line of defense |
| F18-0 | high | adoption | workflow-init | confirmed | clipsight is completely unadopted — zero contract files, contract never loads |
| F18-3 | high | adoption | workflow-init | confirmed | workflow-shell plugin not enabled for clipsight (no project enablement; user enabledPlugins is empty) |
| F0-1 | medium | design-gap | repackage | partial | memory-write-guard.sh (sole-writer enforcement, constitution Rule 5) is asserted by shipped docs but not shipped |
| F0-2 | medium | design-gap | contract-patch | partial | Entire SDK memory pipeline (launcher + 10 modules + sdk-pipeline.md doc) is referenced but absent; deliver-phase memory writes silently no-op |
| F0-3 | medium | temporal | repackage | partial | No provenance stamp ties the plugin (v0.1.0) to a canonical commit — temporal drift is structurally invisible |
| F1-1 | medium | internal-truth | contract-patch | partial | phases.md deliver row + 'Deliver: SDK memory pipeline' section unconditionally state memory IS written at every deliver |
| F1-3 | medium | internal-truth | contract-patch | partial | evaluation.md makes cross-checker's MEMORY.md / selective-mirror-policy compliance an unconditional gating check on a store that crux-only never populates |
| F1-5 | medium | internal-truth | contract-patch | partial | artifacts.md folder-layout comments and MEMORY.md/mirror sections present agent-memory silos, the SDK writer, and the guard hook as live facts |
| F1-7 | medium | internal-truth | contract-patch | confirmed | migration.md onboarding bootstraps user-side memory mirror and 'seed memory/' steps that assume the pipeline keeps stores in sync |
| F7-2 | medium | design-gap | multiple | partial | No secrets deny-list in settings.json — secrets protection relies solely on a narrow .env-only deny in settings.local.json |
| F12-2 | medium | design-gap | workflow-init | partial | Secrets deny-list is partial and lives only in settings.local.json — credentials/service-account/.env.* unprotected; this deny-list is the ONLY secrets protection in crux |
| F15-3 | medium | adoption | workflow-init | confirmed | Missing per-project state files (CLAUDE.md, active.json, workflow/queue.md) — no workflow state machine |
| F16-2 | medium | design-gap | workflow-init | confirmed | No SessionStart hook → contract never auto-loads; custom system relies on manual /start_session instead |
| F16-4 | medium | design-gap | workflow-init | confirmed | Broad Bash / Read(*) / Write(*) allow-list weakens the already-thin secrets deny protection |
| F18-2 | medium | adoption | workflow-init | partial | No secrets deny-list — secrets completely unprotected (deny-list is the ONLY protection in crux) |
| F0-5 | low | temporal | repackage | partial | shell-audit dynamic-workflow (spec 052, 2026-06-18) absent from plugin |
| F0-7 | low | design-gap | repackage | confirmed | Stack-specific rules (backend-go.md, frontend-tsx.md) dropped; agents still assume Go/pytest/React |
| F1-2 | low | internal-truth | contract-patch | partial | phases.md '/compact' and 'Deliver: branch and PR' reference the pipeline's commit/no-op as if the pipeline always exists |
| F1-4 | low | internal-truth | contract-patch | partial | communication.md asserts the SDK memory subprocess runs at every deliver and is the sole writer — false in crux-only; also the BLOCKED-PERSIST-INLINE 'captured by the pipeline' claim |
| F1-8 | low | internal-truth | contract-patch | dormant-by-design | rules/migrations.md and routing.md cite memory topic files as the home of decided facts, implying a populated memory the crux never writes |
| F2-0 | low | design-gap | repackage | partial | No plugin version stamp recorded at adoption — cannot detect plugin/project contract drift |
| F2-1 | low | internal-truth | refresh | confirmed | Archived specs 001/002 still on pre-plugin state.json schema (partial migration) |
| F3-0 | low | temporal | workflow-init | partial | No plugin version stamp recorded anywhere in the project — adopted version is invisible to the project itself |
| F3-1 | low | design-gap | workflow-init | confirmed | CLAUDE.md left as unedited seed template (placeholder description and Stack section) |
| F3-2 | low | internal-truth | refresh | confirmed | settings.local.json contains an over-broad one-off python3 introspection Bash allow that should not be a persisted permission |
| F4-7 | low | design-gap | repackage | confirmed | Secrets deny-list present and matches workflow-init baseline, but coverage is narrow (only protection layer) |
| F7-3 | low | internal-truth | refresh | confirmed | Stale full duplicate of agents/ and commands/ inside the pedantic-euclid worktree's .claude/ |
| F8-4 | low | internal-truth | workflow-init | partial | No version stamp recording which plugin version was adopted |
| F9-4 | low | temporal | repackage | partial | No plugin version stamp recorded for this project |
| F9-5 | low | adoption | workflow-init | partial | No stale copy-based contract duplicates present (negative finding — no double-load risk) |
| F11-3 | low | internal-truth | repackage | partial | No version stamp recording which plugin version was/would be adopted |
| F12-3 | low | temporal | repackage | partial | No version stamp recording which plugin version was (or would be) adopted |
| F13-4 | low | internal-truth | multiple | partial | No plugin version stamp recorded in the project — no on-disk record of which contract version is in force |
| F14-0 | low | adoption | workflow-init | confirmed | Workflow-shell contract entirely absent — project is fully un-adopted (adoptionMode: none confirmed) |
| F15-2 | low | adoption | workflow-init | partial | No secrets deny-list anywhere — secrets are completely unprotected |
| F15-6 | low | adoption | workflow-init | confirmed | No plugin version stamp recorded in the project (no record of which contract version is/was adopted) |
| F16-0 | low | adoption | workflow-init | partial | workflow-shell contract entirely absent — project runs a parallel hand-rolled workflow system, never adopted |
| F17-4 | low | temporal | workflow-init | partial | No plugin version stamp anywhere — if Temp1 is ever adopted there is no record of which workflow-shell version it was seeded from |
| F17-5 | low | internal-truth | refresh | dormant-by-design | TaskCompleted hook references MEMORY.md update, but no MEMORY.md exists in the Temp1 project tree (orphaned reminder) |
| F18-4 | low | design-gap | contract-patch | partial | workflow-init does not seed enabledPlugins — adopted projects rely on a manual enable step |
| F18-5 | low | design-gap | repackage | confirmed | No plugin version stamp recorded at adoption — refresh/compatibility cannot be reasoned about |
| F18-6 | low | internal-truth | workflow-init | confirmed | cowork PRD docs live under .claude/cowork/ (Phase-0 recorded them at project root) and are unmanaged by the contract |
| F19-0 | low | adoption | workflow-init | partial | Workflow-shell contract entirely absent — project was never adopted (adoptionMode: none) |

### 3.2 Finding details

#### Design-gap findings (17)

##### F0-0 — Secrets/protect PreToolUse guard hook (protect-secrets.sh) is entirely dropped from the plugin

- **Severity:** high · **Fix target:** repackage · **Verdict:** partial
- **Component:** hooks/protect-secrets.sh
- **Scope:** Every project that adopts the plugin via /workflow-init
- **Expected:** Canonical ships protect-secrets.sh wired as a PreToolUse hook (matcher Read|Edit|Write|MultiEdit|Bash) that actively BLOCKS (exit 2) any access to .env*, credentials.json, service-account*.json, and SSH private keys (id_rsa/id_ed25519/id_ecdsa[.pub]) for BOTH file tools AND Bash commands (token-boundary regex BASH_TOKEN_RE), with an allow-list short-circuit for .env.example/.sample/.template/.dist/.defaults.
- **Actual:** The plugin registers EXACTLY ONE hook (SessionStart -> session-context.sh, a pure context-injector). protect-secrets.sh is not shipped and not registered. The plugin's only 'secrets protection' is a passive settings.json deny-list patch applied by commands/workflow-init.md (deny Read/Edit/Write on ./.env, ./.env.*, ./credentials.json, ./service-account*.json). This passive deny-list (a) does NOT cover SSH private keys at all (grep for id_rsa/id_ed25519/ecdsa returns 0), and (b) does NOT cover Bash-command exfiltration (e.g. `cat .env`), which the canonical hook explicitly catches. A runtime guard that blocks on exit 2 is replaced by static permission config with a strictly smaller blast radius.
- **Evidence:** Plugin hooks/hooks.json registers only SessionStart. Canonical protect-secrets.sh line 22 PROTECTED_BASENAME_RE includes id_(rsa|ed25519|ecdsa); line 31 BASH_TOKEN_RE blocks Bash refs; line 38 exit 2. Plugin workflow-init.md line 91 PATCH deny[] lists only .env*/credentials/service-account, no SSH keys, no Bash matcher (settings deny cannot gate Bash arg contents).

##### F8-2 — No secrets deny-list — .env with YOUTUBE_API_KEY is unprotected (only line of defense, and it is absent)

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** .claude/settings.json permissions.deny (secrets guard)
- **Scope:** all read/edit/write access to .env and credential files in this project
- **Expected:** /workflow-init merges a permissions.deny list into .claude/settings.json blocking Read/Edit/Write on ./.env, ./.env.*, ./credentials.json, ./service-account*.json. Since there is NO protect/guard hook anywhere in the contract, this settings deny-list is the ONLY protection for secrets.
- **Actual:** There is no .claude/settings.json at all — only settings.local.json, whose permissions.deny is []. A real .env exists at repo root containing YOUTUBE_API_KEY= (plus DEFAULT_CAPTION_LANGUAGE, DEBUG). Nothing prevents the agent from reading or editing it. .gitignore covers .env for git, but that does not constrain agent tool access.
- **Evidence:** settings.local.json deny=[]; no settings.json present; /Users/rohitseelam/Projects/Youtube_MCP/.env exists (492 bytes) with key YOUTUBE_API_KEY. workflow-init.md line 91 PATCH defines the deny patterns that would protect it.

##### F13-3 — Secrets deny-list lives only in settings.local.json and omits workflow-init's broader defaults — and there is NO guard hook anywhere as backstop

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** secrets protection (settings deny-list — the ONLY secret protection in crux)
- **Scope:** /Users/rohitseelam/Projects/claude-personal/.claude/settings.local.json (permissions.deny)
- **Expected:** Per the constitution model, the settings deny-list is the SOLE protection for secrets (there is no protect/guard PreToolUse hook anywhere in crux). workflow-init seeds a baseline deny set: Read/Edit/Write of ./.env, ./.env.*, plus Read of ./credentials.json and ./service-account*.json.
- **Actual:** claude-personal DOES have a deny-list, but only in settings.local.json and narrower than the shell baseline: it covers ./.env (Read/Write/Edit) and ./whatsapp-agent-key.json, but NOT the wildcard ./.env.* family, ./credentials.json, or ./service-account*.json. The only PreToolUse hook present (validate_source_extractor.py) is a Task-argument validator, NOT a secrets guard — so if the deny-list misses a path, nothing else catches it.
- **Evidence:** settings.local.json lines 19-26 deny .env + whatsapp-agent-key.json. workflow-init.md line 91 PATCH deny includes ./.env.*, ./credentials.json, ./service-account*.json — none present here. hooks/validate_source_extractor.py is a source-code-extractor arg validator, not a secrets guard.

##### F14-2 — No committed secrets deny-list in settings.json — only an un-shared settings.local.json protects .env, and a real .env sits at repo root

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** secrets deny-list / settings.json
- **Scope:** /Users/rohitseelam/Projects/LangGraph/langchain-academy/.claude/settings.local.json (deny-list lives only here); repo-root .env
- **Expected:** A committed, shared settings.json carrying the secrets deny-list (Read/Write/Edit on .env and key files). The deny-list is the ONLY secrets protection in the entire workflow-shell design — there is no protect/guard hook anywhere in the plugin — so it must be present and shared.
- **Actual:** There is no settings.json at all. A deny-list exists but only in settings.local.json (denies Read/Write/Edit on ./.env and ./whatsapp-agent-key.json). settings.local.json is the personal/un-committed layer, so the protection is not shared and not guaranteed to be active for other clones/sessions. A real .env (377 bytes) exists at repo root, so the exposure surface is concrete, not hypothetical. With no guard hook to fall back on, the only protection is this local, fragile deny-list.
- **Evidence:** settings.local.json deny block lists ./.env, ./whatsapp-agent-key.json. `ls .claude/settings.json` => NO settings.json. `.env` present at repo root (ls -la shows -rw-r--r-- .env, 377 bytes). Plugin tree has no protect/guard hook (only hooks/session-context.sh under SessionStart).

##### F16-3 — Secrets deny-list lives in settings.local.json (untracked) and is narrow/repo-relative — fragile single line of defense

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** secrets deny-list (settings.json)
- **Scope:** Secret-file access control
- **Expected:** The secrets deny-list should be in the merged, source-controlled .claude/settings.json (the only protection in crux — there is no separate protect/guard hook). It should broadly cover secret material (e.g. **/.env, **/*.key, *-key.json, credentials).
- **Actual:** No .claude/settings.json exists. A deny-list IS present but only in .claude/settings.local.json, which is git-ignored/local and not the contract target. It is also narrow and uses repo-relative './' patterns: Read(./.env) / Write(.env) / Edit(.env) and three entries for ./whatsapp-agent-key.json. Patterns like Read(./.env) miss nested .env files (e.g. service/.env) and other secret types; co-located service-account JSONs beyond the one named file are unprotected.
- **Evidence:** /Users/rohitseelam/Projects/Multi Agent/Multi Agent Pilot/.claude/settings.local.json lines 18-25 (deny block); no settings.json present

##### F0-1 — memory-write-guard.sh (sole-writer enforcement, constitution Rule 5) is asserted by shipped docs but not shipped

- **Severity:** medium · **Fix target:** repackage · **Verdict:** partial
- **Component:** hooks/memory-write-guard.sh
- **Scope:** Memory-store integrity in every adopting project; constitution Rule 5 enforceability
- **Expected:** Canonical ships memory-write-guard.sh as a PreToolUse hook (matcher Write|Edit|MultiEdit) that mechanically enforces the SDK pipeline as the SOLE memory writer (constitution Rule 5, spec 029): it blocks (exit 2) any non-SDK actor writing the memory roots unless CLAUDE_CODE_ENTRYPOINT=sdk-py or SDK_MEMORY_PIPELINE=1.
- **Actual:** The hook is absent from the plugin (only session-context.sh ships). Yet the plugin's own constitution.md line 41 states enforcement happens 'mechanically by .claude/hooks/memory-write-guard.sh', and 16 other shipped files (artifacts.md, rules/claude-code.md, cross-checker.md, orchestrator.md, README.md, etc.) reference it. The shipped constitution asserts a mechanical guard that does not exist in the package — Rule 5 becomes an honor-system rule with no enforcement, so any agent can silently corrupt the memory store.
- **Evidence:** Plugin constitution.md:41 references memory-write-guard.sh; grep -l across plugin returns 17 files referencing the absent guard/pipeline; hooks/hooks.json registers no PreToolUse hook. Canonical hooks/memory-write-guard.sh exists.

##### F0-2 — Entire SDK memory pipeline (launcher + 10 modules + sdk-pipeline.md doc) is referenced but absent; deliver-phase memory writes silently no-op

- **Severity:** medium · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** hooks/sdk-memory-pipeline.sh + sdk_memory_pipeline.py + 8 helper modules + workflow/sdk-pipeline.md
- **Scope:** Deliver phase of every workflow; the 'post-deliver SDK memory write' step the docs mandate
- **Expected:** Canonical ships the full SDK memory pipeline: launcher sdk-memory-pipeline.sh + sdk_memory_pipeline.py + 8 helper modules (_memory_writer, _proposal_schema, _actor_map, _session_scope, _silo_shape_check, _phase_ledger, _budget_check, _orphan_check) + settings.sdk-memory.json + the contract doc workflow/sdk-pipeline.md (19.6KB), invoked at every deliver as the sole memory writer.
- **Actual:** None of the pipeline runtime ships, and workflow/sdk-pipeline.md is dropped from the workflow/ doc set (plugin ships 7 docs; canonical's sdk-pipeline.md is gone). But shipped phases.md references a 'Deliver: SDK memory pipeline' section and communication.md references the claude-agent-sdk deliver subprocess. The marketplace README admits the SessionStart hook 'is not the SDK memory pipeline.' Result: the documented deliver-phase memory write has no implementation in the package and points to a doc that wasn't shipped — a dangling contract reference and a missing core capability.
- **Evidence:** Plugin workflow/ dir lists 7 docs, no sdk-pipeline.md (canonical has it). phases.md/communication.md in plugin reference the pipeline; no sdk-memory-pipeline.sh or sdk_memory_pipeline.py in plugin hooks/ (only session-context.sh).

##### F7-2 — No secrets deny-list in settings.json — secrets protection relies solely on a narrow .env-only deny in settings.local.json

- **Severity:** medium · **Fix target:** multiple · **Verdict:** partial
- **Component:** settings.json secrets deny-list
- **Scope:** /Users/rohitseelam/Projects/Assignments/.claude/settings.json (absent) and settings.local.json
- **Expected:** A committed settings.json carrying the contract's secrets deny-list (broad coverage of credential/key/token/.env-family read paths). The settings deny-list is the ONLY secrets protection in crux — there is no separate protect/guard hook anywhere — so its absence leaves secrets effectively unprotected.
- **Actual:** There is no settings.json at all. The only deny rules live in settings.local.json and cover just three exact paths: Read(./.env), Write(.env), Edit(.env). This is local-only (not committed/shared), does not match nested env files (e.g. src_leoforce/.env, src_proplens/.env which ARE referenced in .gitignore), and does not cover other secret material (keys, tokens, credentials.json, *.pem). Since no protect/guard hook exists in crux, this thin local deny is the entire defense.
- **Evidence:** settings.local.json deny = [Read(./.env), Write(.env), Edit(.env)]. .gitignore lists src_leoforce/.env and src_proplens/.env — real nested secrets that the ./.env-anchored deny rule does not match. No settings.json present; no hooks present (Phase-0 hooksPresent: []).

##### F12-2 — Secrets deny-list is partial and lives only in settings.local.json — credentials/service-account/.env.* unprotected; this deny-list is the ONLY secrets protection in crux

- **Severity:** medium · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** settings secrets deny-list
- **Scope:** /Users/rohitseelam/Projects/professional-workspace/.claude/settings.local.json (deny block)
- **Expected:** workflow-init merges a deny-list covering Read/Edit/Write of ./.env, ./.env.*, ./credentials.json, ./service-account*.json into settings.json. There is no protect/guard hook anywhere in crux, so this deny-list is the sole secrets safeguard.
- **Actual:** settings.local.json deny has only Read(./.env), Write(.env), Edit(.env). Missing: .env.* family, credentials.json, service-account*.json. Also pattern-inconsistent — the Read deny uses ./ prefix but Write/Edit do not. allow[] contains Read(*) and Write(*); deny correctly wins for bare .env, but unmatched secret patterns fall through to the broad allow. No settings.json exists at all. No secret files currently in the repo (find found none; .gitignore covers *credentials* and .env), which limits immediate blast radius — but any future credentials.json / *.pem / .env.local would be readable/writable by an agent.
- **Evidence:** settings.local.json:13-17 deny block; allow has Read(*)/Write(*); workflow-init.md:91 PATCH deny array enumerates the fuller set; no protect/guard hook found in plugin hooks/.

##### F16-2 — No SessionStart hook → contract never auto-loads; custom system relies on manual /start_session instead

- **Severity:** medium · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** SessionStart hook / session bootstrap
- **Scope:** Session bootstrap
- **Expected:** Under the workflow-shell, context (README + constitution + project state) loads automatically at SessionStart via the plugin hook.
- **Actual:** Phase-0 hooksPresent:[] and there is no settings.json (only settings.local.json, which carries no hooks). Context is loaded only when the user manually runs the custom /start_session command, which reads project_context/project_logs and PRD files. No automatic activation of any contract.
- **Evidence:** /Users/rohitseelam/Projects/Multi Agent/Multi Agent Pilot/.claude/settings.local.json (permissions only, no 'hooks' key); .claude/commands/start_session.md (manual bootstrap)

##### F16-4 — Broad Bash / Read(*) / Write(*) allow-list weakens the already-thin secrets deny protection

- **Severity:** medium · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** permissions allow-list (settings.local.json)
- **Scope:** Permission posture
- **Expected:** With the deny-list as the only secrets guard, the allow-list should not contain unconstrained wildcards that broaden the surface the deny-list must defend.
- **Actual:** settings.local.json allow includes bare 'Bash', 'Read(*)', 'Write(*)', and 'Bash(mkdir:*)'. Bare Bash means a shell command (cat .env, etc.) can read secrets entirely outside the tool-level deny patterns, which only cover Read/Write/Edit tools — so the deny-list is bypassable.
- **Evidence:** /Users/rohitseelam/Projects/Multi Agent/Multi Agent Pilot/.claude/settings.local.json lines 14-16 ('Read(*)','Write(*)','Bash')

##### F0-7 — Stack-specific rules (backend-go.md, frontend-tsx.md) dropped; agents still assume Go/pytest/React

- **Severity:** low · **Fix target:** repackage · **Verdict:** confirmed
- **Component:** rules/backend-go.md, rules/frontend-tsx.md
- **Scope:** Code-rule guidance for backend-engineer / frontend-engineer in adopting projects
- **Expected:** Canonical ships 6 active rules docs including backend-go.md (consumed by lint-on-write gofmt/go vet) and frontend-tsx.md.
- **Actual:** The plugin ships only 4 rules (general, claude-code, tests, migrations) — backend-go.md and frontend-tsx.md are dropped. Yet the shipped backend-engineer assumes Go and qa-engineer assumes pytest, so the stack-specific rule docs those agents would lean on are gone. This is partly a reasonable de-stack-ing for a generic template, but it leaves the shipped Go/pytest/React agent assumptions without their rule backing — a coherence gap rather than a security one. (Canonical also keeps a _candidates-2026-06-11.md staging file, intentionally not shipped.)
- **Evidence:** Plugin rules/ = {general, claude-code, tests, migrations}.md. Canonical rules/ adds backend-go.md, frontend-tsx.md, and _candidates-2026-06-11.md. Plugin agents/engineering/backend-engineer.md assumes Go; qa-engineer.md assumes pytest.

##### F2-0 — No plugin version stamp recorded at adoption — cannot detect plugin/project contract drift

- **Severity:** low · **Fix target:** repackage · **Verdict:** partial
- **Component:** workflow-init seeding / .claude (cooking)
- **Scope:** Every project adopted via /workflow-init, including cooking. The cooking project's .claude/ has zero machine-readable record of which plugin version it was adopted against.
- **Expected:** Adoption should leave a version stamp (e.g. .claude/workflow/.workflow-version or a key in active.json/settings.json) recording the workflow-shell version adopted (installed: 0.1.0). Future sessions / refresh tooling could then detect when the installed plugin has moved ahead of what the project was seeded/migrated against.
- **Actual:** workflow-init (commands/workflow-init.md) seeds CLAUDE.md, active.json, queue.md and merges settings.json but writes NO version record anywhere. The plugin installs at version 0.1.0 (plugin.json + installed_plugins.json), yet the only trace of adoption in cooking is a prose memory entry in .claude/memory/topics/decisions.md (2026-06-18) that names the plugin ('workflow-shell@workflow-shell-marketplace') but not its version. There is no programmatic way to know what contract version this project tracks.
- **Evidence:** Installed: /Users/rohitseelam/.claude/plugins/marketplaces/workflow-shell-marketplace/plugins/workflow-shell/.claude-plugin/plugin.json -> "version": "0.1.0". Seeder /Users/rohitseelam/.claude/plugins/marketplaces/workflow-shell-marketplace/plugins/workflow-shell/commands/workflow-init.md seeds only those 4 files, no stamp. grep for version|stamp|adopted across /Users/rohitseelam/Projects/seriesA/cooking/.claude returns only prose hits in decisions.md / spec reports, none a version record.

##### F3-1 — CLAUDE.md left as unedited seed template (placeholder description and Stack section)

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** .claude/CLAUDE.md
- **Scope:** project root description + Stack section consumed every session
- **Expected:** After adoption the project owner edits the one-line description and the Stack section (languages, frameworks, entry points) so the orchestrator has real project context. CLAUDE.md is loaded into every session.
- **Actual:** Line 3 still reads `<one-line description — EDIT THIS>` and line 16 still reads `- EDIT: languages, frameworks, entry points for this project.`. The project name itself is misspelled (`Swift_custom_coice_capture` — 'coice'), and the template carries that misspelling through. The contract is structurally present but conveys zero project-specific signal.
- **Evidence:** .claude/CLAUDE.md lines 1-3 and 15-16 are verbatim seed placeholders.

##### F4-7 — Secrets deny-list present and matches workflow-init baseline, but coverage is narrow (only protection layer)

- **Severity:** low · **Fix target:** repackage · **Verdict:** confirmed
- **Component:** .claude/settings.json permissions.deny
- **Scope:** secret-file read/write protection
- **Expected:** Deny-list covers the common secret surfaces, since (per the lens) there is NO protect/guard hook in crux — settings deny-list is the ONLY secret protection.
- **Actual:** Deny-list IS present and EXACTLY equals the workflow-init seeded baseline (8 entries: ./.env, ./.env.*, credentials.json, service-account*.json for Read/Edit/Write). So this is NOT a missing-deny-list finding. However the baseline omits common secret surfaces (*.pem, id_rsa/id_*, .aws/, *.key, .npmrc, tokens) and there is no guard hook to back it up — a defense-in-depth gap inherited from the packaged default, not a project regression.
- **Evidence:** settings.json lines 3-14 deny array is byte-identical to the PATCH in commands/workflow-init.md. No hooks present to supplement it.

##### F18-4 — workflow-init does not seed enabledPlugins — adopted projects rely on a manual enable step

- **Severity:** low · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** workflow-init command PATCH
- **Scope:** plugin commands/workflow-init.md line 91 (settings PATCH)
- **Expected:** After /workflow-init the project should be fully self-activating: settings.json should carry both the outputStyle/subagents/deny-list AND enabledPlugins so the SessionStart hook fires without a separate manual /plugin install.
- **Actual:** The workflow-init PATCH merges outputStyle, subagents, and permissions.deny only — it never sets enabledPlugins. The reference adopted project has enabledPlugins set, which means it was added by a separate /plugin install step, not by workflow-init. New adoptions (like clipsight will be) need two manual actions, and operators can easily seed active.json without enabling the plugin, leaving the hook permanently dark.
- **Evidence:** workflow-init.md line 91 PATCH JSON contains outputStyle/subagents/permissions.deny but no enabledPlugins key. Reference project nonetheless has enabledPlugins set → added out-of-band.

##### F18-5 — No plugin version stamp recorded at adoption — refresh/compatibility cannot be reasoned about

- **Severity:** low · **Fix target:** repackage · **Verdict:** confirmed
- **Component:** version stamp
- **Scope:** workflow-init seeded files (CLAUDE.md / active.json) across all projects
- **Expected:** An adopted project should record which plugin version it was adopted against (e.g. a pluginVersion/adoptedVersion field), so a future refresh can detect when the installed plugin (currently 0.1.0) has drifted past the adopted contract.
- **Actual:** Neither workflow-init nor any adopted project records the plugin version. The plugin manifest is version 0.1.0, but clipsight (once adopted) and even the reference project carry no stamp. grep for 0.1.0/pluginVersion/adoptedVersion in the reference .claude returns nothing.
- **Evidence:** plugin.json version=0.1.0. workflow-init.md has no version/stamp logic (grep found none). Reference project .claude has no version stamp (grep none).

#### Internal-truth findings (17)

##### F1-0 — Constitution Rule 5 asserts the SDK memory pipeline is the SOLE writer and that a guard hook mechanically enforces it — both false in crux-only

- **Severity:** high · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** constitution.md
- **Scope:** constitution.md:38-41 (Rule 5 'Memory hygiene')
- **Expected:** Rule 5 should describe what is true with the full install AND state the crux-only reality: that when the pipeline plugin is absent, NO writer exists, so durable decisions are NOT captured at deliver and memory hygiene is the USER's manual responsibility (or simply unmet).
- **Actual:** Rule 5 unconditionally claims a sole writer exists and is mechanically enforced by a hook that is not installed. A reader in crux-only believes memory is being written and protected when in fact nothing writes it and the guard does not exist — decisions silently vanish while the constitution implies hygiene is satisfied.
- **Evidence:** constitution.md:40-41: 'The SDK memory pipeline is the SOLE writer of memory. The orchestrator and every subagent MUST NOT write `.claude/memory/`, `.claude/agent-memory/`, or the canonical `~/.claude/projects/<slug>/memory/` — enforced mechanically by `.claude/hooks/memory-write-guard.sh`.' Crux-only reality: the only hook the plugin ships is `hooks/session-context.sh` (hooks.json wires SessionStart only); there is NO `memory-write-guard.sh`, NO `sdk-pipeline.py`, NO `skills/memory/`. The pipeline lives in the SEPARATE, unimplemented `workflow-memory-pipeline` plugin (marketplace README:11 'reserved slot … Not yet implemented … The crux works without it'; that plugin's README:26-27 'constitution.md Rule 5 … stay dormant by design — they describe a writer that simply isn't installed yet').

##### F1-6 — workflow/README.md core-vocabulary and boundaries describe the SDK pipeline / memory-write split as standing facts and point to a nonexistent sdk-pipeline.md

- **Severity:** high · **Fix target:** contract-patch · **Verdict:** confirmed
- **Component:** workflow/README.md
- **Scope:** README.md:24 (memory vs queue), README.md:40 (vocabulary: SDK memory pipeline), README.md:66 (skills/memory/), README.md:75 (what is NOT here)
- **Expected:** The index/vocabulary should define the SDK pipeline as an OPTIONAL companion plugin (matching marketplace README:11), not a standing crux component, and not cite contract/skill files that the crux does not ship.
- **Actual:** Reader following README.md is told memory topics are 'written at every deliver', is sent to `workflow/sdk-pipeline.md` (404 in crux) for the contract, and told `skills/memory/` exists (it doesn't) — every pointer dead-ends in crux-only.
- **Evidence:** README.md:40: 'SDK memory pipeline — the SOLE memory writer; a `claude-agent-sdk` subprocess that runs at every `deliver`. … Contract in `workflow/sdk-pipeline.md` …'. There is NO `workflow/sdk-pipeline.md` in the plugin (find returned nothing). README.md:66: 'skills/memory/ — `compile`, `extract`, `jsonl-format` … read by the SDK memory pipeline.' No `skills/memory/` exists in the crux (skills dir holds only the 5 workflow skills + _scripts). README.md:24: '.claude/memory/topics/*.md — … Written by the SDK memory pipeline at every `deliver`.' README.md:75: memory 'both written solely by the SDK memory pipeline at `deliver` (`constitution.md` Rule 5).'

##### F1-1 — phases.md deliver row + 'Deliver: SDK memory pipeline' section unconditionally state memory IS written at every deliver

- **Severity:** medium · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** workflow/phases.md
- **Scope:** phases.md:33 (per-phase table deliver row), phases.md:59-63 ('Deliver: SDK memory pipeline'), phases.md:190-191 (Termination step 1)
- **Expected:** The deliver contract should mark the memory-pipeline step as conditional on the `workflow-memory-pipeline` plugin being installed, and state that in crux-only deliver completes with NO memory write (only branch/PR + docs).
- **Actual:** Reader is told 'every deliver' runs a subprocess that 'updates project memory' and that a guard hook blocks the orchestrator — in crux-only neither the subprocess nor the guard exists, so deliver writes no memory at all and the cited hook path is dead.
- **Evidence:** phases.md:33 deliver Output column: '… updated docs, memory pipeline run (see "Deliver: SDK memory pipeline" below)'. phases.md:60-61: 'At the end of every `deliver` phase (every workflow type), a `claude-agent-sdk` subprocess updates project memory. … the writer writes the CANONICAL store … and mirrors …'. phases.md:190: 'Project memory is updated by the SDK memory pipeline — the SOLE memory writer … The orchestrator does NOT write `.claude/memory/` itself (`constitution.md` Rule 5; mechanically blocked by `.claude/hooks/memory-write-guard.sh`).' None of this runs in crux-only: no `sdk-pipeline.md` exists in the plugin, no `hooks/sdk-memory-pipeline.sh`, no `memory-write-guard.sh`.

##### F1-3 — evaluation.md makes cross-checker's MEMORY.md / selective-mirror-policy compliance an unconditional gating check on a store that crux-only never populates

- **Severity:** medium · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** workflow/evaluation.md
- **Scope:** evaluation.md:69 (cross-checker Checks column), evaluation.md:239 (cost note pipeline carve-out is fine; the mirror checks are the issue)
- **Expected:** evaluation.md should mark the MEMORY.md/mirror-compliance sub-checks as applicable only when the memory-pipeline plugin is installed (i.e., when the two stores are actually maintained by a writer).
- **Actual:** Verification doc instructs cross-checker to gate the final HITL on memory-mirror compliance that, in crux-only, has no writer to comply — turning a contract check into either dead weight or a false-positive `major` that blocks deliver.
- **Evidence:** evaluation.md:69 lists cross-checker checks including 'MEMORY.md shape compliance (line format, 200-line / 25KB cap, no narrative paragraphs); selective-mirror-policy COMPLIANCE (NOT exact equality) between `~/.claude/projects/<project-slug>/memory/` and `<repo>/.claude/memory/` …'. In crux-only no pipeline ever writes either store; the canonical `~/.claude/projects/<slug>/memory/` and repo mirror are seeded manually at best and never synced, so a 'mirror compliance' gate either has nothing to check or produces spurious `major` findings (artifacts.md:253 says policy violation is `major`). The cross-checker AGENT file already hedges this (cross-checker.md:16: hook/design refs are 'dormant in a crux-only install') but evaluation.md does not.

##### F1-5 — artifacts.md folder-layout comments and MEMORY.md/mirror sections present agent-memory silos, the SDK writer, and the guard hook as live facts

- **Severity:** medium · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** workflow/artifacts.md
- **Scope:** artifacts.md:59-63 + 73 (folder layout + note), artifacts.md:218-225 (MEMORY.md shape), artifacts.md:253-255 (mirror-policy compliance + single-writer enforcement)
- **Expected:** These sections should state silo activeness, the SDK writer, and guard enforcement are contingent on the memory-pipeline plugin; in crux-only the silos/mirror are unwritten and the guard absent.
- **Actual:** Reader treats agent-memory silos as active and the memory roots as guarded; in crux-only the silos auto-load empty/manual files at best, nothing writes them, and there is no PreToolUse guard — the 'now ENFORCED mechanically' claim is simply false.
- **Evidence:** artifacts.md:73: 'The per-subagent silos at `<repo>/.claude/agent-memory/<agent>/` are ACTIVE for the 6 silo agents under the single-writer model … the SDK memory pipeline is the SOLE writer, and `memory-write-guard.sh` blocks non-SDK actors.' artifacts.md:223: '<repo>/.claude/memory/MEMORY.md. Written by the SDK memory pipeline alongside the canonical …'. artifacts.md:255: 'This single-writer contract is now ENFORCED mechanically by the `PreToolUse` guard `.claude/hooks/memory-write-guard.sh` (spec 029), which blocks any non-SDK actor from writing the three memory roots.' Crux-only: no agent-memory silo scaffolding ships (it's listed under the unimplemented memory-pipeline plugin README:14), no SDK writer, no guard hook. The silos are NOT 'ACTIVE' and the guard is NOT enforcing anything.

##### F1-7 — migration.md onboarding bootstraps user-side memory mirror and 'seed memory/' steps that assume the pipeline keeps stores in sync

- **Severity:** medium · **Fix target:** contract-patch · **Verdict:** confirmed
- **Component:** workflow/migration.md
- **Scope:** migration.md:51-62 (2d Bootstrap user-side memory), migration.md:74-79 (4. Seed memory/), migration.md:91 + 123 (hooks wired 'once the SDK pipeline … is enabled' / 'if SDK memory pipeline is in scope')
- **Expected:** Migration steps that seed/sync memory and wire capture/pipeline hooks should be explicitly tagged 'only if adopting the optional memory-pipeline plugin'; the base crux onboarding should not promise store sync.
- **Actual:** A team onboarding crux-only is told to seed a user-side mirror that 'subsequent pipeline runs keep in sync' (no pipeline → never synced, stores silently drift), and to wire hooks/scripts that the crux does not provide.
- **Evidence:** migration.md:62: 'Subsequent runs of the SDK memory pipeline at `deliver` keep both locations in sync (see `specs/012-…/design/04-memory-index-shape.md`).' migration.md:91: 'Hooks are optional for initial adoption … They become important once the SDK memory pipeline at `deliver` is enabled (see `workflow/sdk-pipeline.md`).' Points to `workflow/sdk-pipeline.md` (absent) and `specs/…/design/…` (the orchestrator/cross-checker agents flag these design refs as belonging to the optional pipeline plugin and 'dormant in a crux-only install'). The migration.md hooks step (89-90) even tells the user to copy `capture-session.sh` — a script that ships with the pipeline plugin, not the crux.

##### F1-2 — phases.md '/compact' and 'Deliver: branch and PR' reference the pipeline's commit/no-op as if the pipeline always exists

- **Severity:** low · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** workflow/phases.md
- **Scope:** phases.md:54 (branch-and-PR step 2), phases.md:84-88 ('/compact')
- **Expected:** Branch-and-PR should note the memory commit only rides the PR when the pipeline plugin is installed; the /compact bullet should be conditional or omitted in crux.
- **Actual:** Reader expects a memory commit in every spec PR; in crux-only no such commit exists, so the 'part of the same PR' guarantee is false.
- **Evidence:** phases.md:54: 'This includes the SDK memory pipeline's commit (see "Deliver: SDK memory pipeline") … the pipeline still runs at deliver, but ON the spec branch, and its memory commit is part of the same PR.' phases.md:86 lists '/compact … does NOT trigger the SDK memory pipeline' — describing a component that is not installed. In crux-only there is no pipeline commit, so the PR contains no memory commit.

##### F1-4 — communication.md asserts the SDK memory subprocess runs at every deliver and is the sole writer — false in crux-only; also the BLOCKED-PERSIST-INLINE 'captured by the pipeline' claim

- **Severity:** low · **Fix target:** contract-patch · **Verdict:** partial
- **Component:** workflow/communication.md
- **Scope:** communication.md:134 (BLOCKED-PERSIST-INLINE durability), communication.md:140-144 ('The SDK memory subprocess is NOT in the triangle')
- **Expected:** The 'SDK memory subprocess' section should be prefaced as describing the full install, with an explicit crux-only note that no such subprocess exists; the BLOCKED-PERSIST-INLINE durability claim should not promise pipeline capture in crux-only.
- **Actual:** Reader is told a leaf subprocess writes memory every deliver and that durable patterns are auto-captured — neither is true in crux-only, so the 'don't hand-write, the pipeline will capture it' guidance leaves the knowledge uncaptured.
- **Evidence:** communication.md:142: 'The `claude-agent-sdk` subprocess that runs at every `deliver` … writes the canonical store … and mirrors the non-personal subset …'. communication.md:144: 'Memory updates are best-effort … The next workflow's `verify` phase picks up any divergence via cross-checker's selective-mirror-policy compliance check.' communication.md:134: 'any new instance is captured at `deliver` by the SDK memory pipeline (the sole memory writer — `constitution.md` Rule 5), not hand-written.' In crux-only no such subprocess exists; the BLOCKED-PERSIST-INLINE pattern instance is NOT captured anywhere automatically (no writer), and there is no divergence check because nothing writes the stores.

##### F1-8 — rules/migrations.md and routing.md cite memory topic files as the home of decided facts, implying a populated memory the crux never writes

- **Severity:** low · **Fix target:** contract-patch · **Verdict:** dormant-by-design
- **Component:** rules/migrations.md, workflow/routing.md
- **Scope:** rules/migrations.md:11, routing.md:137
- **Expected:** These cross-references should not assume a populated/maintained `memory/` store in crux-only; the routing-context read of `memory/MEMORY.md` should be qualified as 'if present'.
- **Actual:** Decisions are cited as living in memory topic files that the crux never populates, and routing claims to read a top-200 memory index that may be empty/absent — a soft promise of a memory substrate that isn't maintained.
- **Evidence:** rules/migrations.md:11: 'We do not write down migrations (decided 2026 — see `memory/topics/conventions.md`).' routing.md:137: 'Orchestrator reads the cleaned prompt + relevant context (`active.json`, `constitution.md`, top-200 of `memory/MEMORY.md`).' In crux-only `memory/MEMORY.md` and `memory/topics/conventions.md` are never written by any pipeline; they exist only if hand-seeded and are not auto-loaded the way the doc implies (the auto-load is the canonical `~/.claude/projects/<slug>/memory/`, populated by the absent pipeline).

##### F2-1 — Archived specs 001/002 still on pre-plugin state.json schema (partial migration)

- **Severity:** low · **Fix target:** refresh · **Verdict:** confirmed
- **Component:** .claude/specs/001-diet-tracker/state.json, .claude/specs/002-recipes-cooking/state.json
- **Scope:** Audit/read consistency only. Two archived (completed) specs were intentionally left on the legacy schema during the 2026-06-18 plugin migration; the active spec (003) was migrated correctly.
- **Expected:** All state.json files conform to the plugin's current schema (started, completed, complexity, autonomous, max_fix_rounds, active, tags, phase_history). The active spec 003 has this shape.
- **Actual:** 001/002 use the old schema: 001 has "created":"2026-06-15" (not "started"), no "active", "tags", and a non-schema "complexity":"epic"; 002 similarly legacy. decisions.md explicitly notes 'Archived 001/002 state left as legacy.' Harmless because they are archived in active.json and not advanced, but any tooling that reads all state.json uniformly will see a schema mismatch.
- **Evidence:** /Users/rohitseelam/Projects/seriesA/cooking/.claude/specs/001-diet-tracker/state.json has "created" + "complexity":"epic" and lacks active/tags/started; /Users/rohitseelam/Projects/seriesA/cooking/.claude/specs/003-recipes-revamp/state.json has the full new schema. decisions.md 2026-06-18 entry confirms intentional legacy leave.

##### F3-2 — settings.local.json contains an over-broad one-off python3 introspection Bash allow that should not be a persisted permission

- **Severity:** low · **Fix target:** refresh · **Verdict:** confirmed
- **Component:** .claude/settings.local.json
- **Scope:** local (non-shared) permissions allow-list
- **Expected:** settings.local.json should hold durable, project-meaningful local permissions. A one-shot diagnostic command used once to introspect installed plugins is not a standing permission and should not be persisted.
- **Actual:** settings.local.json allows `Read(//Users/rohitseelam/.claude/plugins/**)` (note the doubled leading slash `//Users` — likely a malformed path that will not match as intended) and a very specific `Bash(python3 -c "import json,sys; ...plugin...market...")` introspection command. Both are adoption-time debugging artifacts, not runtime needs of this project; the doubled-slash Read pattern is also probably a no-op.
- **Evidence:** .claude/settings.local.json lines 4-5: `"Read(//Users/rohitseelam/.claude/plugins/**)"` and the embedded python3 plugin-introspection one-liner.

##### F7-3 — Stale full duplicate of agents/ and commands/ inside the pedantic-euclid worktree's .claude/

- **Severity:** low · **Fix target:** refresh · **Verdict:** confirmed
- **Component:** .claude/worktrees/pedantic-euclid/.claude (duplicated agents + commands)
- **Scope:** /Users/rohitseelam/Projects/Assignments/.claude/worktrees/pedantic-euclid/.claude
- **Expected:** A git worktree should not carry its own divergent copy of the project's .claude/ agents and commands; there should be one source of truth.
- **Actual:** The worktree contains a full second copy of all three agents (library_docs_extractor.md, web_researcher.md, perplexity_researcher.md) and all three invoke_* commands, plus its own settings.local.json. diff -rq shows the agents currently match the parent, but this is an uncontrolled duplicate that will silently drift as either side is edited. (These are the project's OWN bespoke agents, not contract docs — so this is duplicate-content drift, not a plugin-vs-copy conflict.)
- **Evidence:** find lists .claude/worktrees/pedantic-euclid/.claude/{agents,commands}/* mirroring the parent .claude/. .git in that dir = 'gitdir: /Users/rohitseelam/Projects/Assignments/.git/worktrees/pedantic-euclid' (active worktree). .gitignore ignores .claude/, so these copies are untracked and unsynced.

##### F8-4 — No version stamp recording which plugin version was adopted

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** per-project adoption metadata
- **Scope:** future refresh/upgrade auditing
- **Expected:** Some record (in active.json or settings) of the plugin version adopted, so refresh tooling can detect when the cached plugin (currently 0.1.0) drifts past what the project was adopted against.
- **Actual:** No version stamp exists anywhere in the project — consistent with the project never having been adopted. Note this is also a contract-wide design gap: even the workflow-init seed (active.json = {active,queued,archived,prds}) records no plugin version, so adopted projects would lack a stamp too.
- **Evidence:** No active.json present here. workflow-init.md line 59 seeds active.json with no version field. plugin.json declares version 0.1.0 but nothing writes it into project state.

##### F11-3 — No version stamp recording which plugin version was/would be adopted

- **Severity:** low · **Fix target:** repackage · **Verdict:** partial
- **Component:** workflow-init seeding contract (version provenance)
- **Scope:** all adopted projects; surfaced here as a design gap
- **Expected:** An adopted project records the workflow-shell version it was adopted against, so drift between the project's contract and the installed plugin (currently 0.1.0) can be detected later.
- **Actual:** workflow-init.md seeds CLAUDE.md, active.json, queue.md, and merges settings.json, but writes NO version stamp anywhere. The only version record is installed_plugins.json (keyed on plugin install, not adoption) — and Perplexity_MCP has no entry there at all. After a future adoption this project would carry no record of which contract version it received.
- **Evidence:** commands/workflow-init.md (full body read) seeds 4 artifacts, none containing a version field. plugin.json version 0.1.0. installed_plugins.json has no Perplexity_MCP record.

##### F13-4 — No plugin version stamp recorded in the project — no on-disk record of which contract version is in force

- **Severity:** low · **Fix target:** multiple · **Verdict:** partial
- **Component:** version provenance / adoption stamp
- **Scope:** /Users/rohitseelam/Projects/claude-personal/.claude
- **Expected:** A way to know which workflow-shell version a project was adopted against (so refresh/repackage can detect staleness).
- **Actual:** Nothing in .claude/ references workflow-shell at all (grep: 'no workflow-shell mention in .claude'). Even adopted sibling projects rely solely on installed_plugins.json (version 0.1.0) for provenance — there is no per-project version stamp file in the contract at all. For claude-personal there is not even an enablement record, so version is wholly unknown.
- **Evidence:** grep -rl workflow-shell .claude → none. installed_plugins.json is the only version source and has no claude-personal entry. workflow-init.md seeds no version field into active.json or CLAUDE.md.

##### F17-5 — TaskCompleted hook references MEMORY.md update, but no MEMORY.md exists in the Temp1 project tree (orphaned reminder)

- **Severity:** low · **Fix target:** refresh · **Verdict:** dormant-by-design
- **Component:** settings.local.json TaskCompleted hook
- **Scope:** hooks/memory
- **Expected:** Hook references an existing memory target.
- **Actual:** References a non-existent project MEMORY.md.
- **Evidence:** settings.local.json TaskCompleted command echoes the MEMORY.md reminder; find -iname 'MEMORY.md' under Temp1 = 0 hits.

##### F18-6 — cowork PRD docs live under .claude/cowork/ (Phase-0 recorded them at project root) and are unmanaged by the contract

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** cowork/ docs vs workflow/queue.md
- **Scope:** /Users/rohitseelam/Projects/seriesA/clipsight/.claude/cowork/{build_requirements.md,market_report.md}
- **Expected:** Pre-spec product material should flow into the workflow backlog (workflow/queue.md Now/Next/Later buckets) once adopted, so it becomes specs via /workflow-new. The Phase-0 record placed cowork/ at the project root.
- **Actual:** Two substantial PRD-stage docs (build_requirements.md 257 lines, market_report.md 132 lines, both 'Draft v0.1' dated 2026-04-19) sit in .claude/cowork/ — NOT at the project root as the Phase-0 record states ('present':['cowork/ ...'] implied root). They are not referenced by any queue.md (none exists) and will be orphaned content after adoption unless deliberately migrated into the queue. They are also not covered by any deny-list.
- **Evidence:** Actual path: /Users/rohitseelam/Projects/seriesA/clipsight/.claude/cowork/*.md (confirmed by find). Phase-0 'present':['cowork/ (build_requirements.md, market_report.md)'] without the .claude/ prefix. Docs are product PRDs, not contract artifacts.

#### Adoption findings (14)

##### F9-0 — Project never adopted the workflow-shell contract — bare .claude/ with only settings.local.json

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** .claude/ (whole contract surface)
- **Scope:** Entire project: no workflow contract is active despite the plugin being installed globally.
- **Expected:** An adopted project has .claude/CLAUDE.md, .claude/active.json (4 arrays), .claude/workflow/queue.md, and a merged .claude/settings.json (outputStyle + subagent wiring + secrets deny-list) — the files workflow-init seeds.
- **Actual:** Phase-0 adoptionMode is 'none'. Re-read confirms .claude/ contains ONLY settings.local.json. Verified via `find .claude -type f` -> single result `.claude/settings.local.json`. No CLAUDE.md (root or .claude/), no active.json, no workflow/, no specs/, no agents, no settings.json.
- **Evidence:** `ls -la "/Users/rohitseelam/Projects/AI Engineering/.claude/"` -> only settings.local.json (164 bytes). `find .claude -type f` returns just .claude/settings.local.json. The 10 numbered learning-content folders (01_Mathematical_Foundations … 10_MLOps) are project data, not contract.

##### F11-0 — Project never adopted the workflow shell — contract is entirely absent and never loads

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** .claude/ (whole contract: CLAUDE.md, active.json, workflow/, settings.json, outputStyle)
- **Scope:** /Users/rohitseelam/Projects/Perplexity_MCP/.claude/
- **Expected:** An adopted project has .claude/CLAUDE.md (workflow-shell variant), .claude/active.json (4 arrays), .claude/workflow/queue.md, and .claude/settings.json with outputStyle 'Workflow Orchestrator' + subagent wiring + deny-list. The plugin's SessionStart hook then injects workflow/README.md + constitution.md each session.
- **Actual:** Phase-0 adoptionMode 'none' confirmed by re-read. .claude/ contains ONLY settings.local.json. CLAUDE.md is a vanilla /init-style project overview at repo ROOT (10KB, zero references to workflow-shell / active.json / Workflow Orchestrator). No active.json, no workflow/, no constitution, no settings.json, no outputStyle. The workflow contract has zero presence and never activates here.
- **Evidence:** grep for 'workflow-shell|Workflow Orchestrator|active.json' in /Users/rohitseelam/Projects/Perplexity_MCP/CLAUDE.md => no matches. ls .claude/ => only settings.local.json.

##### F11-1 — SessionStart hook does not fire: plugin not installed for this project AND active.json gate fails

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** SessionStart hook (session-context.sh) load path
- **Scope:** plugin enablement for /Users/rohitseelam/Projects/Perplexity_MCP
- **Expected:** In an adopted project the workflow-shell plugin is enabled and .claude/active.json exists, so hooks/session-context.sh injects the always-on contract (workflow/README.md + constitution.md) as SessionStart additionalContext every session.
- **Actual:** Two independent failures: (1) workflow-shell has NO install record for Perplexity_MCP in installed_plugins.json (records exist only for scratchpad-priv, cooking, Swift_custom_coice_capture) and user-level enabledPlugins is {} — so the hook is never even registered for this project. (2) Even if it were, session-context.sh line 14 gates on `[ -f "$PROJ/.claude/active.json" ] || exit 0`; active.json is missing, so the hook would exit 0 silently. Net: contract never loads. No double-load risk (no copy-based files), but no load at all.
- **Evidence:** session-context.sh:14 `[ -f "$PROJ/.claude/active.json" ] || exit 0`. installed_plugins.json workflow-shell records list 3 projects, none of them Perplexity_MCP. ~/.claude/settings.json enabledPlugins: {}.

##### F11-2 — Secrets deny-list absent — real .env with PERPLEXITY_API_KEY is unprotected (only protection in crux)

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** .claude/settings.json permissions.deny
- **Scope:** /Users/rohitseelam/Projects/Perplexity_MCP/.env (PERPLEXITY_API_KEY)
- **Expected:** settings.json carries the workflow-init deny-list: Read/Edit/Write on ./.env, ./.env.*, plus Read on credentials.json and service-account*.json. This deny-list is the ONLY secrets protection in crux — there is no protect/guard hook anywhere.
- **Actual:** settings.json does not exist. The only settings file is settings.local.json with `permissions.deny: []` (empty) and no outputStyle. A live .env containing PERPLEXITY_API_KEY is present at repo root. Nothing — neither a deny-list nor any guard hook — prevents the agent from reading or rewriting the API key. Secret is fully exposed to tool calls.
- **Evidence:** settings.local.json => deny: [], outputStyle <none>. /Users/rohitseelam/Projects/Perplexity_MCP/.env exists (233B), first key PERPLEXITY_API_KEY. No settings.json present.

##### F18-0 — clipsight is completely unadopted — zero contract files, contract never loads

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** .claude/ (whole project)
- **Scope:** /Users/rohitseelam/Projects/seriesA/clipsight/.claude
- **Expected:** An adopted project has .claude/CLAUDE.md, active.json, workflow/queue.md, and settings.json (outputStyle + subagent wiring + deny-list), matching the reference project /Users/rohitseelam/Projects/seriesA/Swift_custom_coice_capture/.claude.
- **Actual:** The entire .claude/ tree is: .claude/.DS_Store, .claude/cowork/build_requirements.md, .claude/cowork/market_report.md. None of CLAUDE.md, active.json, workflow/, constitution, settings.json, settings.local.json, agents, or specs/ exist. The project has never been adopted; adoptionMode:none is correct.
- **Evidence:** find /Users/rohitseelam/Projects/seriesA/clipsight/.claude -type f returns only .DS_Store + the two cowork/*.md docs. No settings*.json files (glob no-match).

##### F18-3 — workflow-shell plugin not enabled for clipsight (no project enablement; user enabledPlugins is empty)

- **Severity:** high · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** enabledPlugins
- **Scope:** user ~/.claude/settings.json + clipsight project settings.json (absent)
- **Expected:** The plugin must be enabled for the contract to apply. The reference project enables it at PROJECT level: settings.json has enabledPlugins['workflow-shell@workflow-shell-marketplace']=true.
- **Actual:** User-level ~/.claude/settings.json has enabledPlugins:{} (empty) — the marketplace is a known marketplace but the plugin is enabled nowhere globally. clipsight has no project settings.json to enable it locally. So even if active.json were created by hand, the SessionStart hook would not run for clipsight because the plugin isn't active here. Adoption must both enable the plugin (project settings) AND seed active.json.
- **Evidence:** ~/.claude/settings.json: enabledPlugins:{}. Reference Swift_custom_coice_capture/.claude/settings.json: enabledPlugins['workflow-shell@workflow-shell-marketplace']=true. clipsight has no settings.json.

##### F15-3 — Missing per-project state files (CLAUDE.md, active.json, workflow/queue.md) — no workflow state machine

- **Severity:** medium · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** per-project seeded files
- **Scope:** spec lifecycle, queue/backlog, project identity doc
- **Expected:** /workflow-init seeds .claude/CLAUDE.md (project + 'runs workflow-shell' doc), .claude/active.json ({active,queued,archived,prds} arrays), and .claude/workflow/queue.md (brainstorming pad).
- **Actual:** None of these exist in RAG. No CLAUDE.md (find returns nothing), no active.json, no workflow/ dir, no queue.md, no specs/. The project has no workflow state surface whatsoever.
- **Evidence:** `find RAG -iname CLAUDE.md` empty; `find RAG -name active.json` empty; `.claude/` contains only agents/ and settings.local.json.

##### F18-2 — No secrets deny-list — secrets completely unprotected (deny-list is the ONLY protection in crux)

- **Severity:** medium · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** settings.json permissions.deny
- **Scope:** /Users/rohitseelam/Projects/seriesA/clipsight/.claude/settings.json (absent)
- **Expected:** settings.json carries permissions.deny covering Read/Edit/Write of ./.env, ./.env.*, ./credentials.json, ./service-account*.json (8 entries, per workflow-init PATCH and the reference project).
- **Actual:** clipsight has no settings.json at all, so hasSecretsDeny:false and there is zero secrets protection. There is NO protect/guard hook anywhere in the plugin — the only hook is SessionStart (read-only context injection) — so the settings deny-list is the sole mechanism, and it is absent. Any .env/credentials the clipsight hardware/cloud project later adds would be fully readable/writable by the agent.
- **Evidence:** No settings*.json in clipsight/.claude (glob no-match). Plugin hooks dir contains only session-context.sh; hooks.json registers only SessionStart. workflow-init PATCH (commands/workflow-init.md line 91) is the only place the 8-entry deny list is defined.

##### F9-5 — No stale copy-based contract duplicates present (negative finding — no double-load risk)

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** .claude/agents, .claude/workflow, .claude/commands, constitution.md (copy-based artifacts)
- **Scope:** Rules out the copy-vs-plugin conflict / double-load failure mode for this project.
- **Expected:** Either a clean plugin-based adoption (no copied agents/commands/constitution) OR, if legacy copy-based, those files would need removal to avoid conflicting with the plugin.
- **Actual:** No copy-based duplicates exist: no .claude/agents, .claude/commands, .claude/workflow, .claude/output-styles, or a copied constitution.md. The only risk is non-load (nothing seeded), not double-load. Clean slate for workflow-init.
- **Evidence:** `ls .claude/agents|workflow|specs|commands|output-styles` all -> No such file or directory. Root CLAUDE.md absent.

##### F14-0 — Workflow-shell contract entirely absent — project is fully un-adopted (adoptionMode: none confirmed)

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** whole contract (CLAUDE.md, active.json, workflow/, constitution.md, settings.json outputStyle, specs/)
- **Scope:** /Users/rohitseelam/Projects/LangGraph/langchain-academy/.claude/
- **Expected:** If this project were intended to run the workflow shell, /workflow-init would have seeded CLAUDE.md (with the workflow-shell pointer block), active.json, workflow/queue.md, and merged settings.json (outputStyle + subagent wiring + secrets deny-list).
- **Actual:** None of these exist. The .claude/ dir contains only settings.local.json and bespoke study assets (agents/web_researcher.md, agents/perplexity_researcher.md, commands/{resume_study,update_sessionlog_and_notes,invoke_websearch_agent,invoke_perplexity_research_agent}.md). No CLAUDE.md anywhere (not at .claude/ nor repo root). Verified missing: CLAUDE.md, active.json, workflow/, constitution.md, specs/, settings.json.
- **Evidence:** find on .claude/ returns exactly 7 files: settings.local.json, 2 agents, 4 commands. `ls .claude/{active.json,settings.json,constitution*,workflow,specs}` all return NO/no matches.

##### F15-2 — No secrets deny-list anywhere — secrets are completely unprotected

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** .claude/settings.json permissions.deny
- **Scope:** all secret files (.env, .env.*, credentials.json, service-account*.json) in the RAG tree
- **Expected:** /workflow-init merges a permissions.deny block into .claude/settings.json: Read/Edit/Write on ./.env, ./.env.*, ./credentials.json, ./service-account*.json. Since there is NO protect/guard hook anywhere in crux, this settings deny-list is the ONLY protection for secrets.
- **Actual:** RAG has no settings.json at all — only settings.local.json, which contains a single allow entry (mcp__perplexity-mcp__perplexity_large) and an empty deny array. No deny-list exists. The sole secrets-protection mechanism is entirely absent.
- **Evidence:** `ls .claude/settings.json` => NO settings.json. settings.local.json deny:[] (empty). workflow-init.md line 91 PATCH defines the deny entries that would be merged.

##### F15-6 — No plugin version stamp recorded in the project (no record of which contract version is/was adopted)

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** confirmed
- **Component:** version provenance
- **Scope:** future refresh/repackage auditing
- **Expected:** An adopted project should carry a record (e.g., in CLAUDE.md or active.json) of the workflow-shell version adopted (currently 0.1.0) so future refreshes can detect contract drift.
- **Actual:** RAG records nothing — no CLAUDE.md, no active.json, no version marker. Even the plugin install records version 0.1.0 only globally in cache, not pinned per-project. If/when RAG is adopted, there is currently no version-stamp mechanism in the seed (workflow-init.md seeds CLAUDE.md without a version line).
- **Evidence:** plugin.json version 0.1.0; workflow-init.md CLAUDE.md template (lines 27-53) contains no version field; RAG has no CLAUDE.md at all.

##### F16-0 — workflow-shell contract entirely absent — project runs a parallel hand-rolled workflow system, never adopted

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** whole contract (active.json, workflow/, constitution, settings.json outputStyle+subagent wiring, specs/)
- **Scope:** Entire project workflow layer
- **Expected:** If this project is meant to run on the workflow-shell, /workflow-init should have seeded CLAUDE.md (workflow header), .claude/active.json, workflow/queue.md, constitution.md, and merged settings.json (outputStyle + subagent wiring + secrets deny-list).
- **Actual:** Zero workflow-shell footprint. grep for 'workflow-shell|workflow-init|constitution|active.json' across .claude/ returns nothing. CLAUDE.md is a bespoke 'Project Nakashima' template with no 'Workflow shell' section. The project instead runs its own custom system: .claude/commands/{start_session,end_session,start_workflow_improvement,sync_prd,sync_implementation_plan,...} and a project_context/ tree (project_logs/session_logs, product_requirement_documents/prd, subagent_memories). adoptionMode:none is accurate.
- **Evidence:** /Users/rohitseelam/Projects/Multi Agent/Multi Agent Pilot/CLAUDE.md (title '# Project Nakashima', no workflow section); .claude/commands/start_session.md (custom PRD/session-log loader); grep 'workflow-shell|active.json' over .claude/ = empty

##### F19-0 — Workflow-shell contract entirely absent — project was never adopted (adoptionMode: none)

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** .claude/ (whole project)
- **Scope:** Entire workflow contract for the Apple notes project
- **Expected:** An adopted project mirrors the host reference: settings.json carries enabledPlugins.workflow-shell@workflow-shell-marketplace + outputStyle 'Workflow Orchestrator' + subagents wiring + permissions.deny; on disk it has CLAUDE.md, active.json, and workflow/queue.md.
- **Actual:** Verified /Users/rohitseelam/Projects/seriesA/Apple notes/.claude/ contains ONLY settings.json with {"enabledPlugins":{"apple-notes@apple-notes-mcp":true}}. No CLAUDE.md, no active.json, no workflow/, no constitution, no outputStyle, no subagents, no permissions block. find confirms zero contract artifacts anywhere under the project.
- **Evidence:** ls /Users/rohitseelam/Projects/seriesA/Apple notes/.claude/ -> settings.json only (70 bytes). find for constitution*/active.json/CLAUDE.md/queue.md/state.json -> no matches. find for specs/workflow/agents dirs -> none.

#### Temporal findings (7)

##### F0-4 — Verifier permissionMode fix (spec 053, 2026-06-19) not in plugin — shipped verifiers stall on per-call permission prompts

- **Severity:** high · **Fix target:** repackage · **Verdict:** confirmed
- **Component:** agents/review/spec-verifier.md, plan-verifier.md, task-verifier.md
- **Scope:** spec/plan/task verify gates in every adopting project (the three Haiku verifiers)
- **Expected:** Per canonical spec 053 (landed 2026-06-19, AFTER the 06-17 packaging), the three Haiku verifier agents set permissionMode: bypassPermissions so they no longer stall on a per-call permission prompt during autonomous verification.
- **Actual:** The plugin ships the OLD version: spec-verifier.md line 5 reads permissionMode: default. The plugin DOES ship these agent files, so this is a concrete, file-level temporal regression — the packaged verifiers carry the exact bug spec 053 fixed and will stall under the same conditions. Invisible precisely because there is no provenance stamp (finding above).
- **Evidence:** Canonical spec-verifier.md:5 = 'permissionMode: bypassPermissions'; plugin spec-verifier.md:5 = 'permissionMode: default'. Commit 382fc7e (2026-06-19) changed all three review/*-verifier.md from default to bypassPermissions; commits are after the marketplace's 2026-06-17 packaging.

##### F0-3 — No provenance stamp ties the plugin (v0.1.0) to a canonical commit — temporal drift is structurally invisible

- **Severity:** medium · **Fix target:** repackage · **Verdict:** partial
- **Component:** .claude-plugin/plugin.json + marketplace.json + README
- **Scope:** Every consumer; all future re-packaging/audit
- **Expected:** The package should record which canonical commit/sha it was cut from (e.g. a packaged-from / source-sha / canonical-commit field in plugin.json or marketplace.json), so a consumer or auditor can compute how far behind canonical the plugin is.
- **Actual:** ABSENT everywhere. plugin.json carries version 0.1.0 but no source field; a grep for packaged-from/provenance/canonical-sha/source-commit/generated-from across the whole marketplace repo returns zero packaging stamps (only an unrelated prose hit in rules/tests.md). Nothing records that the package corresponds to canonical state circa 2026-06-17 (~spec 051). Because canonical lands ~19 commits/week through spec 053+, drift accrues daily and is undetectable from the package's own contents — you cannot tell the plugin is stale without manually diffing two repos.
- **Evidence:** plugin.json has name/version/description/author/keywords/license only, no provenance. Marketplace repo has 2 commits both 2026-06-17. Canonical HEAD is 5728ab9 (spec 053, 2026-06-19) with 12+ .claude/ commits after the packaging date.

##### F0-5 — shell-audit dynamic-workflow (spec 052, 2026-06-18) absent from plugin

- **Severity:** low · **Fix target:** repackage · **Verdict:** partial
- **Component:** dynamic-workflows/shell-audit.md
- **Scope:** Recurring strategic shell-review capability; queue-filing cadence
- **Expected:** Canonical ships .claude/dynamic-workflows/shell-audit.md (spec 052, landed 2026-06-18 after packaging): a saved re-invocable read-only strategic shell-review mechanism (5-dimension fan-out + adversarial skeptic pass + ranked queue-ready findings). Shipped workflow/README.md/phases.md describe the shell-audit recurring-review contract.
- **Actual:** The plugin has NO dynamic-workflows/ directory at all. The mechanism and its run directory are absent, while contract docs that reference the shell-audit cadence may still ship — a capability documented-but-undelivered, added to canonical one day after the package was cut.
- **Evidence:** Plugin has no dynamic-workflows/ dir (ls returns nothing). Canonical commit 480e591 (2026-06-18) 'shell-audit strategic review mechanism'. Canonical .claude/dynamic-workflows/shell-audit.md exists.

##### F3-0 — No plugin version stamp recorded anywhere in the project — adopted version is invisible to the project itself

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** version provenance / adoption record
- **Scope:** .claude/ (no file records adopted plugin version or commit)
- **Expected:** The project should carry a record of which workflow-shell version/commit it was adopted against (e.g. a stamp in active.json, CLAUDE.md, or a dedicated adoption marker), so drift between the project and a newer plugin can be detected and a re-init/refresh can be triggered deterministically.
- **Actual:** grep across the entire project .claude/ for version|0.1.0|adopted|gitCommit returns nothing. The ONLY record that this project adopted workflow-shell@0.1.0 (gitCommitSha 668c87ef...) lives in the global ~/.claude/plugins/installed_plugins.json, keyed by projectPath. The project is blind to its own contract version; if the plugin advances to 0.2.0 the project cannot tell it is stale.
- **Evidence:** installed_plugins.json record for projectPath /Users/.../Swift_custom_coice_capture: version 0.1.0, installedAt 2026-06-18T18:42:12Z, gitCommitSha 668c87ef5ef5d9ea9217e396f4226210c8e81834. Project .claude/ files (active.json, CLAUDE.md, settings.json) contain no version field.

##### F9-4 — No plugin version stamp recorded for this project

- **Severity:** low · **Fix target:** repackage · **Verdict:** partial
- **Component:** version provenance (CLAUDE.md / active.json)
- **Scope:** Auditability: cannot tell which workflow-shell version (if any) this project was adopted against.
- **Expected:** An adopted project carries a record (via seeded CLAUDE.md noting the plugin, plus active.json existence) tying it to a plugin version; installed plugin is workflow-shell 0.1.0.
- **Actual:** No CLAUDE.md, no active.json, no settings.json — therefore no version provenance at all. This is a consequence of never adopting, included for completeness; note the contract itself does not write an explicit semver stamp into per-project files, so even post-init the stamp is implicit.
- **Evidence:** find .claude -type f -> only settings.local.json. Installed version path: plugins/cache/workflow-shell-marketplace/workflow-shell/0.1.0/.

##### F12-3 — No version stamp recording which plugin version was (or would be) adopted

- **Severity:** low · **Fix target:** repackage · **Verdict:** partial
- **Component:** adoption provenance / version stamp
- **Scope:** /Users/rohitseelam/Projects/professional-workspace/.claude/
- **Expected:** An adopted project records the workflow-shell version it adopted (e.g. in CLAUDE.md or active.json) so refresh tooling can detect when the installed plugin (0.1.0) has drifted ahead.
- **Actual:** No version marker anywhere — neither workflow-init nor the plugin currently writes one even on adopted projects. Here it is moot because the project is unadopted, but it means there is no way to later tell which contract revision this project tracks.
- **Evidence:** plugin.json version 0.1.0; workflow-init.md seeds CLAUDE.md/active.json/queue.md with no version field; no stamp in professional-workspace .claude/.

##### F17-4 — No plugin version stamp anywhere — if Temp1 is ever adopted there is no record of which workflow-shell version it was seeded from

- **Severity:** low · **Fix target:** workflow-init · **Verdict:** partial
- **Component:** version provenance / adoption stamp
- **Scope:** provenance/audit
- **Expected:** A recorded adopted-plugin-version field seeded at init.
- **Actual:** No such field defined or present.
- **Evidence:** No active.json (would be the natural home for a version field); CLAUDE.md has no version reference; no manifest stamp found.

---

## 4. Failure classes (shared root cause)

The 55 findings collapse into **7 root-cause failure classes**. Each class is one systemic fix that retires every member finding at once; the `Primary fix target` names the chokepoint where that fix lands.

### 4.1 No provenance/version stamping — all drift is structurally invisible

- **Members (11):** F0-3, F2-0, F3-0, F8-4, F9-4, F11-3, F12-3, F13-4, F15-6, F17-4, F18-5
- **Primary fix target:** `multiple`
- **Shared root cause:** Nothing records which canonical commit the plugin was cut from, nor which plugin version a project was adopted against. plugin.json carries only name/version/description/author/keywords/license (verified: no source/packaged-from/canonical-sha field), and workflow-init seeds CLAUDE.md/active.json/queue.md/settings.json with no version stamp. The sole adoption record lives in the global ~/.claude/plugins/installed_plugins.json keyed by install, not inside any project. Consequence: neither a consumer nor an auditor can compute how far the package is behind canonical, nor whether a given project is stale — drift accrues daily and is undetectable from on-disk contents.
- **Recommended systemic fix:** Two-part stamp: (1) at PACKAGE time, write a provenance field into plugin.json/marketplace.json (e.g. source-commit/packaged-from-sha + canonical-spec) so the package self-describes its canonical lineage; (2) at ADOPT time, have workflow-init write an adopted-version stamp into a project file (active.json key or .claude/workflow/.workflow-version) recording the workflow-shell version/sha seeded against. A refresh check can then diff installed vs adopted and flag staleness deterministically.

### 4.2 Secrets protection is settings-only (guard hook dropped) and the deny-list is narrow, local-only, or absent

- **Members (12):** F0-0, F4-7, F7-2, F8-2, F11-2, F12-2, F13-3, F14-2, F15-2, F16-3, F16-4, F18-2
- **Primary fix target:** `multiple`
- **Shared root cause:** Canonical's protect-secrets.sh PreToolUse guard (which blocks exit-2 on .env*/credentials/service-account/SSH keys for BOTH file tools AND Bash via token-regex) was dropped from the plugin — verified: hooks.json registers only SessionStart->session-context.sh and no protect-secrets.sh ships. So the ONLY secrets mechanism is the settings.json deny-list, and that mechanism is structurally weak everywhere it appears: the seeded baseline is narrow (no SSH keys, *.pem, *.key, tokens, .aws, nested **/.env), it cannot gate Bash-arg contents (so `cat .env` bypasses it), it frequently lives only in the un-committed settings.local.json, broad allow(Read(*)/Write(*)/bare Bash) entries undercut it, and in unadopted projects it is missing entirely — leaving real .env files (YOUTUBE_API_KEY, PERPLEXITY_API_KEY, etc.) fully exposed to tool calls.
- **Recommended systemic fix:** Re-ship protect-secrets.sh as a registered PreToolUse guard hook (Read|Edit|Write|MultiEdit|Bash, exit-2 block, allow-list short-circuit for .env.example/.sample/.template) so a runtime backstop exists independent of settings; AND broaden the workflow-init deny-list baseline to cover the full secret surface (SSH keys, *.pem/*.key, **/.env family, .aws, *-key.json, tokens) and write it into the committed settings.json (not settings.local.json). Defense-in-depth: hook + committed deny-list, neither relying on the other.

### 4.3 Contract docs assert memory/SDK-pipeline invariants that are false in a crux-only install

- **Members (11):** F0-1, F0-2, F1-0, F1-1, F1-2, F1-3, F1-4, F1-5, F1-6, F1-7, F1-8
- **Primary fix target:** `contract-patch`
- **Shared root cause:** The constitution and workflow docs were authored for the FULL install (crux + the separate, unimplemented workflow-memory-pipeline plugin) but ship inside the crux-only package, asserting as standing facts a sole-writer SDK memory pipeline, a memory-write-guard.sh PreToolUse enforcement hook, active per-agent silos, populated MEMORY.md/topics stores, and a deliver-time memory commit — none of which exist in crux. Verified absent: memory-write-guard.sh, sdk-memory-pipeline.sh, sdk_memory_pipeline.py, and the workflow/sdk-pipeline.md doc that README/phases/migration point to (a dangling 404). Result: readers believe memory is captured and guarded at every deliver when in crux nothing writes it, Rule 5 is honor-system, cross-checker gates on mirror-compliance with no writer to comply, and migration onboarding seeds a mirror that is 'kept in sync' by a pipeline that isn't installed.
- **Recommended systemic fix:** Conditionalize every memory/pipeline assertion across constitution.md and workflow/{README,phases,evaluation,communication,artifacts,migration}.md + rules/migrations.md + routing.md on the workflow-memory-pipeline plugin being installed: state the crux-only reality explicitly (no writer, no guard, stores unpopulated, hygiene is manual/unmet), mark mirror-compliance and deliver memory-commit steps as plugin-conditional, and remove or gate dead pointers to sdk-pipeline.md / skills/memory/. (Alternatively, but larger: actually ship the pipeline+guard — repackage — to make the assertions true.)

### 4.4 Plugin package diverges from canonical — temporal regressions and selectively dropped files (repackage drift)

- **Members (3):** F0-4, F0-5, F0-7
- **Primary fix target:** `repackage`
- **Shared root cause:** The plugin was hand-cut from canonical circa 2026-06-17 and never re-synced, so post-cut canonical changes and file drops are baked in with no detection. Verified: the three Haiku review verifiers still carry permissionMode: default (spec 053's 2026-06-19 fix to bypassPermissions never landed — they will stall on per-call prompts); dynamic-workflows/ does not exist (spec 052 shell-audit, 2026-06-18, absent); and rules/ ships only general/claude-code/tests/migrations (backend-go.md and frontend-tsx.md dropped while the shipped backend/qa agents still assume Go/pytest). This is the same lineage gap as the provenance class, but here it manifests as concrete stale/missing files rather than a missing stamp.
- **Recommended systemic fix:** Establish a repeatable canonical->plugin packaging pipeline (scripted export of the .claude/ contract at a pinned commit) so re-cuts are reproducible and complete, then re-cut to pull in the verifier permissionMode fix, shell-audit dynamic-workflow, and reconcile the rules set (either re-ship stack rules or de-stack the agents to match). Pair with the provenance stamp so future divergence is detectable instead of invisible.

### 4.5 Projects never adopted the workflow-shell contract — contract is dark and never loads

- **Members (11):** F9-0, F9-5, F11-0, F11-1, F14-0, F15-3, F16-0, F16-2, F18-0, F18-3, F19-0
- **Primary fix target:** `workflow-init`
- **Shared root cause:** Multiple projects have a bare .claude/ (often only settings.local.json, or bespoke hand-rolled command/agent systems) — /workflow-init was never run, so there is no CLAUDE.md/active.json/workflow/queue.md/settings.json outputStyle. The contract is doubly dark: the plugin is not enabled at project level (user enabledPlugins is {}), and even if it were, session-context.sh gates on `[ -f .claude/active.json ] || exit 0`, so the SessionStart context-injection hook never fires without active.json. Net: zero workflow contract activates, regardless of the plugin being installed globally. (One negative member confirms no copy-based duplicates exist, so the risk is non-load, not double-load.)
- **Recommended systemic fix:** Run /workflow-init in each intended project to seed the four artifacts AND enable the plugin at project scope, so active.json exists and the SessionStart hook fires. For projects with a parallel hand-rolled workflow (Multi Agent Pilot), decide adopt-vs-keep explicitly rather than leaving both dark. Treat 'plugin enabled + active.json present' as the single adoption invariant to assert.

### 4.6 workflow-init leaves adoption half-activated / placeholder content unfinished

- **Members (3):** F3-1, F18-4, F18-6
- **Primary fix target:** `workflow-init`
- **Shared root cause:** Even where workflow-init runs, its seeding is incomplete and leaves manual follow-ups that are easily skipped: the settings PATCH merges outputStyle/subagents/permissions.deny but never sets enabledPlugins (so adoption needs a second out-of-band /plugin install or the SessionStart hook stays dark), the seeded CLAUDE.md ships verbatim placeholders ('<one-line description — EDIT THIS>', '- EDIT: languages...') that nobody fills so the orchestrator gets zero project signal, and pre-spec product docs (clipsight cowork/*.md PRDs) are never migrated into workflow/queue.md so they orphan after adoption.
- **Recommended systemic fix:** Make workflow-init self-activating and content-aware: add enabledPlugins to the settings PATCH so one command fully activates; prompt-for or detect-and-fill the CLAUDE.md description/Stack section (or flag it as a required post-init edit gate); and offer to sweep existing pre-spec product docs into queue.md Now/Next/Later during init so they enter the backlog rather than orphaning.

### 4.7 Local cruft and partial-migration debris in adopted projects (refresh cleanup)

- **Members (4):** F2-1, F3-2, F7-3, F17-5
- **Primary fix target:** `refresh`
- **Shared root cause:** Adopted/working projects accumulate stale or one-off artifacts that no periodic refresh prunes: archived specs 001/002 left on the legacy pre-plugin state.json schema during the 2026-06-18 migration (mismatch for any tool that reads all state.json uniformly), a one-shot python3 plugin-introspection Bash allow plus a malformed doubled-slash Read(//Users/...) pattern persisted into settings.local.json, a full duplicate of agents/ and commands/ inside a git worktree's .claude/ that will silently drift from the parent, and a TaskCompleted hook reminder pointing at a MEMORY.md that does not exist in the tree.
- **Recommended systemic fix:** Add a refresh/lint pass (e.g. extend workflow-status or a dedicated refresh skill) that: normalizes all state.json to the current schema or explicitly tags legacy-archived ones; strips one-off/debug permissions and malformed path patterns from settings.local.json; detects and de-duplicates contract copies inside worktrees (single source of truth); and prunes hook reminders whose target files are absent.

---

## 5. Deliverable 1 — `/workflow-init` hardening (idempotent patches)

Implementation-ready change-list for `/Users/rohitseelam/Projects/workflow-shell-marketplace/plugins/workflow-shell/commands/workflow-init.md`.

### Rationale

These changes close every **`workflow-init`/`multiple`**-targeted failure mode that makes *new* adoptions drift, without touching the `workflow-memory-pipeline` plugin:

- **Version/provenance stamp** (F3-0, F8-4, F13-4, F15-6, F17-4, F18-5, class *No provenance/version stamping*): write `.claude/workflow/.workflow-version` recording the installed plugin version + adoption timestamps, so refresh tooling can later diff installed-vs-adopted deterministically.
- **Secrets deny-list breadth + committed location** (F7-2, F8-2, F12-2, F14-2, F15-2, F18-2, class *Secrets protection is settings-only*): the deny-list is the *only* secret guard in crux (the `protect-secrets.sh` re-ship is a separate repackage deliverable), so the seeded baseline must be broad and land in committed `settings.json`.
- **Self-activation** (F18-4, class *half-activated adoption*): add `enabledPlugins` to the settings PATCH so one command fully activates the contract (active.json + plugin-enabled = the single adoption invariant for F9-0/F11-1/F18-3).
- **Placeholder + orphan-doc gates** (F3-1, F18-6): turn the post-run "edit CLAUDE.md" into a required gate and sweep pre-spec docs into `queue.md`.

All shell stays arg-safe (named vars only, no bare `$1`/`$ARGUMENTS`), every write is seed-if-absent or upsert, and the `settings.json` merge stays a non-destructive union.

---

### Change 1 — broaden the secrets deny-list and add `enabledPlugins` to the PATCH

**File:** `commands/workflow-init.md` · **Section:** step 4, line **91** (the `PATCH='…'` assignment).

Replace the single-line `PATCH='…'` with the broadened patch below (still one shell-safe single-quoted JSON string; no positionals). It adds `enabledPlugins`, nested `**/.env*` coverage, SSH keys, `*.pem`/`*.key`/`*-key.json`, `credentials`/`service-account` for Edit/Write (not just Read), and `.aws`/`.npmrc`/`.pypirc`:

```bash
PATCH='{"outputStyle":"Workflow Orchestrator","enabledPlugins":{"workflow-shell@workflow-shell-marketplace":true},"subagents":{"orchestrator":{"skills":["workflow-advance","workflow-rollback","workflow-status","workflow-new"]},"product-manager":{"skills":["workflow-advance"]},"task-decomposer":{"skills":["workflow-advance"]}},"permissions":{"deny":["Read(./.env)","Read(./.env.*)","Read(**/.env)","Read(**/.env.*)","Edit(./.env)","Edit(./.env.*)","Edit(**/.env)","Edit(**/.env.*)","Write(./.env)","Write(./.env.*)","Write(**/.env)","Write(**/.env.*)","Read(./credentials.json)","Read(**/credentials.json)","Edit(./credentials.json)","Edit(**/credentials.json)","Write(./credentials.json)","Write(**/credentials.json)","Read(./service-account*.json)","Read(**/service-account*.json)","Edit(./service-account*.json)","Edit(**/service-account*.json)","Write(./service-account*.json)","Write(**/service-account*.json)","Read(**/*-key.json)","Edit(**/*-key.json)","Write(**/*-key.json)","Read(**/*.pem)","Edit(**/*.pem)","Write(**/*.pem)","Read(**/*.key)","Edit(**/*.key)","Write(**/*.key)","Read(**/id_rsa)","Read(**/id_dsa)","Read(**/id_ecdsa)","Read(**/id_ed25519)","Edit(**/id_rsa)","Edit(**/id_dsa)","Edit(**/id_ecdsa)","Edit(**/id_ed25519)","Write(**/id_rsa)","Write(**/id_dsa)","Write(**/id_ecdsa)","Write(**/id_ed25519)","Read(**/.aws/**)","Edit(**/.aws/**)","Write(**/.aws/**)","Read(**/.npmrc)","Read(**/.pypirc)"]}}'
```

**No change needed to the jq/python merge bodies (lines 92–120)** — they already (a) deep-merge top-level objects non-destructively, so `enabledPlugins`/`subagents` *union* with any pre-existing keys, and (b) special-case `permissions.deny` as a `unique` set-union, so re-runs are idempotent and existing user deny entries are preserved.

> Add one line of prose under the merge block noting the two known limits (both owned by other deliverables, not this command): the deny-list **cannot gate Bash-arg reads** (`cat .env`) — that needs the `protect-secrets.sh` PreToolUse hook (repackage deliverable); and because `permissions.deny` wins over `allow`, a broad `Read(*)`/`Write(*)` in a project's `settings.local.json` does **not** defeat these entries. The `.env.example`/`.sample`/`.template` allow-list short-circuit is intentionally **not** expressed here (settings `deny` cannot negate) and is deferred to the runtime hook.

---

### Change 2 — seed the version/provenance stamp (new step 5)

**File:** `commands/workflow-init.md` · **Section:** insert a new block **after** the settings-merge `fi`/echo (current line **120**) and **before** `echo "--- done ---"` (line **121**).

Uses `python3` (already in `allowed-tools`) to read the installed plugin version from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` and **upsert** the stamp — first adoption version/time are preserved, `lastInit*` always refreshed. `${CLAUDE_PLUGIN_ROOT}` is an env var (arg-safe, same one `hooks.json`/agents already rely on):

```bash
# 5. Version stamp — record which workflow-shell version this project was adopted against,
#    so refresh tooling can later detect installed-vs-adopted drift. Upsert: keep first
#    adoptedVersion/adoptedAt; always refresh lastInitVersion/lastInitAt.
STAMP=.claude/workflow/.workflow-version
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
python3 - "$STAMP" "$PLUGIN_ROOT" <<'PY'
import json, sys, os, datetime
stamp, root = sys.argv[1], sys.argv[2]
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
ver = "unknown"
try:
    with open(os.path.join(root, ".claude-plugin", "plugin.json")) as fh:
        ver = json.load(fh).get("version", "unknown")
except Exception:
    pass
prev = {}
try:
    with open(stamp) as fh:
        prev = json.load(fh)
except Exception:
    pass
out = {
    "plugin": "workflow-shell@workflow-shell-marketplace",
    "adoptedVersion": prev.get("adoptedVersion", ver),
    "adoptedAt": prev.get("adoptedAt", now),
    "lastInitVersion": ver,
    "lastInitAt": now,
}
with open(stamp, "w") as fh:
    json.dump(out, fh, indent=2)
print("stamped .claude/workflow/.workflow-version (version %s)" % ver)
PY
```

Notes:
- A **dedicated dotfile** is used instead of an `active.json` key on purpose: `active.json`'s shape is asserted elsewhere as exactly the 4 arrays `{active,queued,archived,prds}` (F2-1, F15-3), so adding a version key there would break that assertion. `.claude/workflow/.workflow-version` keeps provenance out of the validated schema.
- If `${CLAUDE_PLUGIN_ROOT}` is empty or `plugin.json` is unreadable, the stamp records `"unknown"` rather than failing the run (the block is non-fatal; keep it out of the `set -e` failure path by relying on the `try/except`).

---

### Change 3 — make the CLAUDE.md edit a gate, sweep orphan docs, and assert the adoption invariant

**File:** `commands/workflow-init.md` · **Section:** post-engine numbered steps, lines **124–134**. Replace them with:

```markdown
After the engine runs:

1. **CLAUDE.md content gate (required).** Read `.claude/CLAUDE.md`. If it still contains the seed
   placeholders `<one-line description — EDIT THIS>` or `EDIT: languages, frameworks, entry points`,
   you MUST fill them now: set the one-line description and the `## Stack` section from the project
   (use the project-name argument for the heading/description if one was passed; otherwise infer the
   stack from the repo and confirm with the user). Do not report adoption complete while placeholders
   remain — CLAUDE.md loads into every session, so an unedited template gives the orchestrator zero
   project signal.

2. **Sweep pre-spec product docs into the queue (offer).** Look for existing product/PRD-stage docs
   not under the contract (e.g. `*requirements*.md`, `*prd*.md`, `cowork/*.md`, `docs/*roadmap*.md`).
   For any found, offer to add their slugs to `.claude/workflow/queue.md` under Now/Next/Later so they
   enter the backlog instead of orphaning. Never move/delete the source docs; only append slugs.

3. Report what was seeded vs. kept (from the echoes above), including the version stamp
   (`.claude/workflow/.workflow-version` → `lastInitVersion`).

4. Remind them: the `Workflow Orchestrator` output style binds at session start — run `/clear`
   (or reopen) to activate it. The SessionStart hook then injects the contract every session.

5. **Assert the adoption invariant** (the single check that the contract will actually load):
   - `.claude/CLAUDE.md` present and de-placeholdered,
   - `.claude/active.json` valid with the 4 arrays `{active,queued,archived,prds}`,
   - `.claude/workflow/queue.md` present,
   - `.claude/workflow/.workflow-version` present,
   - `.claude/settings.json` has `outputStyle: "Workflow Orchestrator"`,
   - `.claude/settings.json` has `enabledPlugins["workflow-shell@workflow-shell-marketplace"] = true`,
   - `.claude/settings.json` `permissions.deny` includes the secret patterns.
   If `enabledPlugins` is not set, the SessionStart hook never fires (active.json gate is moot) —
   the patch in step 4 now sets it, but verify it merged.
```

---

### Change 4 — refresh the front-matter description (optional, doc-accuracy)

**File:** `commands/workflow-init.md` · **Section:** front-matter, line **3**.

Update the `description` so the manifest reflects the new behavior:

```yaml
description: Adopt the workflow-shell contract into THIS project. Seeds CLAUDE.md, active.json, a blank queue.md, and a .workflow-version stamp, then MERGES settings.json (outputStyle + enabledPlugins self-activation + subagent wiring + a broad secrets deny-list). Idempotent — never clobbers existing files; merges/upserts instead of overwriting.
```

No `allowed-tools` change is required — the new stamp block reuses `Bash(python3:*)` (already listed); no `cat`/`date`/`find` is introduced into the shell block (timestamp comes from `datetime`, orphan-doc discovery in step 2 uses the model's own Read/Glob, not the restricted shell).

---

### Idempotency / safety summary

| Change | Re-run behavior |
|---|---|
| Broadened deny-list + `enabledPlugins` | `permissions.deny` merged as `unique` union; `enabledPlugins`/`subagents` deep-merged — existing keys preserved, no clobber. |
| Version stamp | Upsert: `adoptedVersion`/`adoptedAt` kept from prior run; `lastInitVersion`/`lastInitAt` refreshed. Non-fatal on missing plugin.json. |
| CLAUDE.md / active.json / queue.md | Unchanged seed-if-absent guards (lines 26, 58, 64). |
| Post-run gates | Read-only asserts + offers; never overwrite user content. |

All shell variables are named (`$STAMP`, `$PLUGIN_ROOT`, `$SETTINGS`, `$PATCH`, `$NAME`, `$TMP`); no bare positional is referenced. The `workflow-memory-pipeline` plugin is not referenced or modified anywhere in these changes.

---

## 6. Deliverable 2 — `workflow-refresh` plugin spec (project↔plugin drift reconciler)

> A **new, third plugin** in `workflow-shell-marketplace`. It does **not** adopt or re-init a project (that is `/workflow-init`). It **detects** and **repairs** drift between an *already-adopted* project's `.claude/` and the *currently installed* `workflow-shell` plugin — pulling improvements forward, idempotently, never clobbering project-owned state.
>
> Position in the supply chain: `canonical → (repackage) → plugin → (refresh) → project`. Refresh is the last hop. It always targets the **currently installed** plugin version, so it stays correct as the package moves.

---

### 0. Metadata

| Field | Value |
|---|---|
| Plugin name | `workflow-refresh` |
| Marketplace | `workflow-shell-marketplace` |
| Primary surface | `/workflow-refresh` (slash command) + `refresh` skill |
| Mode default | **dry-run** (report a plan; mutate nothing) |
| Apply gate | `--apply` (safe rules) / explicit flags for risky rules |
| Scope of mutation | project `.claude/` plugin-derived scaffolding + `settings*.json` merge + state normalization + cruft cleanup |
| Never touches | `active.json` contents, `specs/**` bodies, `queue.md` body, `CLAUDE.md` prose, user `allow` permissions |
| Resolves baseline from | the **installed** `workflow-shell` (via `installed_plugins.json` → cache), not a hard-coded version |

---

### 1. Command surface

#### 1.1 `/workflow-refresh [flags]`

A two-stage command: **inspect → report** by default, **inspect → report → repair → re-verify** under `--apply`.

```
/workflow-refresh                 # dry-run: full drift report + proposed plan, NO writes
/workflow-refresh --apply         # apply all SAFE+idempotent rules, then re-verify; print residual
/workflow-refresh --check         # CI mode: report + non-zero exit on any high/medium drift, NO writes
/workflow-refresh --only=R-SEC,R-STAMP        # run a subset of rules by id
/workflow-refresh --apply --migrate-state     # opt-in: also normalize legacy state.json (risky rule)
/workflow-refresh --apply --strip-cruft       # opt-in: prune debug perms / malformed patterns / orphan hooks
/workflow-refresh --json          # emit the machine-readable drift report (for tooling / subagents)
```

What it **inspects** (read-only, always):
1. Resolves the installed `workflow-shell` plugin: path, `version`, `gitCommitSha`, and provenance (`source-commit`/`canonical-spec` if the package carries them).
2. Reads the project version stamp `.claude/.workflow-version` (the adopted/last-refreshed marker).
3. Loads the **expected baseline** for that installed version (§4.2).
4. Runs every detector (§3) → a structured **drift report** (§2.4).

What it **reports** (dry-run): a per-rule plan — `rule id · class · severity · current vs expected · proposed action · touches-project-owned? · auto|manual`.

What it **repairs** (`--apply`): only rules marked `auto` and `safe`; risky rules require their explicit flag; `manual` rules are always report-only.

#### 1.2 Exit codes (for `--check` / subagent use)

| Code | Meaning |
|---|---|
| `0` | No drift (or `--apply` resolved all `auto` drift; no residual manual items) |
| `10` | Drift detected (dry-run / `--check`) — report only |
| `20` | `--apply` ran; **residual manual** items remain (placeholder CLAUDE.md, opt-in state migration, allow-list warnings) |
| `1` | Cannot proceed: project not adopted (no `active.json`) or installed plugin not resolvable |

> If the project is **not adopted** (no `.claude/active.json`), refresh **refuses and defers** to `/workflow-init` — it never adopts. (`adoptionMode: none` is out of scope.)

---

### 2. Detection

#### 2.1 Resolve the installed plugin (the moving target)

`resolve_plugin.py` resolves the **currently installed** `workflow-shell` for *this* project, in precedence order:

1. **`~/.claude/plugins/installed_plugins.json`** → key `workflow-shell@workflow-shell-marketplace` → record whose `projectPath == $CLAUDE_PROJECT_DIR` (else `scope:"user"`). Yields `installPath`, `version`, `gitCommitSha`, `installedAt`.
2. **Cache glob** fallback: `~/.claude/plugins/cache/workflow-shell-marketplace/workflow-shell/*` → highest semver dir.
3. **Sibling** fallback: `${CLAUDE_PLUGIN_ROOT}/../../workflow-shell/*` (both plugins share the marketplace cache).

From the resolved `$PLUGIN_ROOT` it reads `.claude-plugin/plugin.json` → `INSTALLED_VERSION`, and provenance fields `source-commit` / `canonical-spec` if present (absent today → report `provenance: unavailable`). This is the mechanism by which refresh **stays correct as the plugin moves**: the baseline is whatever the installed package declares, never a constant baked into refresh.

#### 2.2 Version stamp (the keystone)

Refresh introduces and maintains `.claude/.workflow-version` (JSON). It is the on-disk record that makes drift *detectable* (closes the entire "no provenance/version stamping" failure class — F0-3, F2-0, F3-0, F8-4, F9-4, F11-3, F12-3, F13-4, F15-6, F17-4, F18-5).

```jsonc
// .claude/.workflow-version  (written/updated by refresh; safe for workflow-init to seed too)
{
  "plugin": "workflow-shell@workflow-shell-marketplace",
  "adoptedVersion": "0.1.0",          // first seen at adopt/first-refresh (immutable once set)
  "adoptedSha": "668c87ef…",          // gitCommitSha at adopt time, if known
  "refreshedVersion": "0.2.0",        // installed version at last successful refresh
  "refreshedSha": "5728ab9…",
  "refreshedAt": "2026-06-26T12:00:00Z",
  "sourceCommit": "5728ab9…",         // canonical provenance copied from plugin.json, if present
  "refreshTool": "workflow-refresh@0.1.0",
  "rulesApplied": ["R-STAMP","R-SETTINGS","R-SEC"]   // audit trail of last apply
}
```

Drift signal: **stamp absent** → never refreshed (or pre-stamp adoption) → full reconcile recommended. **`refreshedVersion != INSTALLED_VERSION`** → plugin has moved → run the baseline diff.

#### 2.3 What gets compared

| Comparison | Source of truth (expected) | Project side (actual) |
|---|---|---|
| Plugin version / sha | resolved `$PLUGIN_ROOT` | `.workflow-version.refreshedVersion` |
| settings keys (outputStyle, subagents, enabledPlugins) | baseline `settings.expected.json` (§4.2) | `.claude/settings.json` |
| Secrets deny coverage | baseline `secrets.deny.json` (broadened superset) | union of `settings.json` + `settings.local.json` deny |
| Secrets hook present? | `$PLUGIN_ROOT/hooks/hooks.json` registers `protect-secrets.sh`? | (informational — repackage concern) |
| Copy-based duplicates | `$PLUGIN_ROOT` file inventory + `baseline/copy-artifacts.txt` | project `.claude/{workflow/*.md,agents,rules,constitution.md,skills/workflow*,output-styles}` |
| state.json schema | `baseline/state-schema.json` (current keys) | every `specs/*/state.json` |
| Placeholder content | literal seed strings | `.claude/CLAUDE.md` |
| Local cruft | known-cruft signatures | `.claude/settings.local.json`, orphan hook reminders |
| Memory/pipeline assertions | is `workflow-memory-pipeline` installed? | docs assert pipeline as standing fact (crux-only ⇒ dormant) |

#### 2.4 Drift report schema (`--json`)

```jsonc
{
  "project": "/abs/path",
  "adopted": true,
  "plugin": { "name":"workflow-shell", "version":"0.2.0", "sha":"…", "provenance":"5728ab9|unavailable" },
  "stamp":  { "present":true, "refreshedVersion":"0.1.0", "stale":true },
  "summary": { "high":1, "medium":2, "low":3, "clean":4 },
  "findings": [
    {
      "rule":"R-SEC", "class":"secrets-protection", "severity":"high",
      "status":"drift",                       // clean | drift | manual | info
      "current":["Read(./.env)", "..."],
      "expected":["Read(./.env)","Read(./.env.*)","Read(./**/.env)","Read(./*.pem)","Read(./id_rsa)","..."],
      "action":"union missing deny entries into .claude/settings.json",
      "touchesProjectOwned":false, "mode":"auto-safe",
      "findingRefs":["F0-0","F4-7","F8-2","F11-2","F12-2","F13-3","F16-3"]
    }
  ],
  "exit": 10
}
```

---

### 3. Repair rules

**Invariants for every rule (enforced by `repair.py`):**
- **Idempotent** — re-running with no upstream change is a no-op (each rule has an idempotency key / converged predicate).
- **Additive-merge only** for settings — union/insert-missing; never delete or overwrite a user-set value.
- **Project-owned content is read-only** — `active.json` contents, `specs/**` bodies, `queue.md` body, `CLAUDE.md` prose, and user `allow` permissions are **never** auto-written; drift there is reported as `manual`.
- **Byte-match gate for deletions** — a "stale copy" is removed only if it byte-matches the installed plugin's file (or is on the recognized plugin-artifact inventory). Otherwise it is reported, not deleted.
- Every mutation is journaled into `.workflow-version.rulesApplied`.

#### 3.1 Repair-rule table

| Rule id | Drift class (failure class) | Detector | Repair action | Default mode | Touches project-owned? | Idempotency key | Finding refs |
|---|---|---|---|---|---|---|---|
| **R-STAMP** | No provenance/version stamp | `.workflow-version` absent or `refreshedVersion != INSTALLED_VERSION` | Write/update `.claude/.workflow-version` with installed version+sha+provenance; set `adoptedVersion` once if missing | **auto-safe** (always, even in `--apply` of any rule) | no | stamp == installed version | F0-3,F2-0,F3-0,F8-4,F9-4,F11-3,F12-3,F13-4,F15-6,F17-4,F18-5 |
| **R-SETTINGS** | Half-activated adoption (settings keys evolved) | `settings.json` missing/`outputStyle`≠expected, subagents wiring missing, **`enabledPlugins` unset** | Deep-merge expected PATCH: set missing keys; add `enabledPlugins["workflow-shell@…"]=true` (self-activation); never overwrite a user-set `outputStyle` unless it equals a prior default | **auto-safe** | no | settings ⊇ expected keys | F18-4, F3-1(partial), F16-2 |
| **R-SEC** | Secrets protection narrow/local/absent | union(settings.json+local deny) ⊉ broadened baseline; deny lives only in `settings.local.json`; broad `allow` wildcards present | **Union** broadened deny set into committed `settings.json` (SSH keys `id_rsa/id_ed25519/id_ecdsa`, `*.pem`, `*.key`, `**/.env`+family, `.aws/**`, `*-key.json`, `credentials.json`, `service-account*.json`, tokens); **migrate** deny rules from `settings.local.json`→`settings.json` (de-dupe) | **auto-safe** | no | committed deny ⊇ baseline | F0-0,F4-7,F7-2,F8-2,F11-2,F12-2,F13-3,F14-2,F15-2,F16-3,F18-2 |
| **R-SEC-ALLOW** | Broad allow undercuts deny | `allow` contains `Read(*)`/`Write(*)`/bare `Bash` | **Warn only** (cannot safely narrow user intent) — recommend scoping | **manual** | no (warn) | n/a | F16-4 |
| **R-SEC-HOOK** | Guard hook dropped from package | `$PLUGIN_ROOT/hooks/hooks.json` has no `protect-secrets.sh` PreToolUse | **Info**: installed package lacks runtime guard; deny-list is sole defense; recommend upgrading `workflow-shell` (repackage deliverable) | **info** | no | n/a | F0-0 (repackage) |
| **R-COPY** | Stale copy-based duplicates | project `.claude/` holds plugin-owned copies (`workflow/{README,phases,routing,artifacts,communication,evaluation,migration}.md`, `workflow/templates`, `agents/`, `rules/`, `constitution.md`, `skills/workflow*`, `output-styles/`) | Report exact `rm` set; under `--apply` delete **only byte-matched / inventory-recognized** plugin artifacts; keep `CLAUDE.md`, `active.json`, `queue.md`, `specs/`, `settings*.json` | **auto-safe** (matched only); divergent copies → `manual` | no (only plugin copies) | project has no plugin-owned file | F7-3 (+ README migration step) |
| **R-WORKTREE** | Duplicated `.claude/` inside git worktree | `.git` gitdir points to a worktree AND `.claude/{agents,commands}` duplicated | **Warn only** (worktree may hold active work) — report de-dup recommendation | **manual** | no (warn) | n/a | F7-3 |
| **R-STATE** | Legacy `state.json` schema (partial migration) | `state.json` missing `started/active/tags/phase_history` or carries legacy `created`/non-schema `complexity` | Non-destructive normalize: add missing keys (map `created`→`started`, keep original), tag `legacy-archived`; **never drop user fields**; only on `--migrate-state` | **opt-in** (`--migrate-state`) | yes (state is project-owned) → gated | schema ⊇ required keys | F2-1 |
| **R-CRUFT** | Local debug/cruft permissions | malformed `Read(//Users/…)` doubled-slash; one-off `Bash(python3 -c "…plugin…market…")` introspection allow | Strip patterns matching known-cruft signature from `settings.local.json` | **opt-in** (`--strip-cruft`) | no | no cruft-signature entries | F3-2 |
| **R-ORPHAN-HOOK** | Hook reminder points at absent file | `TaskCompleted`/other hook references `MEMORY.md` and `find` shows no such file | Prune the orphaned reminder entry | **opt-in** (`--strip-cruft`) | yes (settings) → gated | referenced target exists or entry gone | F17-5 |
| **R-CLAUDEMD** | Placeholder CLAUDE.md | literal `<one-line description — EDIT THIS>` / `- EDIT: languages…` | **Flag as required manual edit** (optionally prompt for one-liner) — never auto-author prose | **manual** | yes → report only | n/a | F3-1 |
| **R-MEM-DOC** | Memory/pipeline asserted but crux-only | `workflow-memory-pipeline` **not** installed AND installed docs assert pipeline/guard as standing fact | **Info**: pipeline dormant; Rule 5 honor-system; memory not written at deliver; recommend installing companion plugin or upgrading docs (contract-patch deliverable) | **info** | no | n/a | F0-1,F0-2,F1-0..F1-8 |

#### 3.2 Apply ordering

`R-STAMP` runs **last** on every `--apply` (so the stamp records the post-repair installed version only after repairs converge). Order: `R-COPY` → `R-SETTINGS` → `R-SEC` → opt-in (`R-STATE`,`R-CRUFT`,`R-ORPHAN-HOOK`) → re-verify → `R-STAMP`.

---

### 4. Staying correct as the plugin moves

Refresh is the **project↔plugin reconciler**; it never hard-codes "the right answer." Correctness is preserved by three mechanisms:

#### 4.1 Target = currently installed plugin
Baseline is always derived from the resolved `$PLUGIN_ROOT` (§2.1) — i.e. whatever version is installed *right now* for this project. When the user upgrades `workflow-shell`, the very next `/workflow-refresh` compares against the new package automatically, and the version stamp records the new `refreshedVersion`.

#### 4.2 Baseline precedence (forward-compatible)
The "expected" baseline for the comparisons in §2.3 is loaded by `baseline.py` in this order, first hit wins:

1. **`$PLUGIN_ROOT/baseline/{settings.expected.json, secrets.deny.json, copy-artifacts.txt, state-schema.json}`** — *authoritative.* The repackage deliverable is expected to add these data files so the plugin self-describes what an adopted project should look like. As the plugin evolves, refresh consumes the plugin's own declaration with zero refresh changes.
2. **Extract from `$PLUGIN_ROOT/commands/workflow-init.md`** — parse the `PATCH='…'` literal (deterministic marker). Works against today's `0.1.0` package that ships no `baseline/`.
3. **Refresh's bundled `baseline/` defaults** — last resort, and the *only* source for the **broadened** secrets superset (since the installed PATCH is narrow today). Refresh applies `union(installed-expected, refresh-broadened)` for `R-SEC`, giving defense-in-depth even on old packages, while never removing anything.

#### 4.3 Provenance pass-through
If the installed `plugin.json` carries `source-commit`/`canonical-spec` (added by repackage), refresh copies it into the stamp and surfaces "installed plugin packaged from canonical `<sha>` (spec NNN)" in the report — making temporal drift visible end-to-end. If absent, it reports `provenance: unavailable`, itself a (low) finding nudging the repackage fix.

---

### 5. Plugin file layout + marketplace registration

#### 5.1 Layout

```
plugins/workflow-refresh/
├── .claude-plugin/
│   └── plugin.json
├── README.md
├── commands/
│   └── workflow-refresh.md          # slash command: orchestration prose + bash invocation of the engine
├── baseline/                        # refresh-owned fallback baselines (precedence #3, §4.2)
│   ├── secrets.deny.json            # the BROADENED superset deny-list
│   ├── settings.expected.json       # outputStyle + subagents + enabledPlugins shape
│   ├── copy-artifacts.txt           # plugin-owned relative paths that are "stale" if found in project
│   └── state-schema.json            # current state.json required keys
└── skills/
    └── refresh/
        ├── SKILL.md                 # lets the orchestrator invoke refresh programmatically
        └── _scripts/
            ├── resolve_plugin.py    # §2.1 — resolve installed workflow-shell path/version/sha/provenance
            ├── baseline.py          # §4.2 — load expected baseline (plugin → init-extract → bundled)
            ├── detect.py            # §3 detectors → drift report JSON (§2.4)
            ├── repair.py            # apply rules by id (idempotent; mode gating; journaling)
            └── stamp.py             # read/write .claude/.workflow-version
```

#### 5.2 `plugin.json` (with provenance fields — leads by example)

```jsonc
{
  "name": "workflow-refresh",
  "version": "0.1.0",
  "description": "Detect and repair drift between an adopted project's .claude/ and the currently installed workflow-shell plugin. Dry-run by default; idempotent; never clobbers project-owned state.",
  "author": { "name": "Rohit Seelam", "email": "rohitseelam09@gmail.com" },
  "keywords": ["workflow", "refresh", "drift", "reconcile", "adoption", "upgrade"],
  "license": "MIT",
  "source-commit": "<canonical-sha>",     // provenance stamp (the gap this whole effort closes)
  "canonical-spec": "<NNN-workflow-refresh>"
}
```

#### 5.3 `marketplace.json` — add third plugin entry

```jsonc
{
  "plugins": [
    { "name": "workflow-shell",          "source": "./plugins/workflow-shell",          "category": "workflow" },
    { "name": "workflow-memory-pipeline","source": "./plugins/workflow-memory-pipeline","category": "workflow" },
    {
      "name": "workflow-refresh",
      "description": "Drift reconciler: detect & repair divergence between an adopted project and the installed workflow-shell. Dry-run first, then /workflow-refresh --apply. Does not adopt (use /workflow-init).",
      "source": "./plugins/workflow-refresh",
      "category": "workflow"
    }
  ]
}
```

Marketplace README: add a row to the Plugins table and a short "Keeping an adopted project current" section pointing at `/workflow-refresh` (dry-run) → `--apply`.

---

### 6. Command body sketch — `commands/workflow-refresh.md`

```markdown
---
name: workflow-refresh
description: Detect and repair drift between this adopted project's .claude/ and the currently installed workflow-shell plugin. Dry-run by default; --apply to repair. Idempotent; never clobbers project-owned state.
argument-hint: "[--apply] [--check] [--json] [--only=R-..] [--migrate-state] [--strip-cruft]"
allowed-tools: Bash(python3:*), Bash(test:*), Bash(jq:*), Bash(find:*), Bash(mktemp:*), Bash(mv:*), Bash(rm:*), Read
---

# Refresh the workflow shell in this project

Reconciles the project against the **currently installed** workflow-shell. It does NOT adopt — if the
project is unadopted, it stops and tells you to run `/workflow-init`. Default run is **dry-run** (no writes).

> Arg-substitution safety: this block uses named shell vars only; flags are read in prose and passed to the
> engine via an env var the orchestrator sets (FLAGS), never a bare `$1`.

```bash
set -e
SKILLS="${CLAUDE_PLUGIN_ROOT}/skills/refresh/_scripts"
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
FLAGS="${WORKFLOW_REFRESH_FLAGS:-}"          # e.g. "--apply" / "--check" / "--migrate-state"

# 0. Guard: must be adopted.
if [ ! -f "$PROJ/.claude/active.json" ]; then
  echo "NOT ADOPTED: no .claude/active.json. Run /workflow-init first (refresh does not adopt)."; exit 1
fi

# 1. Resolve installed plugin (path/version/sha/provenance) -> JSON on stdout.
PLUGIN_JSON="$(python3 "$SKILLS/resolve_plugin.py" --project "$PROJ")" || { echo "Cannot resolve installed workflow-shell"; exit 1; }

# 2. Detect: emit the drift report (reads stamp + baseline + project).
REPORT="$(python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON")"

# 3. Dry-run / check / json: print and exit on report's own exit code.
case " $FLAGS " in
  *" --json "*)  printf '%s\n' "$REPORT"; exit "$(printf '%s' "$REPORT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["exit"])')";;
  *" --apply "*) : ;;                       # fall through to repair
  *)             python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON" --pretty
                 exit "$(printf '%s' "$REPORT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["exit"])')";;
esac

# 4. Apply: idempotent repairs, mode-gated. Risky rules only with their flag. R-STAMP runs last.
python3 "$SKILLS/repair.py" --project "$PROJ" --plugin "$PLUGIN_JSON" --report "$REPORT" $FLAGS

# 5. Re-verify and write/refresh the version stamp.
python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON" --pretty
python3 "$SKILLS/stamp.py"  --project "$PROJ" --plugin "$PLUGIN_JSON"
echo "--- refresh done ---"
```

After the engine runs:

1. In **dry-run**, summarize the plan grouped by severity; call out `manual` items (placeholder CLAUDE.md,
   broad allow wildcards, optional state migration) the user must decide on.
2. In **`--apply`**, report repaired vs residual; if residual `manual` items remain, exit was 20 — list them.
3. If the installed package lacks a provenance stamp or the secrets guard hook, note it as an upstream
   (repackage) recommendation — refresh fixed the project side; the package fix is separate.
```

---

### 7. Engine sketches

#### 7.1 `resolve_plugin.py` (target = installed version)
```python
# precedence: installed_plugins.json(projectPath) -> cache glob latest semver -> CLAUDE_PLUGIN_ROOT sibling
# returns {"root","version","sha","provenance","memoryPipelineInstalled":bool}
```

#### 7.2 `baseline.py` (forward-compatible expected baseline)
```python
# 1) $root/baseline/*.json  (authoritative, future)
# 2) parse PATCH='...' from $root/commands/workflow-init.md (works on 0.1.0)
# 3) bundled ${CLAUDE_PLUGIN_ROOT}/baseline/*  (refresh defaults; broadened secrets superset)
# R-SEC expected = union(installed_expected_deny, bundled_broadened_deny)   # never subtract
```

#### 7.3 `repair.py` safety contract
- Settings writes go through the **same deep-merge** semantics as `workflow-init` (union `permissions.deny`, set-missing keys) — proven idempotent there.
- Deletions (`R-COPY`) gated on `filecmp`/sha byte-match against `$PLUGIN_ROOT`; divergent → downgrade to `manual`.
- `R-STATE` / `R-ORPHAN-HOOK` mutate project-owned files → require explicit flag; write through a temp file + `mv`; preserve all original keys.
- Each applied rule appended to `.workflow-version.rulesApplied`; converged predicate re-checked so a second run is a no-op.

---

### 8. Acceptance / test plan

| # | Scenario | Expected |
|---|---|---|
| 1 | Reference adopted project (Swift_custom_coice_capture), plugin unchanged | dry-run: only `R-STAMP` (stamp absent) + `R-SEC` (narrow baseline) + `R-CLAUDEMD` (placeholder); exit 10 |
| 2 | Same, `--apply` | stamp written, deny broadened, placeholder reported as residual `manual`; exit 20; re-run ⇒ exit 0 except CLAUDE.md (still manual) |
| 3 | Unadopted project (clipsight) | exit 1, "run /workflow-init"; no writes |
| 4 | Copy-adopted legacy project with `.claude/workflow/phases.md` etc. byte-matching plugin | `R-COPY` lists exact `rm` set; `--apply` removes only matched copies; project files untouched |
| 5 | Legacy `state.json` (specs 001/002) | `R-STATE` reported; only `--migrate-state` mutates; original keys preserved; archived note tagged |
| 6 | `settings.local.json` with `Read(//Users/…)` + python3 introspection allow | `R-CRUFT` reported; `--strip-cruft` removes only signature matches |
| 7 | Plugin upgraded `0.1.0→0.2.0` between runs | stamp `stale:true`; baseline taken from new `$PLUGIN_ROOT`; new keys reconciled; stamp updated |
| 8 | Idempotency | second `--apply` with no upstream change ⇒ no file mtime changes, exit 0 |
| 9 | `--check` in CI on drifted project | non-zero (10), no writes |

---

### 9. Open questions / hand-offs

- **Baseline ownership.** Ideal end state: the **repackage** deliverable ships `$PLUGIN_ROOT/baseline/*` and the provenance fields in `plugin.json`; refresh then needs no bundled fallback. Until then refresh carries defaults (§4.2 #3). Decide whether `workflow-init` should also write the initial stamp (so refresh only *updates* it) — recommended, and harmless if both write it (idempotent).
- **`R-SEC` superset scope.** Confirm the broadened deny set (SSH keys, `*.pem/*.key`, `**/.env`, `.aws`, `*-key.json`, tokens) — it intentionally exceeds today's narrow plugin PATCH; it is union-only so it can never weaken an existing config.
- **Worktree de-dup (`R-WORKTREE`)** stays `manual` by design (a worktree may hold active divergent work); revisit if a safe single-source-of-truth rule emerges.
- **Memory-doc drift (`R-MEM-DOC`)** is reported as `info` only — the real fix is the contract-patch/repackage deliverable, not project-side.

---

## 7. Deliverable 3 — repackage / version-stamp spec (canonical→plugin re-sync)

**Spec type:** feature (tooling) · **Target repo:** `/Users/rohitseelam/Projects/workflow-shell-marketplace` · **Source of truth (canonical):** `/Users/rohitseelam/Projects/scratchpad-priv/.claude` · **Owner:** maintainer (single-author) · **Status:** ready-to-build

> Deliverable 3 of 4. Sibling deliverables: (1) `protect-secrets` re-ship + deny-list broadening, (2) crux-only contract-doc conditionalization, (4) `workflow-init` self-activation + version stamp at adopt time. This spec owns the **temporal** half of the drift problem: the package is a frozen hand-cut snapshot of canonical, canonical moves ~19 commits/week, and nothing makes the gap reproducible, stamped, or detectable.

### 1. Problem

The plugin at `plugins/workflow-shell/` was hand-cut from canonical circa **2026-06-17** (marketplace commits `6c6f9eb`, `668c87ef`). Canonical has since advanced to HEAD **`ba26824`** (spec 053, 2026-06-19) and continues to land `.claude/` commits daily. Two structural defects follow (audit failure classes "No provenance/version stamping" F0-3/F2-0/F3-0/… and "Plugin package diverges from canonical" F0-4/F0-5/F0-7):

1. **Re-cutting is an undocumented manual ritual.** The packaging transforms (what to exclude, what to rewrite, what to inject) live only in the maintainer's head and in the *diff* between the two trees. There is no script, so every re-cut risks dropping a file or skipping a transform — exactly how `dynamic-workflows/shell-audit.md` (spec 052) and the verifier `permissionMode: bypassPermissions` fix (spec 053) got stranded.
2. **Drift is structurally invisible.** `plugin.json` carries only `name/version/description/author/keywords/license` — **no record of the canonical commit it was cut from**. A consumer or auditor cannot compute how far behind canonical the package is without manually diffing two repos. The only adoption record (`~/.claude/plugins/installed_plugins.json`, `gitCommitSha 668c87ef…`) points at the *marketplace* commit, not the *canonical* commit, and lives outside every project.

Concrete stranded-drift evidence (all auto-resolved by a faithful re-cut):
- **F0-4** (high): `agents/review/{spec,plan,task}-verifier.md` ship `permissionMode: default`; canonical has `bypassPermissions` since `382fc7e` (2026-06-19). The packaged verifiers stall on per-call permission prompts.
- **F0-5** (low): `dynamic-workflows/shell-audit.md` (spec 052, 2026-06-18) absent — the whole `dynamic-workflows/` directory is missing from the plugin.
- **F0-7** (low): `rules/backend-go.md`, `rules/frontend-tsx.md` dropped while shipped agents still assume Go/pytest/React.

### 2. Goals / Non-goals

**Goals**
- G1. A **single repeatable build step** (`scripts/repackage.sh`) that regenerates `plugins/workflow-shell/` from canonical by applying a **codified transform catalog** (§4), so re-cuts are reproducible and complete.
- G2. A **provenance stamp** (§5) written into `plugin.json` + a sidecar, recording the canonical commit/date/spec the package was cut from, so `plugin.packagedFrom.commit` vs `canonical HEAD` is computable.
- G3. A **drift check** (`scripts/check-drift.sh`, optionally surfaced as `/workflow-doctor`) (§6) that tells the maintainer when canonical has moved ahead **on the packaged surface** and a re-cut is warranted.
- G4. A **version-bump policy** (§7) tied to the kind of change pulled in.
- G5. A **decision + plan** on promoting `protect-secrets.sh` into the crux on next repackage (§8).

**Non-goals**
- Not packaging the SDK memory pipeline (that is the reserved `workflow-memory-pipeline` plugin; the exclusions are *intentional*, see §4.3).
- Not editing per-project adopted `.claude/` state, and not the adopt-time version stamp (that is sibling Deliverable 4).
- Not auto-publishing/auto-committing the marketplace repo. `repackage.sh` regenerates the tree and stamps it; the maintainer reviews the diff and commits.
- Not making `repackage.sh` run *inside* canonical or as a hook. It is a maintainer tool in the marketplace repo.

### 3. Inputs the mechanism depends on

| Input | Value (as observed) | How resolved |
|---|---|---|
| Canonical repo root | `/Users/rohitseelam/Projects/scratchpad-priv` | `CANONICAL_REPO` env, default to this path; overridable |
| Canonical contract root | `$CANONICAL_REPO/.claude` | derived |
| Canonical HEAD | `ba26824116a7…` (spec 053, 2026-06-19) | `git -C "$CANONICAL_REPO" rev-parse HEAD` |
| Plugin tree | `plugins/workflow-shell/` | repo-relative |
| Current stamp | *(absent today)* | `plugin.json.packagedFrom` once §5 lands |

### 4. Transform catalog (the heart of `repackage.sh`)

Every path under canonical `.claude/` falls into exactly one of three classes. The script is **manifest-driven**: the manifest below is the contract; the script is a faithful executor of it.

#### 4.1 Class A — Generated from canonical *with transform*

| Canonical source | Plugin destination | Transform |
|---|---|---|
| `agents/**/*.md` (except `_template.md`, `.DS_Store`) | `agents/**/*.md` | **Inject the path-resolution preamble** (§4.5) after YAML frontmatter, before the first `#` heading. Copy frontmatter verbatim (this is what carries the verifier `bypassPermissions` fix forward → auto-fixes F0-4). |
| `agents/_template.md` | `templates/agent-template.md` | **Relocate + rename**, no preamble. |
| `constitution.md` | `constitution.md` | Verbatim. *(Crux-only truth conditionalization is Deliverable 2; repackage copies whatever canonical holds.)* |
| `rules/{general,claude-code,tests,migrations}.md` | `rules/*.md` | Verbatim. |
| `rules/{backend-go,frontend-tsx}.md` | `rules/*.md` | **DECISION-GATED** (§4.6 / F0-7). Default: **include** (re-stack) until agents are de-stacked. |
| `workflow/{README,phases,routing,artifacts,communication,evaluation,migration}.md` | `workflow/*.md` | Verbatim. |
| `workflow/templates/**` | `workflow/templates/**` | Verbatim. |
| `skills/workflow/<verb>/SKILL.md` (`advance,new,rollback,rules-review,status`) | `skills/workflow-<verb>/SKILL.md` | **Flatten + prefix** the dir (`workflow/advance` → `workflow-advance`) **and rewrite** `${CLAUDE_SKILL_DIR}/../_scripts/` → `${CLAUDE_PLUGIN_ROOT}/skills/_scripts/` in body. |
| `skills/workflow/_scripts/*.py` | `skills/_scripts/*.py` | **Hoist** one level (`skills/workflow/_scripts` → `skills/_scripts`). Verbatim content. |
| `dynamic-workflows/shell-audit.md` | `dynamic-workflows/shell-audit.md` | **NEW inclusion** (resolves F0-5). Copy the `.md` only; **exclude** `dynamic-workflows/runs/` (per-project run state). |

#### 4.2 Class B — Plugin-native, hand-authored, **PRESERVED** across re-cut (never generated, never clobbered)

These have no canonical source — they exist only because the plugin distribution model differs from in-repo canonical. `repackage.sh` must **not** delete or overwrite them.

- `commands/workflow-init.md` — adoption command (canonical adoption used the now-removed `adopt-workflow` skill).
- `output-styles/workflow-orchestrator.md` — not present in canonical `.claude/` (lives in `~/.claude/output-styles` upstream).
- `hooks/session-context.sh` + `hooks/hooks.json` — the plugin-native SessionStart shim (replaces canonical's `load-active.sh`/CLAUDE.md `@`-imports).
- `.claude-plugin/plugin.json` — only its `packagedFrom`/`version` fields are touched by the stamper (§5); the rest is hand-maintained.
- `protect-secrets.sh` (+ its hooks.json registration) **once promoted** — see §8.

> **Implementation rule:** the script regenerates Class A into a clean staging dir, then **rsync-merges** Class A over the existing plugin tree *without touching* the Class-B allow-list. It must fail loudly if a Class-A regeneration would collide with a Class-B path.

#### 4.3 Class C — Excluded (must never appear in the crux)

| Excluded canonical path | Reason |
|---|---|
| `hooks/_actor_map.py`, `_budget_check.py`, `_memory_writer.py`, `_orphan_check.py`, `_phase_ledger.py`, `_proposal_schema.py`, `_session_scope.py`, `_silo_shape_check.py`, `sdk_memory_pipeline.py`, `sdk-memory-pipeline.sh`, `capture-session.sh`, `compile-session.sh`, `memory-write-guard.sh` | SDK memory pipeline → reserved `workflow-memory-pipeline` plugin |
| `hooks/{enforce-budget,lint-on-write,load-active,context-budget-check,detect_batch_intent}.*` | Canonical-only runtime hooks not wired in the crux (their agent references are dormant; see Deliverable 2) |
| `workflow/sdk-pipeline.md` | Memory-pipeline contract doc |
| `settings.sdk-memory.json` | Memory-pipeline settings |
| `skills/memory/**`, `skills/media/**`, `skills/research/**` | Memory + non-crux skills |
| `agent-memory/**`, `memory/**` | Memory stores + silo scaffolding |
| `specs/**`, `sessions/**`, `retrospectives/**` | Per-project working data |
| `active.json`, `CLAUDE.md`, `settings.json`, `settings.local.json` | Per-project state (seeded by `workflow-init`, not shipped) |
| `workflow/queue.md`, `workflow/queue-archive-*.md` | Per-project backlog |
| `rules/_candidates-*.md` | Staging file (intentionally not shipped) |
| `.venv/`, `.pytest_cache/`, `__pycache__/`, `hooks/tests/`, `**/.DS_Store`, `*.py[cod]` | Dev/test/OS cruft |

#### 4.4 Default-exclude posture

The manifest is **allow-list, not deny-list**: only Class A + Class B paths land in the plugin. Anything in canonical not explicitly mapped is excluded by default and **reported** by the script as `UNMAPPED` (see §4.7) so new canonical additions can't silently leak in or silently get dropped.

#### 4.5 Agent path-resolution preamble (injected verbatim, idempotent)

Inserted immediately after the closing `---` of frontmatter. The script must **skip injection if the block already exists** (idempotency marker = the literal `> **Plugin path resolution (workflow-shell).**`).

```markdown

> **Plugin path resolution (workflow-shell).** This agent ships in the `workflow-shell` plugin; the project does not contain these files. Resolve shorthand references below as:
> - Contract docs `workflow/<doc>.md` (README, phases, routing, artifacts, communication, evaluation, migration), `constitution.md`, `rules/<x>.md`, the `workflow/templates/`, and sibling agents `agents/<cat>/<name>.md` → **`${CLAUDE_PLUGIN_ROOT}/...`** (bundled here; read them from there).
> - Project state — `active.json`, `specs/<NNN>/…`, `state.json`, `.claude/workflow/queue.md`, `memory/`, `agent-memory/` → under the **project's `.claude/`** (cwd), seeded by `/workflow-init`. `queue.md` is project-side, NOT the plugin's `workflow/`.
> - References to `.claude/hooks/*` scripts and `specs/NNN/design/*` belong to the optional `workflow-memory-pipeline` plugin and are **dormant** in a crux-only install.

```

#### 4.6 De-stack decision hook (F0-7)

Single flag `INCLUDE_STACK_RULES` (default `true`). When `true`, include `backend-go.md`/`frontend-tsx.md`. When `false`, the maintainer must ensure `backend-engineer.md`/`qa-engineer.md`/`frontend-engineer.md` no longer hard-assume Go/pytest/React. The flag is recorded in the provenance stamp (`packagedFrom.options.includeStackRules`) so the choice is auditable. **Recommendation:** keep `true` until a dedicated de-stacking spec lands; shipping stack-assuming agents without their rule docs is the incoherent state.

#### 4.7 `repackage.sh` — reference implementation

```bash
#!/usr/bin/env bash
# scripts/repackage.sh — regenerate plugins/workflow-shell/ from canonical .claude/.
# Manifest-driven, allow-list, idempotent. Stamps provenance. Does NOT commit.
set -euo pipefail

MARKET_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANONICAL_REPO="${CANONICAL_REPO:-/Users/rohitseelam/Projects/scratchpad-priv}"
SRC="$CANONICAL_REPO/.claude"
DST="$MARKET_ROOT/plugins/workflow-shell"
INCLUDE_STACK_RULES="${INCLUDE_STACK_RULES:-true}"
PROMOTE_PROTECT_SECRETS="${PROMOTE_PROTECT_SECRETS:-false}"   # see §8

[ -d "$SRC" ] || { echo "FATAL: canonical not found at $SRC" >&2; exit 1; }
command -v python3 >/dev/null || { echo "FATAL: python3 required" >&2; exit 1; }

CANON_SHA="$(git -C "$CANONICAL_REPO" rev-parse HEAD)"
CANON_DATE="$(git -C "$CANONICAL_REPO" log -1 --format=%cI HEAD)"
# Highest spec number present in canonical (best-effort provenance label):
CANON_SPEC="$(ls "$SRC/specs" 2>/dev/null | grep -Eo '^[0-9]{3}' | sort -n | tail -1 || echo unknown)"
DIRTY="$(git -C "$CANONICAL_REPO" status --porcelain -- .claude | head -1)"
[ -n "$DIRTY" ] && echo "WARN: canonical .claude has uncommitted changes; stamp will be approximate." >&2

STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT

inject_preamble() {  # $1=src .md  $2=dst .md ; preamble file at scripts/lib/agent-preamble.md
  python3 "$MARKET_ROOT/scripts/lib/inject_preamble.py" "$1" "$2" \
          "$MARKET_ROOT/scripts/lib/agent-preamble.md"
}
copy() { mkdir -p "$(dirname "$2")"; cp "$1" "$2"; }

### Class A ---------------------------------------------------------------
# agents (preamble-injected), minus _template/.DS_Store
while IFS= read -r f; do
  rel="${f#"$SRC"/agents/}"
  inject_preamble "$f" "$STAGE/agents/$rel"
done < <(find "$SRC/agents" -name '*.md' ! -name '_template.md')

# agent template -> templates/
copy "$SRC/agents/_template.md" "$STAGE/templates/agent-template.md"

# constitution + workflow docs (allow-list)
copy "$SRC/constitution.md" "$STAGE/constitution.md"
for d in README phases routing artifacts communication evaluation migration; do
  copy "$SRC/workflow/$d.md" "$STAGE/workflow/$d.md"
done
[ -d "$SRC/workflow/templates" ] && cp -R "$SRC/workflow/templates" "$STAGE/workflow/templates"

# rules (allow-list; stack rules gated)
for r in general claude-code tests migrations; do copy "$SRC/rules/$r.md" "$STAGE/rules/$r.md"; done
if [ "$INCLUDE_STACK_RULES" = "true" ]; then
  for r in backend-go frontend-tsx; do
    [ -f "$SRC/rules/$r.md" ] && copy "$SRC/rules/$r.md" "$STAGE/rules/$r.md"
  done
fi

# skills: hoist _scripts, flatten+prefix verbs, rewrite CLAUDE_SKILL_DIR refs
for p in "$SRC"/skills/workflow/_scripts/*.py; do copy "$p" "$STAGE/skills/_scripts/$(basename "$p")"; done
for verb in advance new rollback rules-review status; do
  s="$SRC/skills/workflow/$verb/SKILL.md"; [ -f "$s" ] || continue
  mkdir -p "$STAGE/skills/workflow-$verb"
  sed 's#\${CLAUDE_SKILL_DIR}/\.\./_scripts/#${CLAUDE_PLUGIN_ROOT}/skills/_scripts/#g' \
      "$s" > "$STAGE/skills/workflow-$verb/SKILL.md"
done

# dynamic-workflows (md only; exclude runs/)
[ -f "$SRC/dynamic-workflows/shell-audit.md" ] && \
  copy "$SRC/dynamic-workflows/shell-audit.md" "$STAGE/dynamic-workflows/shell-audit.md"

### Class A → plugin (preserve Class B) -----------------------------------
# Replace ONLY the generated subtrees; never touch commands/, output-styles/,
# hooks/{session-context.sh,hooks.json}, .claude-plugin/.
for sub in agents templates constitution.md workflow rules skills dynamic-workflows; do
  rm -rf "${DST:?}/$sub"
done
cp -R "$STAGE/." "$DST/"

### Collision + unmapped report (§4.4) ------------------------------------
python3 "$MARKET_ROOT/scripts/lib/report_unmapped.py" "$SRC" "$DST"   # prints UNMAPPED canonical paths

### Provenance stamp (§5) -------------------------------------------------
python3 "$MARKET_ROOT/scripts/lib/stamp_provenance.py" \
  --plugin-json "$DST/.claude-plugin/plugin.json" \
  --provenance  "$DST/PROVENANCE.md" \
  --sha "$CANON_SHA" --date "$CANON_DATE" --spec "$CANON_SPEC" \
  --include-stack-rules "$INCLUDE_STACK_RULES" \
  --promote-protect-secrets "$PROMOTE_PROTECT_SECRETS"

echo "Repackaged from canonical $CANON_SHA (spec $CANON_SPEC). Review 'git diff' before committing."
```

> Helper scripts (`scripts/lib/inject_preamble.py`, `report_unmapped.py`, `stamp_provenance.py`) and `scripts/lib/agent-preamble.md` (the §4.5 block) are part of this spec's deliverables. `inject_preamble.py` splits on the second `---`, dedupes on the idempotency marker, then re-emits frontmatter + preamble + body. `report_unmapped.py` walks canonical, subtracts Class-A+B+C globs, and lists residue so new upstream files surface.

A `make repackage` target wrapping `scripts/repackage.sh` is provided for ergonomics.

### 5. Provenance stamp

Two artifacts, one regenerated by the stamper:

**5.1 `plugin.json` — machine-readable (extra keys are tolerated by the Claude Code plugin loader; verify in AC-7).**

```json
{
  "name": "workflow-shell",
  "version": "0.2.0",
  "description": "...",
  "author": { "name": "Rohit Seelam", "email": "rohitseelam09@gmail.com" },
  "keywords": ["workflow", "orchestration", "spec-driven", "agents", "constitution", "phases", "verifier"],
  "license": "MIT",
  "packagedFrom": {
    "canonicalRepo": "scratchpad-priv",
    "commit": "ba26824116a7c3477a1ab1dd15012d304b005067",
    "committedAt": "2026-06-19T02:00:28+05:30",
    "canonicalSpec": "053",
    "packagedAt": "2026-06-26T00:00:00Z",
    "packagedBy": "scripts/repackage.sh",
    "options": { "includeStackRules": true, "promoteProtectSecrets": false }
  }
}
```

**5.2 `plugins/workflow-shell/PROVENANCE.md` — human-readable mirror** (so the lineage is visible in the file tree even if a tool strips unknown JSON keys). Contains the same fields plus the canonical HEAD subject line and a "regenerate with `scripts/repackage.sh`" note.

**Design rationale.** `packagedFrom.commit` is the *canonical* sha (not the marketplace commit) — this is precisely the field absent today (F0-3). With it present, drift = `git -C canonical rev-list --count <packagedFrom.commit>..HEAD`. The marketplace README "Plugins" table version cell and the `marketplace.json` plugin description should additionally surface the canonical spec label (e.g. "v0.2.0 · canonical spec 053") so drift is visible at the catalog level too.

### 6. Drift check — `scripts/check-drift.sh` (and optional `/workflow-doctor`)

Read-only. Compares the stamped canonical commit to canonical HEAD, **filtered to the packaged surface** so memory/specs/sessions churn doesn't create noise.

```bash
#!/usr/bin/env bash
set -euo pipefail
MARKET_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANONICAL_REPO="${CANONICAL_REPO:-/Users/rohitseelam/Projects/scratchpad-priv}"
PJ="$MARKET_ROOT/plugins/workflow-shell/.claude-plugin/plugin.json"

STAMP="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["packagedFrom"]["commit"])' "$PJ" 2>/dev/null || true)"
[ -n "$STAMP" ] || { echo "DRIFT-UNKNOWN: no packagedFrom stamp in plugin.json (run repackage.sh)"; exit 3; }

HEAD="$(git -C "$CANONICAL_REPO" rev-parse HEAD)"
if [ "$STAMP" = "$HEAD" ]; then echo "UP-TO-DATE: plugin == canonical $HEAD"; exit 0; fi

# Packaged surface = the Class-A canonical paths only.
PATHS=(.claude/agents .claude/constitution.md .claude/rules
       .claude/workflow/README.md .claude/workflow/phases.md .claude/workflow/routing.md
       .claude/workflow/artifacts.md .claude/workflow/communication.md
       .claude/workflow/evaluation.md .claude/workflow/migration.md .claude/workflow/templates
       .claude/skills/workflow .claude/dynamic-workflows/shell-audit.md)

TOTAL="$(git -C "$CANONICAL_REPO" rev-list --count "${STAMP}..${HEAD}" 2>/dev/null || echo '?')"
SURFACE="$(git -C "$CANONICAL_REPO" log --oneline "${STAMP}..${HEAD}" -- "${PATHS[@]}" 2>/dev/null || true)"

echo "Plugin packagedFrom: $STAMP"
echo "Canonical HEAD:      $HEAD  ($TOTAL commits ahead total)"
if [ -z "$SURFACE" ]; then
  echo "NO-PACKAGED-DRIFT: $TOTAL commits ahead but none touch the packaged surface. Re-cut optional."
  exit 0
fi
echo "DRIFT on packaged surface — repackage recommended. Commits since stamp:"
echo "$SURFACE"
exit 1   # nonzero = action needed (CI/precommit-friendly)
```

Exit codes: `0` up-to-date / no-packaged-drift · `1` packaged-surface drift (re-cut) · `3` no stamp. Optionally expose as a `/workflow-doctor` skill in the marketplace repo (or `make doctor`) for one-command checking; the script is the engine either way.

### 7. Version-bump policy

`repackage.sh` does **not** auto-bump `version` (semver intent is human judgment); it **prompts** the maintainer with the drift summary and a suggested level. Policy:

| Level | When | Examples from current backlog |
|---|---|---|
| **patch** (`0.1.0→0.1.1`) | doc-only edits within the packaged surface, typo/clarity | crux-only conditionalization wording (Deliverable 2) |
| **minor** (`0.1.0→0.2.0`) | new capability or behavior change, backward-compatible | shell-audit added (F0-5), verifier `bypassPermissions` (F0-4), protect-secrets promotion (§8), stack-rule re-inclusion (F0-7) |
| **major** (`0.x→1.0+`) | breaking contract change | phase-machine/state-schema change, removing a phase, agent renames consumers depend on |

The **first** re-cut that lands F0-4 + F0-5 (+ optionally §8) is a **minor** bump → `0.2.0` (reflected in §5.1).

### 8. Decision — promote `protect-secrets.sh` into the crux on next repackage?

**Recommendation: YES — promote it, as a Class-B plugin-native hook, on the next re-cut.** This is the single highest-value, lowest-risk addition available, and it directly closes the audit's largest recurring failure class (12 findings: F0-0, F4-7, F7-2, F8-2, F11-2, F12-2, F13-3, F14-2, F15-2, F16-3/4, F18-2 — "Secrets protection is settings-only and the deny-list is narrow/local/absent").

**Why it qualifies:**
- **Self-contained, zero pipeline coupling.** `protect-secrets.sh` reads tool JSON on stdin and inspects `.tool_input.file_path` / `.tool_input.command` only — no `memory/`, no canonical paths, no SDK deps. It is *not* part of the excluded memory pipeline.
- **It's the only runtime backstop.** The settings deny-list (the crux's sole current mechanism) cannot gate Bash-arg contents (`cat .env` bypasses it), is frequently narrow/local-only/absent, and does not cover SSH keys. `protect-secrets.sh` blocks (`exit 2`) `.env*`, `credentials.json`, `service-account*.json`, and `id_rsa/id_ed25519/id_ecdsa[.pub]` for **both** file tools **and** Bash, with an allow-list short-circuit for `.env.example/.sample/.template/.dist/.defaults`.

**Required adaptations before shipping (part of the promotion task, not a blocker):**
1. **Drop the `jq` dependency.** Canonical's hook shells out to `jq`; the crux deliberately standardized on `python3` (see `session-context.sh`). Port the two `jq -r` reads to a tiny `python3` stdin parser so the crux adds **no new dependency**. A security hook must **not** fail-open if `jq` is missing — porting removes that risk.
2. **Register via `${CLAUDE_PLUGIN_ROOT}`** in `hooks/hooks.json`, adding a `PreToolUse` block alongside the existing `SessionStart`:
   ```json
   "PreToolUse": [
     { "matcher": "Read|Edit|Write|MultiEdit|Bash",
       "hooks": [ { "type": "command",
         "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/protect-secrets.sh\"" } ] }
   ]
   ```
   Because the hook is project-agnostic (it judges the *tool's* target, not a project file), `${CLAUDE_PLUGIN_ROOT}` resolution is correct and needs no project-root plumbing — unlike `memory-write-guard.sh` (item 1 in the memory-pipeline README), which is why that one stays in the reserved plugin and this one does not.
3. **Classify as Class B** (plugin-native): the jq→python3 port is a one-time adaptation, so the file is hand-maintained in the marketplace repo, not regenerated each re-cut. Add it to the §4.2 preserve allow-list and gate its inclusion behind `PROMOTE_PROTECT_SECRETS=true` for the cut that lands it (then it's permanent).
4. **Pair with the deny-list broadening** in `workflow-init` (sibling Deliverable 4) for defense-in-depth — hook + committed deny-list, neither relying on the other.

**Net:** promoting it makes every adopting project secret-safe at runtime regardless of whether `settings.json` was merged correctly, with no new dependency and no memory-pipeline entanglement. Set `PROMOTE_PROTECT_SECRETS=true` for the `0.2.0` cut.

### 9. Acceptance criteria

- **AC-1.** `scripts/repackage.sh` run against canonical HEAD produces a `git diff` whose **only** changes vs the committed plugin are (a) the F0-4 verifier `permissionMode`, (b) the new `dynamic-workflows/shell-audit.md` (F0-5), (c) the re-included stack rules if `INCLUDE_STACK_RULES=true` (F0-7), (d) the provenance stamp, (e) any genuine canonical doc changes since the stamp. No Class-B file (`commands/`, `output-styles/`, `hooks/session-context.sh`, `hooks/hooks.json`) is modified.
- **AC-2.** Re-running `repackage.sh` twice yields an **empty** diff on the second run except `packagedAt` (idempotent; preamble not double-injected — verified by exactly one `Plugin path resolution` marker per agent).
- **AC-3.** Every Class-A skill body contains `${CLAUDE_PLUGIN_ROOT}/skills/_scripts/` and **zero** `${CLAUDE_SKILL_DIR}` occurrences; `skills/_scripts/*.py` present.
- **AC-4.** No Class-C path appears anywhere under `plugins/workflow-shell/` (grep: no `sdk_memory_pipeline`, `memory-write-guard`, `_memory_writer`, `agent-memory`, `settings.sdk-memory`, `.DS_Store`, `__pycache__`, `_candidates-`).
- **AC-5.** `plugin.json.packagedFrom.commit` equals canonical HEAD after a cut; `PROVENANCE.md` mirrors it.
- **AC-6.** `scripts/check-drift.sh` returns `0` immediately after a cut, `1` after a canonical commit touching the packaged surface, `0`/`NO-PACKAGED-DRIFT` after a canonical commit touching only `memory/`/`specs/`/`sessions/`, and `3` when the stamp is absent.
- **AC-7.** `plugin.json` with the extra `packagedFrom` key still loads: `/plugin install workflow-shell@workflow-shell-marketplace` succeeds and the plugin enables without schema error (if the loader rejects unknown keys, fall back to `PROVENANCE.md` + a top-level `metadata` object per loader docs).
- **AC-8.** `report_unmapped.py` lists zero `UNMAPPED` paths for the current canonical tree (every canonical path is classified A/B/C); a deliberately-added new canonical file surfaces as `UNMAPPED`.
- **AC-9 (if §8 taken).** After `PROMOTE_PROTECT_SECRETS=true`, `hooks/hooks.json` registers the `PreToolUse` matcher; the ported hook blocks `Read` of `.env` and `Bash` `cat .env` (exit 2) and allows `Read` of `.env.example`; it invokes no `jq`.

### 10. Test plan

1. **Golden re-cut:** snapshot current `plugins/workflow-shell/`, run `repackage.sh`, assert AC-1 deltas exactly (no unexpected file add/drop). Confirm `agents/review/spec-verifier.md` line 5 flips to `bypassPermissions` and `dynamic-workflows/shell-audit.md` appears.
2. **Idempotency:** run twice; diff only `packagedAt` (AC-2). Assert single preamble marker per agent file via `grep -c`.
3. **Exclusion fuzz:** plant a `agent-memory/x` and a `.DS_Store` in canonical, re-cut, assert absent (AC-4); assert they appear in the `UNMAPPED`/excluded report appropriately.
4. **Drift matrix:** (a) no canonical change → `0`; (b) `touch`+commit `.claude/workflow/phases.md` → `1` with that commit listed; (c) commit only under `.claude/memory/` → `NO-PACKAGED-DRIFT`/`0`; (d) blank `packagedFrom` → `3` (AC-6).
5. **Loader smoke:** install the stamped plugin locally, `/workflow-init` a throwaway project, `/clear`, confirm SessionStart injection still fires and a skill (`/workflow-status`) resolves `${CLAUDE_PLUGIN_ROOT}/skills/_scripts/…` (AC-3, AC-7).
6. **Secrets hook (if §8):** unit-test the ported `protect-secrets.sh` with crafted stdin JSON for Read/.env (block), Bash/`cat .env` (block), Read/`.env.example` (allow), Read/`README.md` (allow); confirm no `jq` in `PATH` still works (AC-9).

### 11. Risks & mitigations

- **R1 — Class-B clobber.** A future canonical file colliding with a Class-B path would be silently overwritten. *Mitigation:* `repackage.sh` asserts the Class-A staging tree contains none of the Class-B allow-list paths before merge; abort otherwise.
- **R2 — Loader rejects unknown `plugin.json` keys.** *Mitigation:* AC-7 gates this; fallback is `PROVENANCE.md` as source-of-truth + drift check reads the sidecar `.claude-plugin/provenance.json` instead of `plugin.json`.
- **R3 — Stamp taken from a dirty canonical tree.** *Mitigation:* script warns on `git status --porcelain .claude` and records `committedAt`; recommend cutting only from a clean canonical checkout.
- **R4 — New canonical capability silently dropped (the exact F0-5 failure).** *Mitigation:* `report_unmapped.py` + AC-8 force every new canonical path to be explicitly classified before it can be ignored.
- **R5 — Transform drift (canonical changes the `${CLAUDE_SKILL_DIR}` convention or frontmatter shape).** *Mitigation:* AC-3 + golden test catch a rewrite that stops matching; the manifest is the single place to update.

### 12. Deliverables checklist

- `scripts/repackage.sh` (+ `make repackage`)
- `scripts/lib/inject_preamble.py`, `scripts/lib/report_unmapped.py`, `scripts/lib/stamp_provenance.py`, `scripts/lib/agent-preamble.md`
- `scripts/check-drift.sh` (+ `make doctor`, optional `/workflow-doctor` skill)
- `plugin.json` extended with `packagedFrom`; `plugins/workflow-shell/PROVENANCE.md`
- README "Plugins" table + `marketplace.json` descriptions surface the canonical-spec label
- (If §8 accepted) ported `hooks/protect-secrets.sh` (python3, no jq) + `hooks/hooks.json` `PreToolUse` registration, gated by `PROMOTE_PROTECT_SECRETS`
- First stamped re-cut → `workflow-shell 0.2.0` (lands F0-4, F0-5, F0-7, provenance; §8 optional in same cut)

---

**Key paths referenced:** canonical `/Users/rohitseelam/Projects/scratchpad-priv/.claude` (HEAD `ba26824`, spec 053) · plugin `/Users/rohitseelam/Projects/workflow-shell-marketplace/plugins/workflow-shell` · manifest `.claude-plugin/{plugin.json,marketplace.json}` · the to-be-promoted hook `…/scratchpad-priv/.claude/hooks/protect-secrets.sh`.

---

## 8. Deliverable 4 — contract-patch list (crux-only truth fixes)

All paths under `/Users/rohitseelam/Projects/workflow-shell-marketplace/plugins/workflow-shell/`.

**Convention used in every "after":** gate each memory/pipeline assertion on the companion plugin with the explicit phrase **"when the `workflow-memory-pipeline` plugin is installed"** and state the crux-only reality (no writer, no guard, stores unwritten, capture is manual). This mirrors the marketplace README (`workflow-memory-pipeline` = "reserved slot … The crux works without it") and that plugin's own README ("stay **dormant by design** — they describe a writer that simply isn't installed yet").

**Model phrasing already correct (no change required):** `output-styles/workflow-orchestrator.md` lines 62-65 already conditionalize Rule 5 — *"(the SDK memory pipeline, a separate plugin, is the sole writer; if it isn't installed, memory is simply dormant — never write it yourself)"*. Every patch below brings the other docs into line with this output-style. Optional tightening for that file is listed last.

---

### 1. `constitution.md` — Rule 5 (F1-0)  **[the key fix]**

**Before** (lines 40-41):
> The SDK memory pipeline is the SOLE writer of memory. The orchestrator and every subagent MUST NOT write `.claude/memory/`, `.claude/agent-memory/`, or the canonical `~/.claude/projects/<slug>/memory/` — enforced mechanically by `.claude/hooks/memory-write-guard.sh`. These project instructions override Claude Code's built-in auto-memory behavior; the auto-memory-disable setting's scope is covered in `specs/029-memory-sdk-sole-writer/design/auto-load-mechanics.md` (fact 5).

**After** (replace that paragraph; keep line 39 as-is):
> This rule's enforcement depends on the `workflow-memory-pipeline` companion plugin.
>
> **When that plugin is installed:** the SDK memory pipeline is the SOLE writer of memory. The orchestrator and every subagent MUST NOT write `.claude/memory/`, `.claude/agent-memory/`, or the canonical `~/.claude/projects/<slug>/memory/` — enforced mechanically by the plugin's `memory-write-guard.sh` `PreToolUse` hook. These project instructions override Claude Code's built-in auto-memory behavior (auto-memory-disable scope lives in the pipeline plugin's design notes).
>
> **Crux-only — no memory-pipeline plugin installed (the default):** this rule is INERT. There is no writer and no guard, so nothing is written to the memory roots at `deliver` and decisions are NOT captured automatically. If a decision is worth retaining, hand-write it into `.claude/memory/topics/<topic>.md` via a `docs` workflow (permitted because no guard is active). Do NOT treat a decision as persisted unless the pipeline plugin is installed or you wrote it down yourself.

**Why:** Rule 5 currently asserts unconditionally a sole writer + a `memory-write-guard.sh` hook that the crux package does not ship (only `hooks/session-context.sh` is registered). A crux-only reader believes memory is written and guarded when nothing writes it and decisions silently vanish.

---

### 2. `workflow/phases.md` (F1-1, F1-2, F0-2)

**2a — deliver row (line 33):**
**Before:** `… updated docs, memory pipeline run (see "Deliver: SDK memory pipeline" below)`
**After:** `… updated docs; memory pipeline run **only if the `workflow-memory-pipeline` plugin is installed** (see "Deliver: SDK memory pipeline" below). **In a crux-only install deliver writes NO memory — branch/PR + docs only.**`
**Why:** the per-phase contract is the table a reader scans first; "memory pipeline run" reads as guaranteed.

**2b — branch-and-PR step 2 (line 54):**
**Before:**
> This includes the SDK memory pipeline's commit (see "Deliver: SDK memory pipeline" — `phases.md#deliver-sdk-memory-pipeline`): the pipeline still runs at deliver, but ON the spec branch, and its memory commit is part of the same PR — NOT an independent `main` commit.

**After:**
> When the `workflow-memory-pipeline` plugin is installed, this includes the SDK memory pipeline's commit (see "Deliver: SDK memory pipeline"): the pipeline runs at deliver ON the spec branch, and its memory commit is part of the same PR — NOT an independent `main` commit. In a crux-only install there is no pipeline and therefore no memory commit in the PR.

**Why:** the "memory commit is part of the same PR" guarantee is false in crux-only.

**2c — "Deliver: SDK memory pipeline" section (lines 59-63):**
**Before** (opening, line 60):
> At the end of every `deliver` phase (every workflow type), a `claude-agent-sdk` subprocess updates project memory.

**After** (prepend a conditional banner to the section):
> **This entire section applies ONLY when the `workflow-memory-pipeline` companion plugin is installed.** In a crux-only install (the default) there is NO memory subprocess and NO writer: `deliver` completes with branch/PR + updated docs but writes NO memory, and the rest of this section is dormant. The full pipeline contract (`workflow/sdk-pipeline.md`) ships with that plugin and is **absent in crux-only** — references to it below resolve only when the plugin is installed.
>
> **When the plugin is installed:** at the end of every `deliver` phase (every workflow type), a `claude-agent-sdk` subprocess updates project memory. …(rest unchanged)

**Why:** the section narrates a subprocess, a propose→write split, and a `workflow/sdk-pipeline.md` contract doc — none of which ship in the crux (dangling 404 + missing capability, F0-2).

**2d — Compact bullet (line 86) + PreCompact note (line 88):**
**Before:** `- It does NOT trigger the SDK memory pipeline.`
**After:** `- It does NOT trigger the SDK memory pipeline (relevant only when that plugin is installed; in a crux-only install there is no pipeline to trigger).`
Also annotate line 88: the `PreCompact` archive hook + "the SDK reads the canonical in-file marker" are part of the memory-pipeline plugin — append `(PreCompact capture + SDK marker-read apply only with the `workflow-memory-pipeline` plugin installed).`
**Why:** describes components not installed in crux.

**2e — Termination step 1 (lines 190-191):**
**Before:**
> Project memory is updated by the SDK memory pipeline — the SOLE memory writer — per "Deliver: SDK memory pipeline" above, with its commit riding the same spec branch. The orchestrator does NOT write `.claude/memory/` itself (`constitution.md` Rule 5; mechanically blocked by `.claude/hooks/memory-write-guard.sh`).

**After:**
> If the `workflow-memory-pipeline` plugin is installed, project memory is updated by the SDK memory pipeline (the SOLE writer) per "Deliver: SDK memory pipeline" above, its commit riding the same spec branch, and the orchestrator does NOT write `.claude/memory/` itself (`constitution.md` Rule 5; blocked by that plugin's `memory-write-guard.sh`). In a crux-only install no memory is written at `deliver` and no guard is active; the PR carries only the branch/code/doc commits.

**Why:** cites a dead hook path and a sole-writer that does not exist in crux.

---

### 3. `workflow/evaluation.md` (F1-3)

**Before** (cross-checker Checks column, line 69 — the memory sub-checks):
> … every AC has a passing test cited by name; MEMORY.md shape compliance (line format, 200-line / 25KB cap, no narrative paragraphs); selective-mirror-policy COMPLIANCE (NOT exact equality) between `~/.claude/projects/<project-slug>/memory/` and `<repo>/.claude/memory/`, with the `agent-memory/` silos (canonical-only) carved out — per `workflow/artifacts.md` "Selective mirror policy" |

**After:**
> … every AC has a passing test cited by name. **The memory sub-checks that follow apply ONLY when the `workflow-memory-pipeline` plugin is installed; SKIP them in a crux-only install, where no writer maintains the stores (gating on them there yields a false-positive `major` with nothing to comply).** MEMORY.md shape compliance (line format, 200-line / 25KB cap, no narrative paragraphs); selective-mirror-policy COMPLIANCE (NOT exact equality) between `~/.claude/projects/<project-slug>/memory/` and `<repo>/.claude/memory/`, with the `agent-memory/` silos carved out — per `workflow/artifacts.md` "Selective mirror policy" |

**Why:** turns an unconditional gating check into a plugin-conditional one; in crux-only the two stores have no writer, so "mirror compliance" either has nothing to check or fabricates a `major` that blocks deliver.
**No change needed:** line 239 cost note's pipeline carve-out is already correct.

---

### 4. `workflow/communication.md` (F1-4, F0-2)

**4a — BLOCKED-PERSIST-INLINE durability (line 134):**
**Before:**
> Two confirmed instances (spikes 008, 010). The pattern is durable; any new instance is captured at `deliver` by the SDK memory pipeline (the sole memory writer — `constitution.md` Rule 5), not hand-written.

**After:**
> Two confirmed instances (spikes 008, 010). The pattern is durable. When the `workflow-memory-pipeline` plugin is installed, a new instance is captured at `deliver` by the SDK memory pipeline (the sole writer — `constitution.md` Rule 5), not hand-written. In a crux-only install nothing captures it automatically; if it is worth keeping, record it manually in `.claude/memory/topics/<topic>.md`.

**4b — "SDK memory subprocess is NOT in the triangle" (lines 140-144):**
**Before** (opening, line 142): `The `claude-agent-sdk` subprocess that runs at every `deliver` (per `phases.md` "Deliver: SDK memory pipeline" and `workflow/sdk-pipeline.md`) is NOT a subagent …`
**After** (prepend): `**This section describes the `workflow-memory-pipeline` plugin; in a crux-only install there is no such subprocess and `workflow/sdk-pipeline.md` is not shipped — skip it.** The `claude-agent-sdk` subprocess that runs at every `deliver` … is NOT a subagent …`
**Before** (line 144): `The next workflow's `verify` phase picks up any divergence via cross-checker's selective-mirror-policy compliance check …`
**After:** `When the plugin is installed, the next workflow's `verify` phase picks up any divergence via cross-checker's selective-mirror-policy compliance check …; in a crux-only install there is no writer and no mirror check, so nothing diverges or needs reconciling.`

**Why:** tells the reader a leaf subprocess writes memory every deliver and patterns are auto-captured + auto-reconciled — none true in crux; also a dangling `sdk-pipeline.md` pointer.

---

### 5. `workflow/artifacts.md` (F1-5)

**5a — folder-layout comment (line 63):**
**Before:** `│   (agent-memory/<agent>/ — per-agent silos: active & SDK-written, guarded; see CLAUDE.md)`
**After:** `│   (agent-memory/<agent>/ — per-agent silos: active, SDK-written & guarded ONLY with the workflow-memory-pipeline plugin; inert/empty in crux-only)`

**5b — auto-loaded-memory note (line 73):** conditionalize the two false clauses.
**Before:** `… kept in sync by the SDK memory pipeline at every `deliver`. The per-subagent silos at `<repo>/.claude/agent-memory/<agent>/` are ACTIVE for the 6 silo agents under the single-writer model … each auto-loads via `memory: project`, the SDK memory pipeline is the SOLE writer, and `memory-write-guard.sh` blocks non-SDK actors.`
**After:** `… kept in sync by the SDK memory pipeline at every `deliver` **only when the `workflow-memory-pipeline` plugin is installed; in a crux-only install nothing writes or syncs it.** The per-subagent silos at `<repo>/.claude/agent-memory/<agent>/` become ACTIVE for the 6 silo agents under the single-writer model **only with that plugin installed** — each auto-loads via `memory: project`, the SDK memory pipeline is the SOLE writer, and `memory-write-guard.sh` blocks non-SDK actors. **Without the plugin the silos auto-load only hand-seeded/empty files; there is no writer and no guard.**`

**5c — MEMORY.md shape (lines 223, 225):**
**Before (223):** `Written by the SDK memory pipeline alongside the canonical, but holds only the workflow/mirrored class …`
**After:** `Written by the SDK memory pipeline alongside the canonical **when the `workflow-memory-pipeline` plugin is installed** (holds only the workflow/mirrored class …); **in a crux-only install it is hand-seeded or empty.**`
**Before (225):** `… are ACTIVE for the 6 silo agents under the single-writer model … the SDK memory pipeline is the SOLE writer. `.claude/hooks/memory-write-guard.sh` blocks any non-SDK actor from writing the path.`
**After:** `… are ACTIVE for the 6 silo agents under the single-writer model **only when the `workflow-memory-pipeline` plugin is installed** — then the SDK memory pipeline is the SOLE writer and that plugin's `memory-write-guard.sh` blocks any non-SDK actor. **In a crux-only install the silos are inert and unguarded.**`

**5d — mirror-policy + single-writer enforcement (lines 253, 255):**
**Before (253):** `**Mirror-policy compliance** … is verified by `cross-checker` during every workflow's `verify` phase …`
**After:** `**Mirror-policy compliance** … is verified by `cross-checker` during `verify` **only when the `workflow-memory-pipeline` plugin is installed** (it maintains both stores); in a crux-only install there are no maintained stores to compare and the check is skipped.`
**Before (255):** `This single-writer contract is now ENFORCED mechanically by the `PreToolUse` guard `.claude/hooks/memory-write-guard.sh` (spec 029), which blocks any non-SDK actor from writing the three memory roots.`
**After:** `This single-writer contract is ENFORCED mechanically by the `PreToolUse` guard `memory-write-guard.sh` (spec 029) **only when the `workflow-memory-pipeline` plugin ships it; the crux package does NOT include this guard, so in a crux-only install nothing blocks writes to the memory roots.**`

**Why:** presents silos as active, the SDK writer as live, and the guard as enforcing — the "now ENFORCED mechanically" claim is simply false in crux (no guard hook ships).

---

### 6. `workflow/README.md` (F1-6, F0-2)

**6a — memory vs queue (line 24):**
**Before:** `- `.claude/memory/topics/*.md` — landed decisions and characterization findings. Written by the SDK memory pipeline at every `deliver`. …`
**After:** `- `.claude/memory/topics/*.md` — landed decisions and characterization findings. Written by the SDK memory pipeline at every `deliver` **when the `workflow-memory-pipeline` plugin is installed; in a crux-only install these are written only by hand, or not at all**. …`

**6b — vocabulary entry (line 40):**
**Before:** `- **SDK memory pipeline** — the SOLE memory writer; a `claude-agent-sdk` subprocess that runs at every `deliver`. Not a subagent in the triangle. Contract in `workflow/sdk-pipeline.md`; mirror classification in `workflow/artifacts.md#selective-mirror-policy`.`
**After:** `- **SDK memory pipeline** — the SOLE memory writer **when installed**. **Ships as the OPTIONAL `workflow-memory-pipeline` companion plugin, NOT part of the crux; in a crux-only install it is absent and no memory is written at `deliver`.** A `claude-agent-sdk` subprocess that runs at every `deliver`; not a subagent in the triangle. Contract in `workflow/sdk-pipeline.md` (**ships with that plugin; absent in crux-only**); mirror classification in `workflow/artifacts.md#selective-mirror-policy`.`

**6c — skills list (line 66):**
**Before:** `- `skills/memory/` — `compile`, `extract`, `jsonl-format` … read by the SDK memory pipeline).`
**After:** `- `skills/memory/` — `compile`, `extract`, `jsonl-format` (read by the SDK memory pipeline). **Ships with the `workflow-memory-pipeline` plugin; NOT present in a crux-only install.**`

**6d — what is NOT here (line 75):**
**Before:** `… both written solely by the SDK memory pipeline at `deliver` (`constitution.md` Rule 5). …`
**After:** `… both written solely by the SDK memory pipeline at `deliver` (`constitution.md` Rule 5) **when the `workflow-memory-pipeline` plugin is installed; in a crux-only install nothing writes them — they are empty/hand-seeded.** …`

**Why:** the index/vocabulary sends readers to a 404 (`workflow/sdk-pipeline.md`) and to a non-existent `skills/memory/`, and asserts deliver-time writes as standing facts. Highest-severity doc-truth finding (F1-6 confirmed).

---

### 7. `workflow/migration.md` (F1-7, F0-2)

**7a — Section 2d heading + line 62:**
**After (banner under `### 2d. Bootstrap user-side memory (mirror seed)`):** `**Section 2d applies only if you are adopting the optional `workflow-memory-pipeline` plugin. In a crux-only install skip it — there is no pipeline to keep a mirror in sync.**`
**Before (62):** `Subsequent runs of the SDK memory pipeline at `deliver` keep both locations in sync (see `specs/012-…/design/04-memory-index-shape.md`).`
**After:** `**With the `workflow-memory-pipeline` plugin installed,** subsequent runs of the SDK memory pipeline at `deliver` keep both locations in sync. **Without it, this seed is a one-time copy that nothing keeps in sync — the two locations will drift.**`

**7b — Section 4 "Seed `memory/`" (74-79):** add a one-line note: `**In a crux-only install this hand-seed is the ONLY way `memory/` ever gets content — there is no pipeline to populate or update it.**`

**7c — Section 6 wire hooks (lines 89-91):**
**Before (89):** `Create `.claude/hooks/` and copy `capture-session.sh` (or equivalent) from a reference repo.`
**After:** `(**Only if adopting the `workflow-memory-pipeline` plugin.**) Create `.claude/hooks/` and copy `capture-session.sh` — it ships with that plugin, not the crux.`
**Before (91):** `… They become important once the SDK memory pipeline at `deliver` is enabled (see `workflow/sdk-pipeline.md`).`
**After:** `… The memory-capture/pipeline hooks (`capture-session.sh`, `sdk_memory_pipeline.py`, `memory-write-guard.sh`) and `workflow/sdk-pipeline.md` ship with the OPTIONAL `workflow-memory-pipeline` plugin — install it to enable deliver-time memory writes. The crux ships none of these.`

**7d — Onboarding checklist (lines 119, 123):**
**Before (119):** `- [ ] User-side memory mirror seeded via 2d.`
**After:** `- [ ] User-side memory mirror seeded via 2d (only if adopting the optional memory-pipeline plugin).`
**Before (123):** `- [ ] Hooks wired if SDK memory pipeline is in scope.`
**After:** `- [ ] Hooks wired ONLY if adopting the optional `workflow-memory-pipeline` plugin (the crux needs none).`

**Why:** onboarding tells a crux-only team to seed a mirror that "pipeline runs keep in sync" (no pipeline → silent drift) and to copy `capture-session.sh` / wire `workflow/sdk-pipeline.md`, both of which ship only with the absent plugin (F1-7 confirmed).

---

### 8. `rules/migrations.md` (F1-8) and `workflow/routing.md` (F1-8)

**8a — `rules/migrations.md` line 11:**
**Before:** `We do not write down migrations (decided 2026 — see `memory/topics/conventions.md`).`
**After:** `We do not write down migrations. (This line is the decision of record; a longer rationale lives in `memory/topics/conventions.md` **only when the memory store is populated — i.e. with the `workflow-memory-pipeline` plugin installed.**)`
**Why:** cites a memory topic file the crux never writes as the home of the decision; the rule itself must stand without it.

**8b — `workflow/routing.md` line 137:**
**Before:** `Orchestrator reads the cleaned prompt + relevant context (`active.json`, `constitution.md`, top-200 of `memory/MEMORY.md`).`
**After:** `Orchestrator reads the cleaned prompt + relevant context (`active.json`, `constitution.md`, and — **if present** — the top-200 lines of the canonical `~/.claude/projects/<slug>/memory/MEMORY.md`). **That index is populated only when the `workflow-memory-pipeline` plugin is installed; in a crux-only install it may be empty or absent and is simply skipped.**`
**Why:** claims to read a top-200 memory index that crux never populates (and points at the repo path, not the canonical auto-load path).

---

### 9. `output-styles/workflow-orchestrator.md` — already conditional (optional tightening)

**Status:** lines 62-65 already correctly conditionalize Rule 5 — *"the SDK memory pipeline, a separate plugin, is the sole writer; if it isn't installed, memory is simply dormant — never write it yourself."* No fix required; this is the model the patches above replicate.

**Optional tightening** (name the plugin + the manual-capture escape hatch, to match the new constitution Rule 5):
**Before:** `(5) memory hygiene — you and every subagent MUST NOT write `memory/` or `agent-memory/` (the SDK memory pipeline, a separate plugin, is the sole writer; if it isn't installed, memory is simply dormant — never write it yourself);`
**After:** `(5) memory hygiene — when the `workflow-memory-pipeline` plugin is installed, you and every subagent MUST NOT write `memory/` or `agent-memory/` (its SDK pipeline is the sole writer, mechanically guarded); when it is NOT installed (crux-only), the rule is inert and nothing is auto-captured — if a decision must be retained, hand-write it into `memory/topics/<topic>.md` via a `docs` workflow;`

---

#### Cross-cutting note (applies to all "after" text)
Every remaining citation of `workflow/sdk-pipeline.md`, `hooks/memory-write-guard.sh`, `hooks/sdk-memory-pipeline.sh`, `skills/memory/`, or `capture-session.sh` in the shipped docs is a dangling reference in crux-only (none ship with the crux — `hooks/hooks.json` registers only `SessionStart → session-context.sh`). Each should be annotated inline with **"(ships with the `workflow-memory-pipeline` plugin; absent in crux-only)"** wherever it appears, not just at the locations enumerated above. The alternative, larger fix (out of scope for contract-patch) is to actually ship the pipeline + guard via the companion plugin so these assertions become true.

---

## 9. Recommended execution order

The four deliverables are sequenced by **blast-radius-per-unit-effort** and by dependency. The `workflow-memory-pipeline` plugin is **not touched** by any step — it remains the reserved, unimplemented companion; the work below only conditionalizes references to it (Deliverable 4) and never ships or modifies it.

### Step 0 — Cheap, high-value, no dependencies (do immediately)

**Deliverable 1 — harden `/workflow-init`** (edits one file, `commands/workflow-init.md`). This is the highest leverage per unit effort: it broadens and commits the secrets deny-list, adds `enabledPlugins` self-activation, writes the adopt-time version stamp, and gates the placeholder-CLAUDE.md edit. It closes or mitigates the largest secrets findings for **all future adoptions**, fixes the half-activation gap (F18-4), and lays the project side of the version-stamp scheme. No dependency on the other deliverables; ship first.

### Step 1 — The package re-cut (unblocks everything downstream)

**Deliverable 3 — the `repackage.sh` + provenance pipeline.** Build the scripted canonical→plugin re-cut, then cut **v0.2.0**. This single re-cut auto-resolves the confirmed temporal regressions (F0-4 verifier `permissionMode`, F0-5 shell-audit, F0-7 stack rules), writes the package-time provenance stamp (the other half of the version scheme), and — with `PROMOTE_PROTECT_SECRETS=true` — re-ships `protect-secrets.sh` as a runtime guard, giving secrets defense-in-depth alongside Deliverable 1's broadened deny-list. It is sequenced after Deliverable 1 only because the re-cut should bake in the hardened `workflow-init` PATCH; functionally the two can proceed in parallel, but the provenance fields and the `baseline/` data files this deliverable can emit are what make Deliverable 2 most accurate.

### Step 2 — Make crux-only truthful (do alongside or just after the re-cut)

**Deliverable 4 — contract-patch the crux-only doc assertions.** Conditionalize every memory/SDK-pipeline claim across `constitution.md` and `workflow/{README,phases,evaluation,communication,artifacts,migration}.md` + `rules/migrations.md` + `routing.md`, gating each on "when the `workflow-memory-pipeline` plugin is installed" and stating the crux-only reality. These are doc edits in the plugin tree; they ride into the **same v0.2.0 re-cut** as Deliverable 3 (the repackage copies whatever canonical/plugin docs hold, so the conditionalization should be authored as part of, or immediately before, the cut). Retires the 11-finding internal-truth class.

### Step 3 — The drift reconciler (depends on the stamps existing)

**Deliverable 2 — the new `workflow-refresh` plugin.** Build and register the third plugin. It depends on the version-stamp scheme being in place: it reads the adopt-time stamp (Deliverable 1) and the package-time provenance (Deliverable 3), and it consumes the broadened deny-list baseline and `baseline/` data files those deliverables produce. Shipping it last means it reconciles projects against an already-hardened, already-stamped plugin, and it can then retire the remaining `refresh`-class cruft findings (F2-1, F3-2, F7-3, F17-5) and re-stamp/upgrade the already-adopted projects.

### Step 4 — Operate

Once Deliverables 1–3 have shipped (v0.2.0) and Deliverable 2 is available:

1. Run `/workflow-init` in each intended-but-unadopted project (closes the entire adoption class: F9/F11/F14/F15/F16/F18/F19), enabling the plugin at project scope so the SessionStart hook fires.
2. Run `/workflow-refresh --apply` in each already-adopted project to broaden its deny-list, write its version stamp, and prune local cruft.
3. Adopt `scripts/check-drift.sh` (or `/workflow-doctor`) as a recurring check so future canonical movement surfaces a re-cut prompt instead of accruing invisibly.

### Dependency summary

| Order | Deliverable | Fix target | Depends on | Retires (classes) |
|---|---|---|---|---|
| 0 | D1 — `workflow-init` hardening | `workflow-init` | — | half-activation; project-side of provenance; part of secrets |
| 1 | D3 — repackage + provenance | `repackage` | D1 (PATCH baked in) | package divergence; package-side of provenance; secrets guard re-ship |
| 2 | D4 — crux-only contract-patch | `contract-patch` | rides D3's cut | internal-truth (memory/pipeline) |
| 3 | D2 — `workflow-refresh` plugin | `refresh` | D1 + D3 stamps | refresh-class cruft; ongoing project↔plugin drift |
| 4 | operate (`init` + `refresh` + `doctor`) | — | D1–D3 shipped, D2 available | adoption class; recurring drift detection |
