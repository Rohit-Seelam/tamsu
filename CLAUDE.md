# tamsu

My Claude Code harness: the `oskiv` plugin (`plugins/oskiv/`) and the source of my user-level
config (`user/`, symlinked into `~/.claude` by `scripts/link-user.sh`). The design is in
`docs/architecture/baseline.md`; read it before changing what oskiv or `user/` contains.

## Build list (how work runs)
- State lives in `.claude/build/`: `feature_list.json` (what to build and how we know) and
  `progress.md` (what each session did).
- **Start:** read `progress.md` and `git log --oneline -20`. Take the first feature with
  `passes: false` unless I name one.
- **One feature per session.** Ask all rulings together, each with a recommendation.
- **End:** run the tests. Set `passes: true` only if every step ran and its result was seen. Add a
  dated entry at the top of `progress.md`, then commit on a branch and open a PR.
- Never delete, reword or reorder features or their steps. If a step is wrong, write it in
  `progress.md` and ask.

## Rules for changes
- Keep it lean: add something only when the same miss has happened twice, and cut whatever the
  model or harness now does by default.
- `user/` is public: no secrets, tokens, personal data or absolute home paths.
- Editing a file in `user/` changes the live `~/.claude` config immediately, because it is
  symlinked. The live config follows whichever branch is checked out here, so return to `main`
  after branch work.
- `skills/init/SKILL.md` is untested prose that Claude follows. After changing it, run `/oskiv:init`
  on a real repo.

## Feedback inbox
`feedback/` holds ideas about oskiv recorded from other projects by `/oskiv:feedback`. Commit new
entries with your work. When one is acted on, say so in `VERSIONS.md`.

## Release
1. Bump the version in **both** `plugins/oskiv/.claude-plugin/plugin.json` and
   `.claude-plugin/marketplace.json`. The bump is what delivers the release.
2. Add a `## <version>` entry to `VERSIONS.md`: what changed, what was verified, known gaps.
3. Run `python3 -m unittest discover tests` and `claude plugin validate plugins/oskiv`.
4. Commit and push. Then run `/plugin marketplace update tamsu` and `/reload-plugins`.

## Git
Work on a branch and open a PR; I merge into `main`.
