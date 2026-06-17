---
name: claude-code
description: Awareness rules for Claude Code first-party slash commands that mutate settings without confirmation. Always-on.
always: true
---

# Claude Code awareness rules

Rules covering behaviors of the Claude Code CLI itself that the workflow contract must accommodate. Not project conventions — these are upstream Anthropic behaviors that affect every project.

## Settings auto-write by first-party slash commands

Several slash commands write to `settings.json` WITHOUT a confirmation dialog (per Anthropic docs, retrieved 2026-05-12):

| Slash command | Writes |
|---|---|
| `/effort low\|medium\|high\|xhigh` | `effortLevel` in `~/.claude/settings.json` |
| `/voice` | voice-related settings in `~/.claude/settings.json` |
| `/skills` | `skillOverrides` in `<repo>/.claude/settings.local.json` |
| `/tui` | `tui` block in user-scope `settings.json` |

There is **no documented mechanism to disable** these auto-writes. `disableInteractiveSettingsWrites` (or equivalent) does not exist in Anthropic's schema.

## Mitigation chosen (sub-design 06)

1. **Commit canonical settings.** `<repo>/.claude/settings.json` is the team baseline, committed to git.
2. **`.local` overrides.** User-specific or machine-specific overrides land in `<repo>/.claude/settings.local.json`, gitignored.
3. **Periodic review.** Check `<repo>/.claude/settings.json` mtime; diff against the last committed version. If unintended changes appear (e.g., a stray `effortLevel` write from `/effort` ran in a sub-shell), restore from git.

**Precedence reminder** (highest → lowest, per Anthropic docs): Managed → CLI args → Local (`.claude/settings.local.json`) → Project (`.claude/settings.json`) → User (`~/.claude/settings.json`). Committed project-level settings WIN over user-level — this is the protection mechanism.

## Auto-memory canonical location

The auto-loaded memory directory is `~/.claude/projects/<project-slug>/memory/` by default, NOT `<repo>/.claude/memory/`. `autoMemoryDirectory` CAN be set in project-scope or local-scope `settings.json`, but is honored only after you accept the workspace-trust dialog (a cloned repo could otherwise redirect auto-memory writes to sensitive paths). We do not set it — the default canonical location plus the selective-mirror policy is our mechanism. `autoMemoryEnabled` (default `true`) gates auto-memory entirely; this repo does not disable it. [source: <https://code.claude.com/docs/en/settings>, retrieved 2026-05-30; corrected in spec 033]

`<project-slug>` is derived from cwd with `/` rewritten to `-` (e.g., `/Users/alice/Projects/foo` → `-Users-alice-Projects-foo`).

**Subagents inherit this auto-memory.** Every non-Explore/non-Plan custom subagent auto-loads the SAME canonical `MEMORY.md` the main session does — part of the inherited CLAUDE.md/memory hierarchy — independent of any `memory:` frontmatter. Spec 029 removed `memory: project` (dropping the per-agent *silo* load while leaving this shared canonical load intact); spec 034 re-introduced `memory: project` for the silo agents — now 6 after spec 047 marked `frontend-engineer` dormant (`product-manager`, `architect`, `backend-engineer`, `task-decomposer`, `qa-engineer`, `cross-checker`; canonical list `_budget_check.SILO_AGENTS`) — so each of them ALSO auto-loads its own `agent-memory/<agent>/MEMORY.md` silo on top of the shared canonical load. The SDK memory pipeline is the SOLE writer of those silos. The shared-canonical inheritance was verified by live recall test 2026-05-30 (`specs/033-subagent-memory-access-restore/design/subagent-memory-mechanics.md`). [source: <https://code.claude.com/docs/en/sub-agents#what-loads-at-startup>, retrieved 2026-05-30]

The repo-side `<repo>/.claude/memory/` is a git-tracked mirror, kept in sync by the SDK memory pipeline at every `deliver` (mirror mechanism contract: `workflow/sdk-pipeline.md`; index shape: `specs/012-workflow-contract-v2/design/04-memory-index-shape.md`). The pipeline is a propose→write split: the LLM half EMITS a proposal (no file writes) and a deterministic Python writer writes the canonical store and copies the non-personal subset into the repo mirror. The cross-checker verifies selective-mirror-policy compliance (NOT exact equality), with `agent-memory/` (the canonical-only silos) carved out of that check. Authoritative definition: `workflow/artifacts.md` "Selective mirror policy".

## Don't set `autoMemoryDirectory` in project or local settings

Not because it's rejected — it IS honored at project/local scope behind the workspace-trust dialog (the prior "silently rejected" claim was wrong; corrected 2026-05-30 in spec 033 with a live-docs citation). We don't set it because the default canonical location plus the selective-mirror policy is already our mechanism, and redirecting auto-memory adds risk without benefit. If you find it in `<repo>/.claude/settings.json`, remove it.
