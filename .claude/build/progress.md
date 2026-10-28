# Progress

Newest first. Keep the latest 10 entries; git history holds the rest.

## 2026-10-23: oskiv 1.0.4, loop v2 + feedback + init as a skill (owner-directed)
- **State:**
  - Loop v2: a shared `oskiv` tmux session, with role tabs (implementer, verifier, outcome,
    deployer) and one pane per project. Workers run Sonnet at medium effort; the orchestrator is
    Opus at high effort. The deployer lands and sets `passes`.
  - `/oskiv:feedback` writes to `feedback/`, and `init` is now a skill.
  - One method line was added to user `CLAUDE.md`.
  - Tests and validation pass. The detached tmux test with two fake projects passed. A headless
    `/oskiv:feedback` run wrote the right file; it was deleted.
- **Judgement calls:**
  - The pane source lives in `skills/loop/` as the owner asked. `bin/oskiv-pane` stays as a
    2-line wrapper, because a rule on the skill's path would need the versioned cache path or a
    leading wildcard that matches any program.
  - The outcome agent runs app processes in the background itself; it opens no extra panes.
  - By default the outcome sitting stays batched at the end, per the 2026-10-21 ruling.
  - The owner's uncommitted `user/settings.json` edit (Opus effort `high`) was left
    uncommitted: it is theirs.
- **Next:** the first real `/oskiv:loop` run under `tmux -CC new -A -s oskiv`. PR #4
  (`chore/oskiv-init`) still waits for a ruling. F001 is still open.

## 2026-10-21: oskiv 1.0.3, tmux panes (owner-directed)
- **State:**
  - `oskiv-pane` drives tmux.
  - The orchestrator runs inside `tmux -CC new -A -s <repo>`.
  - Tested in a detached tmux session, including a real Claude pane and `/exit`.
  - Tests pass, and validate is clean.
- **Judgement calls:**
  - Pane ids are restricted to `%N`, so a call can't target another session.
  - `send` waits 0.3 s between the text and Enter.
  - `read` trims the trailing blank rows.
- **Next:** the first `/oskiv:loop` dry run under `-CC` in iTerm2. F001 is still open.

## 2026-10-21: oskiv 1.0.2, the outer loop (owner-directed, not from the build list)
- **State:**
  - `/oskiv:loop` and `bin/oskiv-pane` added; the templates updated; `user/settings.json` drops
    the ask rules and allows `Bash(oskiv-pane *)`; `baseline.md` gains the Outer loop section.
  - The design was asked for by the macjev orchestrator session, with the owner's rulings
    relayed. The owner approved the settings change directly in this session.
  - Tests pass, and `claude plugin validate` is clean.
  - `oskiv-pane` drove a real iTerm2 tab and pane.
- **Judgement calls:**
  - The pane rule went into `user/settings.json`, not `~/.claude/settings.local.json`: the docs
    list no user-level local file.
  - The script ships in the plugin's `bin/`, so the rule needs no home path or version.
  - Auto mode first blocked staging `user/settings.json` as self-modification. The owner then
    told me to commit it.
  - The commit includes the owner's earlier edits: `model: opus`, Opus 5.5 effort `medium` and
    `teammateMode: in-process`.
  - Versioned 1.0.2 at the owner's request, not 1.1.0.
- **Next:** a dry run of `/oskiv:loop` on one small macjev feature. F001 is still open.

## 2026-10-17: `/oskiv:init` run as a command on tamsu (top-up)
- **State:**
  - First time `/oskiv:init` ran as a slash command rather than followed by hand.
  - Added: `docs/README.md`, `docs/{product,decisions,research}/`, and the `Commands` and
    `Where files go` sections in `CLAUDE.md`.
  - Left alone: settings, placement rule, build files, `.gitignore` (fragment already present;
    `.claude/build/` not ignored), the Git section (already the remote variant), README.md and
    VERSIONS.md at the root. No `pyproject.toml`: the only Python is `tests/`, run with stdlib
    unittest.
  - Check: 8 tests OK, `claude plugin validate` passed, `link-user.sh --check` all ok.
- **Next:** F001, `.env` protection for shell reads.

## 2026-10-17: tamsu set up; oskiv 1.0.0 → 1.0.1 shipped
- **State:**
  - tamsu replaces `workflow-shell-marketplace` and is now public.
  - oskiv 1.0.1 (`/oskiv:init` + templates) is installed at user scope.
  - `user/` is linked into `~/.claude`. Checked with a headless probe: the user CLAUDE.md lines
    load, and the Read tool is denied on `.env`.
  - macjev was the first repo initialised. Its lessons went into 1.0.1.
  - The design is in `docs/architecture/baseline.md`.
- **Next:** F001, `.env` protection for shell reads. The current deny rules cover only the Read
  tool, so `cat .env` still works.

---

## Owner decisions
- 2026-10-17: names. The repo/marketplace is `tamsu`; the plugin is `oskiv` (`oskiv@tamsu`).
  Versions start at 1.0.0 and are bumped once per release.
- 2026-10-17: lean baseline. Add something only after the same miss happens twice; cut whatever
  becomes a model default.
- 2026-10-17: plugin development happens in this repo's sessions, not in the repos that use it.
- 2026-10-17: git. Work on branches and open PRs; I review and merge. The older commits that
  contain my Gmail address are fine to keep public.

- 2026-10-21: the outer loop. It is fully autonomous: there are no user-level ask rules, and the
  orchestrator merges and pushes `main` after the gate. Other rulings:
  - one lane until a dry run passes;
  - after 2 fix rounds, the orchestrator asks;
  - only the orchestrator sets `passes`;
  - click checks are batched for me;
  - context: relaunch at 250K, hard cutoff at 300K;
  - `teammateMode` stays in-process.

  tamsu's own PRs are still mine to merge.

## Open risks
- With no ask rules, any session in any repo can push `main` or merge a PR without asking.
- scratchpad-priv and the four seriesA repos still enable `workflow-shell@workflow-shell-marketplace`;
  each needs migrating to oskiv.
- `/oskiv:init` has run as a command only on tamsu, which was already set up; a run on a fresh
  repo is still untested.
- A bare `git push` while on `main` isn't caught by the ask rules.
