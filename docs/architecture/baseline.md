# tamsu: my Claude Code harness (baseline design)

**Status:** final draft for review, 2026-10-17. Nothing is built yet.
**Sources:**
- my work-laptop methodology KT (2026-10-17)
- Anthropic, "Effective harnesses for long-running agents" (2025-11-26)
- Claude Code docs: best practices, memory, plugins, hooks, sub-agents (read 2026-10-17)
- Opus 5 / 5.5 prompting guides
- community setups (Trail of Bits `claude-code-config`, HumanLayer)

**Names:**
- `tamsu` is the repo, the folder and the marketplace. It replaces `workflow-shell-marketplace`;
  the GitHub repo is renamed and made public.
- `oskiv` is the plugin inside it, installed as `oskiv@tamsu` and starting at **1.0.0**.
- Each release bumps the version in both manifests; the bump is what delivers a release.
- `workflow-shell` 0.4.1 stays in git history, so its pieces can be brought back one at a time.

## Goal

Every repo I start gets my method, not a vanilla setup. Any new session, main or subagent, knows
where things go, what to build next and how to tell when it's done, without my repeating it.

**A baseline, not a finished system.** 0.4.x tried to be complete and took months. The official
guidance agrees with starting small:
- "If Claude already does something correctly without the instruction, delete it or convert it to
  a hook."
- Anthropic's own repo CLAUDE.md is 40 lines.
- Opus 5 needs fewer instructions than earlier models.

**A line is added only when the same miss happens twice under the current model.**

## Principles

1. **Few features, adopted deliberately.** Drop whatever costs more than it saves.
2. **Enforce each rule in the cheapest reliable place:**
   tool config (ruff, pyright) > permissions > path-scoped rule > `CLAUDE.md` > `docs/`.
   Facts go in `CLAUDE.md`, procedures in skills, and anything that must always or never happen
   in hooks or permissions.
3. **Don't restate model defaults.** No "verify your work", no CAPS emphasis.
4. **Separate by audience:** my habits at user level, neutral tooling in the plugin, facts in the repo.
5. **One feature per session, with state in files.** The conversation is disposable.
6. **Measure before asserting.**

## Layers

| Layer | Holds | Source (versioned) | Reaches |
|---|---|---|---|
| **User** | 4 personal lines · `rules/python.md` · settings (permissions, model) | `tamsu/user/`, symlinked into `~/.claude/` | Every repo and subagent on this Mac (Explore/Plan skip CLAUDE.md) |
| **Plugin** `oskiv` | `/oskiv:init` + templates | `tamsu/plugins/oskiv/` | Repos where it's enabled |
| **Repo** | Its facts, commands, build list, docs, checks | The repo | That repo |

**Why there are two places.** A plugin can't set permissions or ship always-loaded instructions:
a plugin `CLAUDE.md` is ignored, and plugin settings accept only `agent` and
`subagentStatusLine`. So the user layer stays real files in `~/.claude`. Keeping their source in
tamsu gives one versioned repo for the whole harness, which also works on a new Mac. tamsu is
public, so `user/` never holds secrets or personal data.

## tamsu repo

```
tamsu/
├── README.md                  what this is · install on a new Mac · harness-review checklist
├── CLAUDE.md                  how to work on this repo (release steps, tests)
├── VERSIONS.md                per release: what changed, what was verified, known gaps
├── .claude-plugin/marketplace.json     name: tamsu → plugins: [oskiv]
├── plugins/oskiv/
│   ├── .claude-plugin/plugin.json      1.0.0
│   ├── commands/init.md                /oskiv:init: scaffold or top up a repo; never overwrites
│   ├── skills/loop/SKILL.md            /oskiv:loop: the orchestrator's outer loop
│   ├── bin/oskiv-pane                  iTerm2 pane control (on PATH while the plugin is enabled)
│   └── templates/                      (see "What init writes")
├── user/                      source of ~/.claude/{CLAUDE.md, rules/, settings.json}
│   ├── CLAUDE.md
│   ├── rules/python.md
│   └── settings.json
├── scripts/link-user.sh       symlink user/* into ~/.claude (shows what it replaces, asks first)
├── docs/architecture/baseline.md       this file
└── tests/                     manifest versions match; templates are valid JSON; init paths exist
```

Removed: `plugins/workflow-shell/`, `repackage.sh`, `check-drift.sh`, `Makefile` and the 0.4.x
audit docs (all in git history). `scratchpad-priv` stops being the canonical source.

## User layer (1.0)

**`user/CLAUDE.md`.** Only misses that happened under Opus 5.x:
- When I ask why, check or review, give the diagnosis and the proposed change; edit when I say so.
- Answer short and in plain words first; define any new term; go deeper when I ask.
- I often dictate: read for intent, and ask when the meaning matters and is unclear.
- Visuals are design work: load the diagram/dataviz skills first and make them look professional.

**`user/rules/python.md`** (`paths: **/*.py`): use uv for everything; never global pip.

**`user/settings.json`:** today's file, plus these permission rules:

| Effect | Rules |
|---|---|
| deny | `Read(**/.env*)` except `.env.example` · `Read(**/*.pem)` · `Read(**/*.key)` · `Bash(git push --force*)` · `Bash(git push -f*)` · `Bash(* --no-verify*)` |
| allow | `Bash(oskiv-pane *)` (the loop's iTerm2 control, on PATH from oskiv's `bin/`) |

