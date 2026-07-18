---
name: workflow-init
description: Adopt the workflow-shell contract into THIS project. Seeds CLAUDE.md, active.json, a blank queue.md, memory scaffolding, and a .workflow-version stamp; MERGES settings.json (outputStyle + enabledPlugins self-activation + subagent wiring + a broad secrets deny-list); provisions the memory pipeline's .claude/.venv via uv. Idempotent — never clobbers existing files; merges/upserts instead of overwriting.
argument-hint: [project-name]
allowed-tools: Bash(mkdir:*), Bash(test:*), Bash(jq:*), Bash(python3:*), Bash(basename:*), Bash(printf:*), Bash(command:*), Bash(mktemp:*), Bash(mv:*), Bash(uv:*), Bash(grep:*), Bash(touch:*), Bash(cp:*), Read
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
mkdir -p .claude .claude/workflow .claude/specs .claude/sessions \
         .claude/memory/topics \
         .claude/agent-memory/architect .claude/agent-memory/backend-engineer \
         .claude/agent-memory/cross-checker .claude/agent-memory/product-manager \
         .claude/agent-memory/qa-engineer .claude/agent-memory/task-decomposer
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
PATCH='{"outputStyle":"Workflow Orchestrator","enabledPlugins":{"workflow-shell@workflow-shell-marketplace":true},"subagents":{"orchestrator":{"skills":["workflow-advance","workflow-rollback","workflow-status","workflow-new"]},"product-manager":{"skills":["workflow-advance"]},"task-decomposer":{"skills":["workflow-advance"]}},"permissions":{"deny":["Read(./.env)","Read(./.env.*)","Read(**/.env)","Read(**/.env.*)","Edit(./.env)","Edit(./.env.*)","Edit(**/.env)","Edit(**/.env.*)","Write(./.env)","Write(./.env.*)","Write(**/.env)","Write(**/.env.*)","Read(./credentials.json)","Read(**/credentials.json)","Edit(./credentials.json)","Edit(**/credentials.json)","Write(./credentials.json)","Write(**/credentials.json)","Read(./service-account*.json)","Read(**/service-account*.json)","Edit(./service-account*.json)","Edit(**/service-account*.json)","Write(./service-account*.json)","Write(**/service-account*.json)","Read(**/*-key.json)","Edit(**/*-key.json)","Write(**/*-key.json)","Read(**/*.pem)","Edit(**/*.pem)","Write(**/*.pem)","Read(**/*.key)","Edit(**/*.key)","Write(**/*.key)","Read(**/id_rsa)","Read(**/id_dsa)","Read(**/id_ecdsa)","Read(**/id_ed25519)","Edit(**/id_rsa)","Edit(**/id_dsa)","Edit(**/id_ecdsa)","Edit(**/id_ed25519)","Write(**/id_rsa)","Write(**/id_dsa)","Write(**/id_ecdsa)","Write(**/id_ed25519)","Read(**/.aws/**)","Edit(**/.aws/**)","Write(**/.aws/**)","Read(**/.npmrc)","Read(**/.pypirc)"]}}'
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

# 5. Version stamp — record which workflow-shell version this project was adopted against.
#    Upsert: keep first adoptedVersion/adoptedAt; always refresh lastInitVersion/lastInitAt.
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
# Preserve-merge: start from prev so any keys other tooling may have written survive a re-init.
# init only OWNS the four keys it sets below.
out = dict(prev)
out["plugin"] = "workflow-shell@workflow-shell-marketplace"
out.setdefault("adoptedVersion", ver)
out.setdefault("adoptedAt", now)
out["lastInitVersion"] = ver
out["lastInitAt"] = now
with open(stamp, "w") as fh:
    json.dump(out, fh, indent=2)
print("stamped .claude/workflow/.workflow-version (version %s)" % ver)
PY

# 6. Memory-pipeline runtime — provision .claude/.venv with claude-agent-sdk (idempotent).
#    The SDK memory pipeline (sole memory writer at deliver) runs from this per-project venv.
if [ -x .claude/.venv/bin/python ] && .claude/.venv/bin/python -c 'import claude_agent_sdk' 2>/dev/null; then
  echo "kept existing .claude/.venv (claude-agent-sdk present)"
elif command -v uv >/dev/null 2>&1; then
  { uv venv .claude/.venv --python 3.13 || uv venv .claude/.venv; } >/dev/null 2>&1
  if uv pip install --python .claude/.venv/bin/python claude-agent-sdk >/dev/null 2>&1; then
    echo "provisioned .claude/.venv (claude-agent-sdk installed)"
  else
    echo "WARN: venv created but claude-agent-sdk install failed (network?) — memory writes stay inert until you run: uv pip install --python .claude/.venv/bin/python claude-agent-sdk"
  fi
else
  echo "WARN: uv not found — memory pipeline not provisioned. Run once: uv venv .claude/.venv --python 3.13 && uv pip install --python .claude/.venv/bin/python claude-agent-sdk"
fi

# 6b. Seed the extraction-learnings skill PROJECT-SIDE (only if absent). The memory pipeline
#     APPENDS learned heuristics to this file at every deliver — an append target is per-project
#     data and must never live in the plugin cache (which is replaced on update).
if [ ! -f .claude/skills/memory/extraction-learnings/SKILL.md ] && [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] \
   && [ -f "${CLAUDE_PLUGIN_ROOT}/skills/memory-extraction-learnings/SKILL.md" ]; then
  mkdir -p .claude/skills/memory/extraction-learnings
  cp "${CLAUDE_PLUGIN_ROOT}/skills/memory-extraction-learnings/SKILL.md" .claude/skills/memory/extraction-learnings/SKILL.md
  echo "seeded .claude/skills/memory/extraction-learnings/SKILL.md (pipeline append target)"
else
  echo "kept existing extraction-learnings (or plugin root unavailable)"
fi

# 7. .gitignore — keep the venv and raw session captures out of the project's git (idempotent appends)
touch .gitignore
grep -qxF '.claude/.venv/' .gitignore || printf '%s\n' '.claude/.venv/' >> .gitignore
grep -qxF '.claude/sessions/' .gitignore || printf '%s\n' '.claude/sessions/' >> .gitignore
echo "ensured .gitignore covers .claude/.venv/ and .claude/sessions/"
echo "--- done ---"
```

> **Two known limits of the settings deny-list** (both owned by other deliverables, not this command):
> it **cannot gate Bash-arg reads** (`cat .env`) — that needs the `protect-secrets.sh` PreToolUse hook
> (repackage deliverable); and because `permissions.deny` wins over `allow`, a broad `Read(*)`/`Write(*)`
> in a project's `settings.local.json` does **not** defeat these entries. The `.env.example`/`.sample`/
> `.template` allow-list short-circuit is intentionally **not** expressed here (settings `deny` cannot
> negate) and is deferred to the runtime hook.

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
   - `.claude/settings.json` `permissions.deny` includes the secret patterns,
   - `.claude/memory/topics/` and the 6 `.claude/agent-memory/<actor>/` silos exist,
   - `.claude/.venv/bin/python` imports `claude_agent_sdk` (else surface the WARN from step 6 —
     adoption is still valid, but deliver-time memory writes stay inert until the venv exists).
   If `enabledPlugins` is not set, the SessionStart hook never fires (active.json gate is moot) —
   the patch in step 4 now sets it, but verify it merged.
