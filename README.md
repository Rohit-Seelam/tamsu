# workflow-shell-marketplace

A Claude Code **marketplace** distributing the spec-driven workflow shell as installable plugins —
replacing the old `cp -R` / `adopt-workflow` copy approach.

## Plugins

| Plugin | Status | What it is |
|---|---|---|
| `workflow-shell` | ✅ v0.1.0 | The **crux**: routing, the 6-phase state machine, verifier/fixer loops, the categorized agent tree, the workflow skills (+ shared `_scripts`), and the `Workflow Orchestrator` output style. |
| `workflow-memory-pipeline` | 🔒 reserved slot | The optional SDK memory pipeline (sole memory writer at `deliver`). Not yet implemented — see its `README.md`. The crux works without it. |

## Install

```text
# Local (recommended while iterating):
/plugin marketplace add /Users/rohitseelam/Projects/workflow-shell-marketplace
/plugin install workflow-shell@workflow-shell-marketplace

# From GitHub (after you push this repo):
/plugin marketplace add <owner>/workflow-shell-marketplace
/plugin install workflow-shell@workflow-shell-marketplace
```

Then, **in each project** you want to run the workflow:

```text
/workflow-init        # seeds .claude/{CLAUDE.md, active.json, workflow/queue.md}, merges settings.json
/clear                # binds the Workflow Orchestrator output style (output styles load at session start)
```

That's it. The contract docs, skills, agents, and behavior come from the plugin; only per-project state
lives in the project's `.claude/`.

## How the two hard problems are solved

1. **Auto-loading the contract.** Plugins have no declarative always-on context, and a project `CLAUDE.md`
   cannot reliably `@`-import a plugin file (the cache path carries a version hash and changes on update).
   So a **SessionStart hook** (`hooks/session-context.sh`, gated on `.claude/active.json`) injects
   `workflow/README.md` + `constitution.md` each session via `additionalContext`, using
   `${CLAUDE_PLUGIN_ROOT}`. The rest of `workflow/` loads on demand. This is the only hook in the crux —
   it is **not** the SDK memory pipeline.
2. **The output style.** Bundled at `output-styles/workflow-orchestrator.md` (un-forced). `/workflow-init`
   sets `outputStyle: "Workflow Orchestrator"` in the **project** `settings.json`, scoping the behavior to
   adopted projects (rather than `force-for-plugin`, which would apply it globally).

## Migrating a copy-adopted project to the plugin

For a project that previously got the shell via `cp -R` / `adopt-workflow`:

1. Install the plugin (above).
2. Run `/workflow-init`. It is idempotent — it keeps your existing `CLAUDE.md`/`active.json`/`queue.md` and
   only merges `settings.json` (adds `outputStyle` + subagent wiring, unions the secrets deny-list).
3. **Delete the now-duplicated, plugin-provided copies** from the project so there's one source of truth:
   `rm -rf .claude/workflow/{README,phases,routing,artifacts,communication,evaluation,migration}.md .claude/workflow/templates .claude/skills/workflow* .claude/agents .claude/constitution.md .claude/rules`
   Keep **only** the project files: `.claude/CLAUDE.md`, `.claude/active.json`, `.claude/workflow/queue.md`,
   `.claude/specs/`, `.claude/settings.json` (and `memory/` if you run the pipeline).
4. `/clear` and verify the SessionStart hook injects the contract.

> Edit your project `CLAUDE.md`: drop the old `@workflow/README.md` / `@constitution.md` imports (the hook
> now provides them) and keep the project name + stack + state pointers.

## Fate of `adopt-workflow`

The old copy-based `~/.claude/skills/adopt-workflow` skill has been **removed** (2026-06-17). This plugin
fully replaces it — install it and run `/workflow-init` instead.

## Repo layout

```
workflow-shell-marketplace/
├── .claude-plugin/marketplace.json
└── plugins/
    ├── workflow-shell/              # crux plugin (see plugins/workflow-shell)
    └── workflow-memory-pipeline/    # reserved slot + build plan
```
