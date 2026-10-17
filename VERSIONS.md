# Versions

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
