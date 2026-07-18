# workflow-shell-marketplace

A Claude Code **marketplace** distributing the spec-driven workflow shell as a single installable
plugin — replacing the old `cp -R` / `adopt-workflow` copy approach.

## The plugin

| Plugin | Status | What it is |
|---|---|---|
| `workflow-shell` | ✅ v0.4.0 | Everything: routing, the 6-phase state machine, verifier/fixer loops, the categorized agent tree, the workflow skills (+ shared `_scripts`), the full hook surface (secrets guard, memory-write guard, 350K context-budget check, session capture/compile, budget/lint), the **SDK memory pipeline** (sole memory writer at `deliver`; `/workflow-init` provisions its per-project `.venv`), and the `Workflow Orchestrator` output style. |

## Install

```text
# From GitHub:
/plugin marketplace add Rohit-Seelam/workflow-shell-marketplace
/plugin install workflow-shell@workflow-shell-marketplace

# Local (while iterating on the marketplace repo itself):
/plugin marketplace add /Users/rohitseelam/Projects/workflow-shell-marketplace
/plugin install workflow-shell@workflow-shell-marketplace
```

**Prerequisites (once per machine):**
- **`jq`** — the memory-write guard and the session-capture / budget / lint hooks parse hook stdin with it
  (`brew install jq`). Without it those hooks no-op noisily; the secrets guard and contract injection are
  python3-only and unaffected.
- **`uv`** — `/workflow-init` uses it to provision the memory pipeline's per-project Python environment
  (`.claude/.venv` with `claude-agent-sdk`). If absent, init prints the one manual command instead.

Then, **in each project** you want to run the workflow:

```text
/workflow-init        # seeds .claude/{CLAUDE.md, active.json, workflow/queue.md, memory scaffolding},
                      # merges settings.json, provisions .claude/.venv for the memory pipeline
/clear                # binds the Workflow Orchestrator output style (output styles load at session start)
```

That's it. The contract docs, skills, agents, hooks, and behavior come from the plugin; only per-project
state lives in the project's `.claude/`.

## Updating adopted projects

```text
/plugin marketplace update workflow-shell-marketplace
claude plugin update workflow-shell@workflow-shell-marketplace --scope project   # in each project
```

Restart the session after updating. Re-running `/workflow-init` afterwards is safe and recommended — it is
idempotent (merges, never clobbers) and fills in anything a newer plugin version expects (settings keys,
memory scaffolding, the `.venv`).

## How the two hard problems are solved

1. **Auto-loading the contract.** Plugins have no declarative always-on context, and a project `CLAUDE.md`
   cannot reliably `@`-import a plugin file (the cache path carries a version hash and changes on update).
   So a **SessionStart hook** (`hooks/session-context.sh`, gated on `.claude/active.json`) injects
   `workflow/README.md` + `constitution.md` each session via `additionalContext`, using
   `${CLAUDE_PLUGIN_ROOT}`. The rest of `workflow/` loads on demand. The plugin ships the full hook
   surface alongside it (secrets + memory-write guards, the 350K context-budget check, session
   capture/compile, budget/lint) wired in `hooks/hooks.json`.
2. **The output style.** Bundled at `output-styles/workflow-orchestrator.md` (un-forced). `/workflow-init`
   sets `outputStyle: "Workflow Orchestrator"` in the **project** `settings.json`, scoping the behavior to
   adopted projects (rather than `force-for-plugin`, which would apply it globally).

## Migrating a copy-adopted project to the plugin

For a project that previously got the shell via `cp -R` / `adopt-workflow` (or a messy earlier adoption),
the clean path is a backup-and-reinit:

1. Back up the old state: `mv .claude ".claude.bak-$(date +%Y%m%d-%H%M%S)"`
2. Install/update the plugin (above) and run `/workflow-init` for a fresh, current adoption.
3. Copy anything you still want (in-flight `specs/`, `active.json`, `queue.md` entries, decisions) from the
   backup into the fresh `.claude/`.
4. `/clear` and verify the SessionStart hook injects the contract.

## Fate of retired components

- **`adopt-workflow`** (copy-based skill) — removed 2026-06-17; `/workflow-init` replaces it.
- **`workflow-memory-pipeline`** (separate memory plugin) — never built as a separate plugin; the SDK
  memory pipeline ships inside `workflow-shell` since 0.3.0.
- **`workflow-refresh`** (drift reconciler plugin) — retired at 0.4.0 in favor of the simpler
  backup-and-reinit flow above; `/workflow-init` is idempotent and safe to re-run after every update.

## Repo layout

```
workflow-shell-marketplace/
├── .claude-plugin/marketplace.json
└── plugins/
    └── workflow-shell/              # the single plugin, incl. memory pipeline
```
