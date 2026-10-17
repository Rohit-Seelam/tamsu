# Progress

Newest first. Keep the latest 10 entries; git history holds the rest.

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

## Open risks
- scratchpad-priv and the four seriesA repos still enable `workflow-shell@workflow-shell-marketplace`;
  each needs migrating to oskiv.
- `/oskiv:init` has been followed by hand (on macjev) but not yet invoked as a command.
- A bare `git push` while on `main` isn't caught by the ask rules.
