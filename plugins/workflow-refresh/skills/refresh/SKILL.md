---
name: refresh
description: Detect and repair drift between an adopted project's .claude/ and the currently installed workflow-shell plugin. Use when the orchestrator needs to programmatically check or reconcile a project against the installed plugin (post-/plugin update, onboarding a copy-adopted repo, or a CI drift gate). Dry-run by default; idempotent; never clobbers project-owned state. Does not adopt — that is /workflow-init.
---

# refresh — project↔plugin drift reconciler

Lets the orchestrator invoke the refresh engine without the `/workflow-refresh` slash command — e.g. as a
drift gate inside a larger flow, or to produce the `--json` report for another agent to consume.

The engine lives in `_scripts/` and is pure `python3` (no `jq` dependency):

| Script | Role |
|---|---|
| `resolve_plugin.py` | Resolve the **currently installed** workflow-shell (path/version/sha/provenance) for a project. The moving target. |
| `baseline.py` | Load the **expected** baseline: plugin `baseline/` → installed `workflow-init.md` `PATCH` → bundled defaults. Secrets = `union(installed, broadened)`. Also the single source for the cruft/placeholder/broad-allow signatures. |
| `detect.py` | Run every detector → the drift report JSON (`--render` pretty-prints a report from stdin). Never writes. |
| `repair.py` | Apply idempotent, mode-gated repairs. Additive merges; byte-match-gated deletions; project-owned files only with explicit flags; journals to the stamp. |
| `stamp.py` | Read/write `.claude/workflow/.workflow-version` (preserve-merge; co-owned with `/workflow-init`). |

## Invocation

```bash
SKILLS="${CLAUDE_PLUGIN_ROOT}/skills/refresh/_scripts"
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"

# Resolve + detect (read-only). The report's "exit" field: 0 clean · 10 drift · 20 residual-after-apply.
PLUGIN_JSON="$(python3 "$SKILLS/resolve_plugin.py" --project "$PROJ")"
python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON"            # JSON report
python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON" | \
  python3 "$SKILLS/detect.py" --render                                          # human summary

# Repair (writes). R-STAMP is always written last. Risky rules require their flag.
python3 "$SKILLS/repair.py" --project "$PROJ" --plugin "$PLUGIN_JSON" \
  --report "$(python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON")" \
  --apply [--strip-cruft] [--migrate-state] [--only=R-SEC,R-STAMP]
```

## Rules (ids surfaced in the report)

`R-PARSE` (settings file present but not valid JSON — refuses to touch settings, manual) · `R-STAMP`
(version stamp) · `R-SETTINGS` (outputStyle/enabledPlugins/subagents + subagent skills) · `R-STYLE` (custom
outputStyle override — info) · `R-SEC` (broadened + migrate-local deny union, auto-safe) · `R-SEC-ALLOW`
(broad allow — manual warn) · `R-SEC-HOOK` (guard hook absent — info) · `R-COPY` (stale plugin copies —
byte-match-gated) · `R-WORKTREE` (duplicated .claude in a git worktree — manual warn) · `R-STATE` (legacy
state.json — opt-in `--migrate-state`) · `R-CRUFT` / `R-ORPHAN-HOOK` (local cruft / orphan hooks — opt-in
`--strip-cruft`) · `R-CLAUDEMD` (placeholder — manual) · `R-MEM-DOC` (memory pipeline dormant in crux-only — info).

## Invariants

Idempotent (a no-change re-apply mutates nothing) · additive settings merge (never delete/overwrite a user
value) · byte-match gate for any deletion · project-owned content (`active.json`, `specs/**`, `queue.md`,
`CLAUDE.md` prose, user `allow`) is never auto-written · **does not adopt** — defers to `/workflow-init`.
