# Migration

How to adopt the `.claude/` workflow shell into an existing project that has no prior workflow infrastructure. Distinct from greenfield (no existing code) and from the daily contract docs.

**Greenfield vs. migration.** Greenfield (brand-new repo, no code) starts with a `prd` workflow to define the system being built, then decomposes into specs. Migration (existing repo, months/years old) starts with a `docs` workflow to install the workflow shell into the existing repo, THEN considers `prd` once the team has a major change to define.

## 1. Prerequisites

- Working Claude Code installation, version ≥ 2.1.32 (Teams version floor; matches `specs/012-workflow-contract-v2/design/02-agent-teams-implement.md`).
- Git repository with at least one commit (rollback path).
- Team agreement to commit `.claude/` to the repo. The workflow shell is check-in-able; per-machine team config files inside `~/.claude/` are not.

## 2. Bootstrap the shell

If `.claude/` already exists in the target repo, use the side-by-side install protocol first (Section 2a). Otherwise proceed directly to Section 2b.

### 2a. Side-by-side install protocol (existing `.claude/` present)

Common case: the team has been using Claude Code with ad-hoc agents/skills/hooks. Do NOT auto-overwrite.

a. Copy the reference workflow shell to `.claude-v2/` (not `.claude/`).
b. Validate the v2 shell loads cleanly: start a Claude Code session with `CLAUDE_PROJECT_DIR=.claude-v2` (or equivalent); confirm `routing.md`, `phases.md`, and the orchestrator agent register.
c. Compare existing `.claude/` against `.claude-v2/` file by file. For each file:
   - **Only in `.claude-v2/`** → safe to copy into `.claude/` (additive).
   - **Only in `.claude/`** → keep as-is OR migrate per Section 2c.
   - **In both, identical** → no action.
   - **In both, divergent** → manual review: keep existing, replace with v2, or merge. NEVER auto-overwrite.
d. Once `.claude/` reflects the merged state and a clean session loads, remove `.claude-v2/`.

### 2b. Fresh install (no existing `.claude/`)

Ordered:

a. Create `.claude/` at repo root.
b. Author `.claude/CLAUDE.md` — project manifest. Required imports: `@workflow/README.md`, `@constitution.md`. Project-specific stack notes.
c. Author `.claude/constitution.md` — project's non-negotiable principles. Use the starter principles in the reference repo's `constitution.md` as a template; edit per project needs.
d. Copy `.claude/workflow/` from a reference repo (this repo, or a stripped-down sample). Includes: `README.md`, `phases.md`, `routing.md`, `artifacts.md`, `communication.md`, `evaluation.md`, `templates/*`.
e. Author `.claude/active.json` with empty `active`, `archived`, `prds` arrays.

### 2c. Discovery + categorization for existing agents / skills / hooks

When the target repo's pre-existing `.claude/` has its own customizations:

a. **Inventory** — list every file under existing `.claude/agents/`, `.claude/skills/`, `.claude/hooks/`. Group by purpose (research, engineering, product, review, ops, …).
b. **Categorize per the v2 layout** — map each existing agent to a category subfolder (`agents/<category>/<name>.md`). Same for skills (`skills/<category>/<name>/SKILL.md`).
c. **Reconcile frontmatter** — existing agents may lack required v2 frontmatter (`model`, `permissionMode`, `memory`, `tools`). Add the missing fields; preserve existing behavior unless explicitly changing.
d. **Reconcile tool allowlists** — v2 expects `tools:` as a comma-separated string. Convert if existing uses JSON array.
e. **Wire into orchestrator** — `agents/orchestrator.md` references the migrated agents by name; update delegation patterns to use them.
f. **Test the migration** — run a small `bugfix` workflow that exercises each migrated agent; surface any behavioral regressions before declaring migration complete.

### 2d. Bootstrap user-side memory (mirror seed)

The canonical auto-loaded memory location is `~/.claude/projects/<project-slug>/memory/` (per Anthropic docs; project-level `autoMemoryDirectory` is honored only behind the workspace-trust dialog, not rejected — corrected spec 033, see `rules/claude-code.md`; we keep the default and do not redirect it). The repo-side `.claude/memory/` is a git-tracked mirror.

If `~/.claude/projects/<project-slug>/memory/` is empty or missing on first session:

