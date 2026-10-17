---
description: Set up or top up this repo with the oskiv baseline (build list, progress log, docs layout, CLAUDE.md, Python checks). Safe to re-run; never overwrites.
argument-hint: "[project name]"
---

Set up this repository with the oskiv baseline. Project name: $ARGUMENTS (if empty, use the repo
folder name).

Templates are in `${CLAUDE_PLUGIN_ROOT}/templates/`. If that path didn't resolve, use the newest
`~/.claude/plugins/cache/tamsu/oskiv/*/templates/`.

## What the repo should end up with

| Path | From template | If it already exists |
|---|---|---|
| `CLAUDE.md` | `CLAUDE.md` | Keep it. Add any missing baseline sections (Build list, Git, Commands, Where files go), and propose moving per-module detail into `docs/architecture/` |
| `.claude/settings.json` | `settings.json` | Merge keys; keep everything already there |
| `.claude/rules/placement.md` | `rules/placement.md` | Keep it |
| `.claude/build/{README.md, feature_list.json, progress.md}` | `build/` | Keep them |
| `.claude/plans/` | (an empty folder, kept by a .gitkeep file) | Keep it |
| `docs/README.md` + `docs/{product,architecture,decisions,research}/` | `docs/README.md` | Keep them; add only the missing folders (`.gitkeep` in empty ones) |
| `.gitignore` | append `gitignore.fragment` lines that are missing | |
| `pyproject.toml` (Python repos only) | merge `pyproject.fragment.toml` | Add missing tables only; never change values the repo already set |

## How to fill it in

- Fill every `{{placeholder}}` from what you can observe: the README, the manifests, the scripts,
  `git log`, the test layout. If something can't be observed, ask me rather than inventing it, and
  ask everything in one go.
- The **check command** in `CLAUDE.md` should be the repo's real lint + types + tests, e.g.
  `uv run ruff check . && uv run pyright && uv run pytest`. Run it once and report the result.
  Pre-existing failures are findings for me, not something to fix now.
- **Existing docs** (PRD, design, decisions, research, TODO/roadmap files): propose where each
  moves in the `docs/` layout and wait for my OK. Use `git mv`, so history follows the file.
  Replace fully; no copies are left behind.
- **Git section:** check `git remote -v` and keep the matching variant of the line.
- `feature_list.json` starts as `[]`. Features are mine to add. Offer to draft candidates from the
  product docs for me to review, but never write them in without my OK.
- Write the first `progress.md` entry: the date, what was set up, and what's next.
- After editing `.gitignore`, run `git check-ignore -v .claude/build/progress.md`. A common
  `build/` line ignores `.claude/build/` too; anchor it as `/build/`.
- **Python checks:** match the config to how the code is already written before judging it. That
  means line length (measure it), and per-file ignores for files that print by design (CLI,
  scripts, tests). Then run the checks and record the remaining counts by rule under Open risks
  in `progress.md`. Fixing them is a feature for me to add, not part of init.
- Keep `CLAUDE.md` under 12 KB. Every line should pass "would removing this cause a mistake?"

## Finish

Report what was created, merged, moved or left alone, and the result of the check command. Then
commit the setup on a branch `chore/oskiv-init`, following the repo's git policy.
