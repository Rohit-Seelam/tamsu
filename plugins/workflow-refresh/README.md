# workflow-refresh

The **drift reconciler** for the workflow shell. The third plugin in `workflow-shell-marketplace`:

```
canonical → (repackage) → workflow-shell plugin → (/plugin update) → installed → (workflow-refresh) → project
```

`workflow-refresh` is the **last hop**. It detects and repairs drift between an *already-adopted* project's
`.claude/` and the *currently installed* `workflow-shell` — pulling plugin improvements forward,
idempotently, **without ever clobbering project-owned state**. It does **not** adopt a project (that is
`/workflow-init`); if a project is unadopted it refuses and defers.

## When to use it

- After `/plugin update workflow-shell` — re-reconcile each adopted project to the new package.
- Onboarding a project that adopted the shell long ago (or via the old `cp -R` copy approach).
- As a CI/drift gate (`/workflow-refresh --check` → non-zero exit on high/medium drift).

## Usage

```text
/workflow-refresh                 # dry-run: full drift report + plan, NO writes
/workflow-refresh --apply         # apply safe+idempotent rules, re-verify, print residual
/workflow-refresh --check         # CI: report only, non-zero exit on high/medium drift
/workflow-refresh --json          # machine-readable report
/workflow-refresh --apply --strip-cruft     # also prune local settings.local.json cruft
/workflow-refresh --apply --migrate-state   # also normalize legacy specs/*/state.json
/workflow-refresh --only=R-SEC,R-STAMP      # run a subset of rules
```

Default is **dry-run**: it reports and writes nothing. `--apply` runs only the safe, idempotent rules;
risky rules need their explicit opt-in flag; `manual` items (placeholder `CLAUDE.md`, broad `allow`
wildcards) are always report-only.

## What it reconciles

| Rule | Drift | Mode |
|---|---|---|
| `R-PARSE` | a `settings*.json` exists but is not valid JSON | manual (refuses to read/write settings until fixed) |
| `R-STAMP` | `.claude/workflow/.workflow-version` absent or behind the installed version | auto-safe |
| `R-SETTINGS` | `outputStyle` / `enabledPlugins` self-activation / subagent wiring or **skills** missing | auto-safe |
| `R-STYLE` | project sets a custom `outputStyle` (acknowledged override) | info (left as-is) |
| `R-SEC` | committed deny-list narrower than the broadened baseline, or deny living only in `settings.local.json` | auto-safe (union-only) |
| `R-SEC-ALLOW` | broad `Read(*)`/`Write(*)`/bare `Bash` allow undercuts the deny-list | manual (warn) |
| `R-SEC-HOOK` | installed package ships no `protect-secrets.sh` guard hook | info (upstream) |
| `R-COPY` | stale plugin-owned file copies left in the project | auto-safe (byte-match only) |
| `R-WORKTREE` | duplicated `.claude/{agents,commands}` inside a git worktree | manual (warn) |
| `R-STATE` | legacy `state.json` schema | opt-in `--migrate-state` |
| `R-CRUFT` / `R-ORPHAN-HOOK` | one-off / malformed local permissions, orphan hook reminders | opt-in `--strip-cruft` |
| `R-CLAUDEMD` | placeholder `CLAUDE.md` never edited | manual |
| `R-MEM-DOC` | memory/pipeline asserted but `workflow-memory-pipeline` not installed (crux-only) | info |

## Guarantees

- **Never overwrites corrupt config** — if a `settings*.json` exists but is not valid JSON (a trailing
  comma, a `//` comment, git merge-conflict markers), refresh reports `R-PARSE` and **refuses to read or
  write** settings until you fix it — it never rewrites an unparseable file to a baseline and wipes it.
- **Idempotent** — a no-change re-apply mutates nothing (zero mtime churn).
- **Additive** — settings are union/set-missing merged; a user value is never overwritten or deleted (an
  explicit `enabledPlugins: false` and a custom `outputStyle` are both preserved).
- **Byte-match-gated deletions** — a stale copy is removed only if it byte-matches the installed plugin
  file; divergent copies and whole directories are reported, never auto-deleted.
- **Project-owned content is sacred** — `active.json` contents, `specs/**` bodies, `queue.md` body,
  `CLAUDE.md` prose, and user `allow` permissions are never auto-written.
- **Stays correct as the plugin moves** — the baseline is always derived from whatever `workflow-shell`
  version is installed *right now*, never a constant baked into refresh.

## Version stamp

Refresh maintains `.claude/workflow/.workflow-version` (co-owned with `/workflow-init`; preserve-merged so
neither tool drops the other's keys). It records the adopted and last-refreshed plugin version/sha, the
canonical provenance (when the package carries it), and an audit trail of applied rules — making drift
**detectable** and end-to-end provenance **visible**.

## Layout

```
workflow-refresh/
├── .claude-plugin/plugin.json
├── commands/workflow-refresh.md      # slash command (orchestrator runs the engine)
├── baseline/                         # fallback baselines (the broadened secrets superset lives here)
│   ├── secrets.deny.json
│   ├── settings.expected.json
│   ├── copy-artifacts.txt
│   └── state-schema.json
└── skills/refresh/
    ├── SKILL.md                      # programmatic invocation
    └── _scripts/{resolve_plugin,baseline,detect,repair,stamp}.py
```
