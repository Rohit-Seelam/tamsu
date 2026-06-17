#!/usr/bin/env bash
# SessionStart hook for workflow-shell.
# Injects the always-on contract (workflow/README.md + constitution.md) into the session,
# but ONLY when this project has been adopted (.claude/active.json exists). This is the
# plugin-native replacement for the old project-CLAUDE.md @-imports.
#
# Hook scripts are plain bash (no slash-command arg substitution), so positional/env vars are safe.
set -euo pipefail

PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
ROOT="${CLAUDE_PLUGIN_ROOT:-}"

# Gate: do nothing in non-adopted projects (keeps the hook silent everywhere else the plugin is enabled).
[ -f "$PROJ/.claude/active.json" ] || exit 0
[ -n "$ROOT" ] || exit 0

# Emit SessionStart additionalContext as JSON. python3 (already required by the workflow skills)
# json-escapes the file contents; no jq dependency.
python3 - "$ROOT" <<'PY'
import json, sys, os
root = sys.argv[1]
parts = [
    "# Workflow shell active (plugin: workflow-shell)\n",
    f"Full contract docs live at `{root}/workflow/` and `{root}/constitution.md` — read the rest "
    f"(phases, routing, artifacts, communication, evaluation, migration) on demand from there.\n",
    "Project state lives under `./.claude/` (active.json, specs/, workflow/queue.md). "
    "The `Workflow Orchestrator` output style governs behaviour.\n",
    "\nThe two always-on docs follow.\n",
]
for label, rel in (("workflow/README.md", "workflow/README.md"), ("constitution.md", "constitution.md")):
    path = os.path.join(root, rel)
    try:
        with open(path) as fh:
            parts.append(f"\n\n---\n\n# {label}\n\n" + fh.read())
    except OSError:
        parts.append(f"\n\n(could not read {label})")
ctx = "".join(parts)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
PY