```
mkdir -p ~/.claude/projects/<project-slug>/memory
cp -r .claude/memory/* ~/.claude/projects/<project-slug>/memory/
```

`<project-slug>` is the cwd path with `/` rewritten to `-` (e.g., `/Users/alice/Projects/foo` → `-Users-alice-Projects-foo`). Subsequent runs of the SDK memory pipeline at `deliver` keep both locations in sync (see `specs/012-workflow-contract-v2/design/04-memory-index-shape.md`).

## 3. Retroactive scoping (existing code)

Two acceptable strategies — pick one per module:

**Strategy A — No retroactive specs.** Existing code is "legacy" from the workflow's perspective. New work files specs going forward; existing code is touched without specs only via `bugfix` or `refactor` workflows that scope to the touched area.

**Strategy B — Retroactive specs for active areas.** For modules under active development, file a `docs` workflow that produces a retrospective `spec.md` describing the existing module's contract. The retrospective spec sets the AC baseline so future `bugfix` / `refactor` work has a contract to verify against.

Most teams use Strategy A for stable code, Strategy B for hot areas.

## 4. Seed `memory/`

- Create `.claude/memory/` and `.claude/memory/topics/`.
- Seed `.claude/memory/topics/decisions.md` with 3–10 entries describing the project's most important architectural choices and the reasoning behind them.
- Seed `.claude/memory/MEMORY.md` as an index per the shape contract in `workflow/artifacts.md` (each line `- [Title](topics/file.md) — one-line hook ≤80 chars`; ≤200 lines OR ≤25KB).
- Optional starter topics: `conventions.md`, `incidents.md`.

## 5. Introduce `agents/`

- Create `.claude/agents/` with subdirectories per category (`product/`, `engineering/`, `review/`, `research/`, `ops/`).
- Author `agents/orchestrator.md` (the main session agent).
- Author phase-actor agents incrementally as the team adopts each workflow type. Don't author all 12+ at once; start with `product-manager`, `spec-verifier`, and a domain engineer matched to the project's stack.

## 6. Wire hooks

- Create `.claude/hooks/` and copy `capture-session.sh` (or equivalent) from a reference repo.
- Configure `.claude/settings.json` to wire `PreCompact` → `capture-session.sh` (and other hooks as needed).
- Hooks are optional for initial adoption; the workflow contract works without them. They become important once the SDK memory pipeline at `deliver` is enabled (see `workflow/sdk-pipeline.md`).

## 7. Opt-in for Agent Teams (deferred)

- DO NOT enable Agent Teams during initial migration. The teamed-implement contract (`specs/012-workflow-contract-v2/design/02-agent-teams-implement.md`) is for established teams that have run the sequential workflow successfully and want to optimize their bottleneck.
- Opt-in trigger: at least **3 successful sequential implements** under the team's belt before flipping to teamed. Then set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, ensure Claude Code version ≥ 2.1.32, and proceed per the lifecycle protocol in `specs/012-workflow-contract-v2/design/07-team-lifecycle.md`.

## 8. First workflow run

After bootstrapping:

- Pick a small `docs` or `bugfix` workflow as the first run — low stakes, full phase exercise.
- Walk through `spec → tasks → implement → verify → deliver` with the verifier-fixer loops engaged.
- Review the experience as a team; tune `constitution.md` and `templates/` based on what felt off.

## 9. When to file a `prd` workflow

- Defer `prd` until at least 3 successful single-spec workflow runs have built team familiarity.
- Then, when a multi-feature or platform-level change comes up, file `prd` per `routing.md`'s PRD branch.

## Onboarding checklist

A condensed view for the team lead:

- [ ] Claude Code ≥ 2.1.32 installed; git repo has ≥ 1 commit.
- [ ] Existing `.claude/` reconciled via 2a, OR fresh `.claude/` bootstrapped via 2b.
- [ ] CLAUDE.md, constitution.md, workflow/ in place.
- [ ] active.json initialized.
- [ ] User-side memory mirror seeded via 2d.
- [ ] Retroactive scoping strategy chosen (A or B) per module.
- [ ] memory/ seeded with starter decisions.
- [ ] Initial agents authored (orchestrator + 2–3 phase actors).
- [ ] Hooks wired if SDK memory pipeline is in scope.
- [ ] First small workflow run completed end-to-end.
- [ ] Agent Teams deferred until 3 successful sequential implements.