There are no `ask` rules (2026-10-21): the loop must never wait on a prompt, and auto mode still
prompts for ask rules. So any session can push `main` or merge a PR without asking. Force push
stays denied, so a bad push is undone by a revert.

It also removes:
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`;
- the stale `~/.claude/output-styles/workflow-orchestrator.md`.

`teammateMode: "in-process"` stays (2026-10-21): teammates run inside the session, not in tmux.

**Git policy (stated in the init's CLAUDE.md skeleton):**
- The agent works on `feat/<slug>`, or in a worktree for background work.
- It commits there after each verified feature.
- Single session: it pushes the branch and opens a PR; I merge. With no remote, I merge locally.
- With the loop: the orchestrator merges into `main` locally, and pushes it, after the merge
  gate (see "Outer loop").

## What `/oskiv:init` writes into a repo

```
<repo>/
├── CLAUDE.md                 Overview · Git policy · Commands (run, test, check) · Build list ·
│                             Where files go · Known limitations     (fills from the repo; asks, never invents)
├── .claude/
│   ├── settings.json         tracked: enabledPlugins, plansDirectory, project hooks
│   ├── rules/placement.md    where non-code files go
│   ├── plans/
│   └── build/
│       ├── feature_list.json [{id, category, description, steps[], passes}]; only `passes` changes
│       └── progress.md       newest-first session entries (keep 10) · Owner decisions · Open risks
├── docs/                     README.md · product/ · architecture/ · decisions/ · research/
├── .scratch/                 gitignored: logs/ runs/ tmp/
└── pyproject.toml            Python repos: ruff + pyright config added if missing; the check
                              command becomes `ruff check && pyright && <tests>`
```

Existing docs are moved into this layout with my OK, not duplicated. Re-running init only fills in
what's missing. The repo's `CLAUDE.md` stays under 12 KB.

**Session loop** (in the skeleton, about 6 lines):
- **Start:** read `progress.md` and `git log`, take the first failing feature, and re-check the one it
  depends on.
- **During:** one feature only. Decide and record: unsettled choices go under Judgement calls,
  and the session stops only for the project's stop items or anything risky.
- **End:** run the check command. Flip `passes` only if every step was seen to pass. Then write the
  progress entry, commit on the branch, and push/PR.
- **New requirements** go to me first: the spec page changes, then I add a feature.

## Outer loop (`/oskiv:loop`, 2026-10-21)

One orchestrator session lands a batch of features on `main`. It is the only session that asks me.
The design and its rulings are in `.claude/plans/2026-10-21-outer-loop.md`.

- **Lanes:** per feature, an iTerm2 tab with two panes:
  - an implementer, working in its own worktree and branch;
  - a verifier, which runs the app and reports to the orchestrator only.

  One lane at a time until a dry run passes, then two.
- **Flow:** brief, build, verify, triage (fix now · hold · non-blocker), merge gate, next feature.
  - After 2 fix rounds without a pass, the orchestrator asks me.
  - The gate is the check command plus every step passing.
  - Only the orchestrator sets `passes`, in the merge commit.
  - Steps that need my clicks are batched into one ask at the end.
- **Pane control:** `oskiv-pane`, from oskiv's `bin/`, uses iTerm2's own AppleScript only.
  Messages go by SendMessage.
- **Context:** before each brief or fix round, the orchestrator reads the worker's status line.
  - At 250K tokens it asks for a handoff note and relaunches the worker.
  - 300K is the hard cutoff.
  - Auto-compact is off, so a full worker would stop.
- **Stop list:**
  - the kickoff block (services, `.env` keys, macOS permissions, steps that need me present);
  - a human dependency nobody foresaw;
  - a spec or decision change;
  - anything destructive, costly or outbound;
  - stuck;
  - batch done.

## Deferred (add when a miss repeats twice)

Format hook (`ruff format` on edit) · Stop-hook check gate · SessionStart bearings · drift check +
`/maint` · `/tmp` guard · feature-list edit guard · starter agents + agent memory · spec/verify
skills · TypeScript rule + tsconfig template (when a TS repo exists).

## Direction (recorded, not built)

- **Autonomous building:** now in the design, as the outer loop above.
- **Knowledge from what I watch:** YouTube, Instagram and X, retrievable by agents. This needs its
  own design.

## Rollout

1. **tamsu**
   - Rename the folder and the GitHub repo, and switch the owner email to noreply.
   - Strip 0.4.1, build oskiv 1.0.0, tests, `VERSIONS.md`.
   - Commit, push, make the repo public.
   - Re-register the marketplace and enable `oskiv@tamsu` at user scope.
2. **User layer:** write `user/*` → `link-user.sh` → settings cleanup → check with `/memory` and
   `/permissions`.
3. **macjev**
   - Run init. Move `docs/PRD.md` → `docs/product/` and `decisions.md` → `docs/decisions/`.
   - Move the module architecture from `CLAUDE.md` to `docs/architecture/`.
   - Record **D19: voice-first, which supersedes the rest of M1**.
   - Seed `progress.md`. Delete `AGENTS.md` and `.codex/`. Add ruff + pyright config.
   - The voice feature list comes from a separate product session.
4. **Other repos, later:** seriesA/* and scratchpad-priv. Until each is migrated it loses its
   0.4.x `workflow-shell` plugin, because that marketplace name goes away.

## Harness review (about every 7 days, my reminder)

1. Read the official sources fresh.
2. Compare them with the user, plugin and repo config.
3. Make three lists: what changed; what is now a default (cut it); misses that happened twice
   (add a line).
4. Present one block of rulings, each with a recommendation.
