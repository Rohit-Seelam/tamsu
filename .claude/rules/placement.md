---
paths:
  - "docs/**"
  - "scripts/**"
  - ".scratch/**"
  - ".claude/build/**"
  - ".claude/plans/**"
---

# Where files go

Pick the home by what the file is, not where the session happens to be.

| What it is | Home |
|---|---|
| What the product must do | `docs/product/` (the PRD wins any disagreement) |
| How it's built | `docs/architecture/` |
| A significant choice or a reversal | `docs/decisions/YYYY-MM-DD-slug.md`; never rewritten, superseded by a new record |
| A dated finding, measurement or review | `docs/research/YYYY-MM-DD-slug.md`; immutable once filed |
| What to build next and how we know it's done | `.claude/build/` (I amend the feature list) |
| One route through the work starting now | `.claude/plans/`, one at a time, renamed `YYYY-MM-DD-slug.md` |
| A script worth running again | `scripts/` |
| Logs, run output, one-off probes, screenshots | `.scratch/{logs,runs,tmp}/` |

- `.scratch/` is gitignored and absent from fresh clones and worktrees, so nothing durable lives
  there. A conclusion drawn from it goes to `docs/research/` and cites the log.
- External docs are read live and cited by URL, never copied in.
- Output containing personal data or identifiers stays in `.scratch/runs/`.
