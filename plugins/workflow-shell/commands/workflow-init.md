---
name: workflow-init
description: Adopt the workflow-shell contract into THIS project. Seeds CLAUDE.md, active.json, and a blank queue.md, then MERGES settings.json (outputStyle + subagent wiring + secrets deny-list). Idempotent — never clobbers existing files; merges instead of overwriting.
argument-hint: [project-name]
allowed-tools: Bash(mkdir:*), Bash(test:*), Bash(jq:*), Bash(python3:*), Bash(basename:*), Bash(printf:*), Bash(command:*), Bash(mktemp:*), Bash(mv:*), Read
---

# Initialize the workflow shell in this project

Replaces the old `adopt-workflow` Step 2. The plugin already provides the contract docs, skills, agents,
and the `Workflow Orchestrator` output style — this command only seeds the **per-project** files and
activates the style. It is **idempotent**: existing files are left untouched; `settings.json` is merged.

> **Arg-substitution safety.** Slash-command rendering blanks bare `$1`/`$2`/`$ARGUMENTS` inside shell
> blocks. The block below therefore uses **named shell variables only** (`$SETTINGS`, `$PATCH`, `$NAME`)
> and never a bare positional. An optional project name typed after the command is read in prose, not shell.

Run the seeding engine (safe to run repeatedly):

```bash
set -e
mkdir -p .claude .claude/workflow
NAME="$(basename "$PWD")"

# 1. CLAUDE.md — seed only if absent
if [ ! -f .claude/CLAUDE.md ]; then
cat > .claude/CLAUDE.md <<EOF
# ${NAME}

<one-line description — EDIT THIS>

## Workflow shell

This project runs the **workflow-shell** plugin. The workflow contract (routing, phases, constitution,
agents, skills) is provided by the plugin and is NOT copied here. Each session, the plugin's SessionStart
hook injects \`workflow/README.md\` + \`constitution.md\`; the \`Workflow Orchestrator\` output style
(set in settings.json) drives behaviour; the rest of the contract loads on demand from the plugin.

If the contract is missing, install it:
\`/plugin install workflow-shell@workflow-shell-marketplace\`, then re-run \`/workflow-init\`.

## Stack
- EDIT: languages, frameworks, entry points for this project.

## Project state (lives here, under .claude/)
- \`active.json\` — in-flight / queued / archived specs
- \`specs/<NNN-slug>/\` — per-spec artifacts + \`state.json\`
- \`workflow/queue.md\` — pre-spec brainstorming backlog

## Conventions
- File paths in artifacts are relative to repo root.
- PR titles: \`[NNN-slug] short description\`.
EOF
echo "seeded .claude/CLAUDE.md"
else echo "kept existing .claude/CLAUDE.md"; fi

# 2. active.json — seed only if absent
if [ ! -f .claude/active.json ]; then
  printf '%s\n' '{ "active": [], "queued": [], "archived": [], "prds": [] }' > .claude/active.json
  echo "seeded .claude/active.json"
else echo "kept existing .claude/active.json"; fi

# 3. queue.md — blank brainstorming pad, seed only if absent
if [ ! -f .claude/workflow/queue.md ]; then
cat > .claude/workflow/queue.md <<'EOF'
# Workflow queue — planning state

Pre-spec slug brainstorming, hand-edited. Slug-based, readiness-bucketed. An item lives here until it is
authored as a real spec; then its slug exits the bucket and a `specs/<NNN-slug>/` folder appears.

This file is workflow domain. Memory is for landed decisions only — pending items NEVER live in memory.

## Now

(empty)

## Next

(empty)

## Later

(empty)
EOF
echo "seeded .claude/workflow/queue.md"
else echo "kept existing .claude/workflow/queue.md"; fi

# 4. settings.json — MERGE (deep-merge; union the deny list; never clobber existing keys)
SETTINGS=.claude/settings.json
[ -f "$SETTINGS" ] || printf '%s\n' '{}' > "$SETTINGS"
PATCH='{"outputStyle":"Workflow Orchestrator","subagents":{"orchestrator":{"skills":["workflow-advance","workflow-rollback","workflow-status","workflow-new"]},"product-manager":{"skills":["workflow-advance"]},"task-decomposer":{"skills":["workflow-advance"]}},"permissions":{"deny":["Read(./.env)","Read(./.env.*)","Edit(./.env)","Edit(./.env.*)","Write(./.env)","Write(./.env.*)","Read(./credentials.json)","Read(./service-account*.json)"]}}'
if command -v jq >/dev/null 2>&1; then
  TMP="$(mktemp)"
  jq --argjson p "$PATCH" '. as $o | ($o * $p) | .permissions.deny = ((($o.permissions.deny) // []) + (($p.permissions.deny) // []) | unique)' "$SETTINGS" > "$TMP" && mv "$TMP" "$SETTINGS"
  echo "merged .claude/settings.json (jq)"
else
  python3 - "$SETTINGS" "$PATCH" <<'PY'
import json, sys
path, patch = sys.argv[1], json.loads(sys.argv[2])
try: cur = json.load(open(path))
except Exception: cur = {}
def merge(a, b):
    for k, v in b.items():
        if k == "permissions" and isinstance(v, dict):
            a.setdefault("permissions", {})
            for pk, pv in v.items():
                if pk == "deny":
                    a["permissions"]["deny"] = sorted(set(a["permissions"].get("deny", [])) | set(pv))
                else:
                    a["permissions"][pk] = pv
        elif isinstance(v, dict):
            base = a.get(k) if isinstance(a.get(k), dict) else {}
            a[k] = merge(base, v)
        else:
            a[k] = v
    return a
json.dump(merge(cur, patch), open(path, "w"), indent=2)
PY
  echo "merged .claude/settings.json (python)"
fi
echo "--- done ---"
```

After the engine runs:

1. If the user passed a project name argument, offer to replace the `# <basename>` heading and the
   `<one-line description>` line in `.claude/CLAUDE.md` with it; otherwise tell them to edit those two
   lines plus the Stack section.
2. Report what was seeded vs. kept (from the echoes above).
3. Remind them: the `Workflow Orchestrator` output style binds at session start — run `/clear` (or reopen)
   to activate it. The SessionStart hook will then inject the contract every session.
4. Confirm the adapted compliance check passes (see the plugin's `commands/` companion or run the
   project-side asserts: CLAUDE.md present, active.json valid with 4 arrays, queue.md present,
   settings.json has `outputStyle: "Workflow Orchestrator"`).
