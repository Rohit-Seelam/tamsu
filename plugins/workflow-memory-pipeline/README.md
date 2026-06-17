# workflow-memory-pipeline (reserved slot — not yet implemented)

The second half of the two-part workflow distribution. The crux (`workflow-shell`) deliberately
ships **without** memory so it works standalone; this companion plugin will package the SDK memory
pipeline — **the sole memory writer**, which runs at every `deliver`.

## What it will package (the "identical part" excluded from the crux)

From `/Users/rohitseelam/Projects/scratchpad-priv/.claude`:
- `hooks/` — `sdk_memory_pipeline.py`, `capture-session.sh`, `compile-session.sh`, `memory-write-guard.sh`
- `workflow/sdk-pipeline.md` — the propose→write contract
- `settings.sdk-memory.json` — pipeline settings
- `skills/memory/` — `compile`, `extract`, `jsonl-format`, `extraction-learnings`
- `agent-memory/` silo scaffolding consumed by the 6 silo agents

## Open design problems to resolve before building (carried from the audit)

1. **Plugin hooks vs the constitution's Rule 5 guard.** `memory-write-guard.sh` enforces "SDK pipeline is
   the sole memory writer." As a plugin hook it must locate the project's `memory/` via `$CLAUDE_PROJECT_DIR`,
   not a hardcoded `.claude`.
2. **Where memory is written.** The pipeline writes the project's `memory/` + `~/.claude/projects/<slug>/memory/`.
   A plugin ships globally; the writer targets must stay project-scoped.
3. **Multi-agent rework.** Per the source queue's `memory-pipeline-multiagent` item, the pipeline is slated to
   move from a single subprocess to parallel `query()` slice-proposers. Package after that lands, not before.

Until then, `workflow-shell`'s `constitution.md` Rule 5 and `CLAUDE.md` memory-strategy references stay
**dormant by design** — they describe a writer that simply isn't installed yet.
