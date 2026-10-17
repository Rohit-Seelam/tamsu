# {{project}}

{{One or two lines: what this repo is and who uses it, so a newcomer can tell whether a task belongs here.}}

## Build list (how work runs)
- State lives in `.claude/build/`: `feature_list.json` (what to build and how we know) and
  `progress.md` (what each session did).
- **Start:** read `progress.md` and `git log --oneline -20`. Take the first feature with
  `passes: false` unless I name one, and first re-check the passing feature it depends on.
- **One feature per session.** Ask all rulings together, each with a recommendation.
- **End:** run the check command. Set `passes: true` only if every step ran and its result was
  seen. Add a dated entry at the top of `progress.md`, then commit.
- Never delete, reword or reorder features or their steps. If a step is wrong, write it in
  `progress.md` and ask. New requirements go to me first: the `docs/` page changes, then I add a
  feature.

## Git
- Work on `feat/<slug>` (or a worktree for background work), never on `main`. Commit after each
  verified feature.
- {{With a remote: push the branch and open a PR with `gh pr create`; I merge. / No remote yet: I merge locally.}}

## Commands
```bash
{{run}}
{{check: lint + types + tests, the command a session runs before saying done}}
```

## Where files go
`docs/` holds the design (start at `docs/README.md`). `.claude/rules/placement.md` says where
everything else goes. Scratch output goes in `.scratch/` (gitignored), never `/tmp`.

## Known limitations
{{What the agent can't reach or do here, and gotchas that cost time. Delete this section if there are none.}}
