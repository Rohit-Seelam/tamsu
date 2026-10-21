# Versions

## 1.0.2 (2026-10-21)

The outer loop: one orchestrator lands a batch of features on `main` with an implementer and a
verifier per feature. Design and rulings: `.claude/plans/2026-10-21-outer-loop.md`.

- **Added:**
  - `/oskiv:loop` (`skills/loop/SKILL.md`): kickoff ask, per-feature flow, triage, merge gate,
    the 250K/300K context rule, the stop list, and the worker briefs.
  - `bin/oskiv-pane`: iTerm2 pane control through iTerm2's own AppleScript. The verbs are
    new-tab, split, send, read, busy and exit.
- **Changed:**
  - Templates: "decide and record" replaces "ask all rulings together".
  - `passes` is set only in the commit that lands on `main`.
  - The orchestrator may merge and push after the gate.
  - There is a slot for how to check a feature by hand, and progress entries gain Judgement
    calls.
- **User config:**
  - `user/settings.json` drops all `ask` rules and allows `Bash(oskiv-pane *)`.
  - `baseline.md` gains the Outer loop section, and `teammateMode` stays.
- **Verified:**
  - Tests pass, and `claude plugin validate` is clean.
  - A headless `--plugin-dir` session found `oskiv-pane` on PATH and the `oskiv:loop` skill.
  - `oskiv-pane` opened a tab, split it, typed into both panes, read the text back, reported
    `busy`, and closed them. There was no macOS permission prompt.
- **Known gaps:**
  - The loop itself hasn't run end to end. Its first use is the dry run.
  - Sending `/exit` into a live Claude pane is untested; only shell panes were driven.
  - `init.md` doesn't add `.worktreeinclude`.
  - The 50K margin under the 300K cutoff is a guess.

## 1.0.1 (2026-10-17)

Lessons from the first real `/oskiv:init` run (macjev).

- **Changed:** `init.md` now:
  - checks that `.claude/build/` isn't caught by a `build/` gitignore line;
  - matches the Python check config to the code's existing style before measuring;
  - records the pre-existing findings in `progress.md` instead of fixing them.

  `CLAUDE.md` notes that the live `~/.claude` config follows the checked-out branch.
- **Verified:** tests pass, `claude plugin validate` is clean, and the macjev migration followed
  these steps.
- **Known gaps:** as in 1.0.0.

## 1.0.0 (2026-10-17)

First release of `oskiv`. It replaces `workflow-shell` 0.4.1 (still in git history, before this
commit).

- **Changed:**
  - `/oskiv:init` with templates: `CLAUDE.md` skeleton, `.claude/build/` (feature list +
    progress), `docs/` layout, placement rule, tracked settings, gitignore and pyproject
    fragments.
  - The source of the user-level config now lives in `user/`, linked by `scripts/link-user.sh`.
  - Removed everything from 0.4.1: agents, phases, the SDK memory pipeline, hooks, the output
    style, `repackage.sh`.
- **Verified:** `tests/` pass and `claude plugin validate` is clean. Init gets its first real run
  on macjev.
- **Known gaps:**
  - No hooks yet (format, check gate, drift).
  - The `.env` deny rules cover Read only, not shell commands such as `cat .env`.
  - Pushing to `main` with a bare `git push` while on main isn't caught by the ask rules.
