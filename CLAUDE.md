# tamsu

My Claude Code harness: the `oskiv` plugin (`plugins/oskiv/`) and the source of my user-level
config (`user/`, symlinked into `~/.claude` by `scripts/link-user.sh`). The design is in
`docs/architecture/baseline.md`; read it before changing what oskiv or `user/` contains.

## Rules for changes
- Keep it lean: add something only when the same miss has happened twice, and cut whatever the
  model or harness now does by default.
- `user/` is public: no secrets, tokens, personal data or absolute home paths.
- Editing a file in `user/` changes the live `~/.claude` config immediately, because it is
  symlinked.
- `commands/init.md` is untested prose that Claude follows. After changing it, run `/oskiv:init`
  on a real repo.

## Release
1. Bump the version in **both** `plugins/oskiv/.claude-plugin/plugin.json` and
   `.claude-plugin/marketplace.json`. The bump is what delivers the release.
2. Add a `## <version>` entry to `VERSIONS.md`: what changed, what was verified, known gaps.
3. Run `python3 -m unittest discover tests` and `claude plugin validate plugins/oskiv`.
4. Commit and push. Then run `/plugin marketplace update tamsu` and `/reload-plugins`.

## Git
Work on a branch and open a PR; I merge into `main`.
