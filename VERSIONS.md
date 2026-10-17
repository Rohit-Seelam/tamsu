# Versions

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
