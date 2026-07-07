---
name: workflow-refresh
description: Detect and repair drift between THIS adopted project's .claude/ and the currently installed workflow-shell plugin. Dry-run by default; --apply to repair. Idempotent; never clobbers project-owned state (active.json, specs, queue.md, CLAUDE.md prose, user allow-rules). Does NOT adopt — run /workflow-init for an unadopted project.
argument-hint: "[--apply] [--check] [--json] [--only=R-..] [--migrate-state] [--strip-cruft]"
allowed-tools: Bash(python3:*), Bash(test:*), Bash(printf:*), Read
---

# Refresh the workflow shell in this project

Reconciles the project against the **currently installed** workflow-shell — pulling plugin improvements
forward, idempotently. It does **not** adopt: if the project is unadopted (no `.claude/active.json`) it
stops and tells you to run `/workflow-init`. The default run is **dry-run** (reports a plan, writes nothing).

What each mode does:

| Invocation | Behavior |
|---|---|
| `/workflow-refresh` | Dry-run: full drift report + proposed plan. **No writes.** Exit 10 if drift. |
| `/workflow-refresh --apply` | Apply all **safe + idempotent** rules (R-COPY, R-SETTINGS, R-SEC, R-STAMP), re-verify, print residual. |
| `/workflow-refresh --check` | CI mode: report only, non-zero exit on high/medium drift. No writes. |
| `/workflow-refresh --json` | Emit the machine-readable drift report (for tooling/subagents). |
| `/workflow-refresh --apply --strip-cruft` | Also prune local cruft (malformed/one-off `settings.local.json` allow entries). |
| `/workflow-refresh --apply --migrate-state` | Also non-destructively normalize legacy `specs/*/state.json`. |
| `/workflow-refresh --only=R-SEC,R-STAMP` | Run a subset of rules by id. |

> **Arg-substitution safety.** Like `/workflow-init`, this engine is run by the orchestrator via the Bash
> tool, and slash-command rendering blanks bare `$1`/`$ARGUMENTS` inside shell blocks. So flags are read in
> prose and forwarded through the **`FLAGS` shell variable** the orchestrator sets — never a bare positional.

**Orchestrator:** set `FLAGS` to exactly the flags the user typed (e.g. `FLAGS="--apply --strip-cruft"`, or
empty for a dry-run), then run this block:

```bash
set -e
SKILLS="${CLAUDE_PLUGIN_ROOT}/skills/refresh/_scripts"
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
FLAGS="${FLAGS:-}"                                   # orchestrator sets this from the user's flags

# 0. Guard: refresh reconciles an ADOPTED project; it never adopts.
if [ ! -f "$PROJ/.claude/active.json" ]; then
  echo "NOT ADOPTED: no .claude/active.json. Run /workflow-init first (refresh does not adopt)."; exit 1
fi

# 1. Resolve the currently installed workflow-shell (path/version/sha/provenance).
PLUGIN_JSON="$(python3 "$SKILLS/resolve_plugin.py" --project "$PROJ")"
printf '%s' "$PLUGIN_JSON" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("root") else 1)' \
  || { echo "Cannot resolve an installed workflow-shell for this project. Is the plugin installed?"; exit 1; }

# 2. Detect: build the drift report once (read-only).
REPORT="$(python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON")"

# 3. Dry-run / --check / --json paths all write NOTHING.
case " $FLAGS " in
  *" --json "*)
    printf '%s\n' "$REPORT"
    exit "$(printf '%s' "$REPORT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["exit"])')" ;;
  *" --apply "*) : ;;                                # fall through to repair
  *)                                                 # dry-run or --check: render + exit on report code
    printf '%s' "$REPORT" | python3 "$SKILLS/detect.py" --render
    exit "$(printf '%s' "$REPORT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["exit"])')" ;;
esac

# 4. Apply: idempotent, mode-gated repairs. Risky rules need their own flag; R-STAMP is written last.
python3 "$SKILLS/repair.py" --project "$PROJ" --plugin "$PLUGIN_JSON" --report "$REPORT" $FLAGS

# 5. Re-verify and print residual. Exit 20 if residual manual items remain (e.g. placeholder CLAUDE.md).
REPORT2="$(python3 "$SKILLS/detect.py" --project "$PROJ" --plugin "$PLUGIN_JSON" --applied)"
printf '%s' "$REPORT2" | python3 "$SKILLS/detect.py" --render
echo "--- refresh applied; stamp updated ---"
exit "$(printf '%s' "$REPORT2" | python3 -c 'import json,sys;print(json.load(sys.stdin)["exit"])')"
```

After the engine runs, the orchestrator should:

1. **Dry-run** — summarize the plan grouped by severity. Call out `manual` items the user must decide on
   (placeholder `CLAUDE.md`, broad `allow` wildcards, optional `--migrate-state`/`--strip-cruft`). Offer to
   re-run with `--apply` (plus any opt-in flags) once the user agrees.
2. **`--apply`** — report what was repaired vs. what is residual. If exit was `20`, list the residual
   `manual` items (they were intentionally **not** auto-written — project-owned content is never clobbered).
   For `R-CLAUDEMD`, offer to fill the one-liner + `## Stack` (with the user) rather than auto-authoring prose.
3. If the report notes `provenance: unavailable` or a missing `protect-secrets.sh` guard hook, surface that
   as an **upstream** recommendation: the installed package predates those — `/plugin update workflow-shell`
   to a repackaged build closes it. Refresh fixed the *project* side; the *package* fix is separate.

## What it never touches

`active.json` contents · `specs/**` bodies · `workflow/queue.md` body · `CLAUDE.md` prose · user `allow`
permissions. Settings are **additive-merged** (union deny, set-missing keys) — a user value is never
overwritten. Copy deletions are gated on a byte-match against the installed plugin file; divergent copies
and whole directories are reported, never auto-deleted.
