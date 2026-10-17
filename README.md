# tamsu

My Claude Code harness in one repo:

- **`plugins/oskiv`**: a plugin that sets up any repo with a lean long-running-agent baseline: a
  feature list, a progress log, a docs layout, a `CLAUDE.md` skeleton and Python checks
  (`/oskiv:init`).
- **`user/`**: the source of my user-level config (`~/.claude/CLAUDE.md`, `rules/`,
  `settings.json`, status line). `scripts/link-user.sh` symlinks it into `~/.claude`.

The design and the reasons behind it are in [`docs/architecture/baseline.md`](docs/architecture/baseline.md).
What changed in each release is in [`VERSIONS.md`](VERSIONS.md).

## On a new Mac

```bash
git clone https://github.com/Rohit-Seelam/tamsu.git ~/Projects/tamsu
sh ~/Projects/tamsu/scripts/link-user.sh      # shows a diff and asks before replacing any file
```

Then, in Claude Code:

```text
/plugin marketplace add Rohit-Seelam/tamsu
/plugin install oskiv@tamsu
```

`user/settings.json` registers the marketplace and enables `oskiv@tamsu` for every project, so after
linking, the marketplace add may already be done.

## In a repo

```text
/oskiv:init [project name]
```

Safe to re-run: it fills in what's missing and never overwrites.

## Harness review (about every 7 days)

1. Read the official sources fresh: Claude Code docs (best practices, memory, hooks, sub-agents,
   settings, plugins), the prompting guide for the current model, and Anthropic's engineering blog.
2. Compare them with `user/`, the oskiv templates, and the CLAUDE.md files of the repos I'm working in.
3. Make three lists:
   - what the guidance changed;
   - which lines are now a model or harness default (cut them);
   - which misses happened twice since the last review (add one line each).
4. Present one block of rulings, each with a recommendation. Nothing changes without my go.
5. Run `scripts/link-user.sh --check` to confirm the user-level links are still intact.
