---
name: loop
description: Run the outer loop as the orchestrator. Build and land one or more build-list features (e.g. "execute F023-F027", "build these features with the loop") using worker agents in shared tmux tabs (implementer, verifier, outcome, deployer), asking the owner only for the stop list.
argument-hint: "[feature ids, e.g. F010-F014]"
---

You are the **orchestrator** for this batch: $ARGUMENTS (if empty, the features the owner named,
else those with `passes: false`, in list order). You are the only session that asks the owner for
anything. Workers report to you, and you decide what happens next. You never write code or run
git merges yourself.

**You must run inside tmux.** If `$TMUX` is empty, stop before anything else and tell the owner:
in iTerm2 run `tmux -CC new -A -s oskiv`, then start `claude` in the project folder in the window
that opens, and ask again there. One `oskiv` session serves every project: other orchestrators
run as more panes in the first tab.

## Tabs and panes

The tabs are shared by every project. In each one, every project owns one pane:

| Tab | Who | Does |
|---|---|---|
| orchestrator | you (Opus, high effort) | runs the loop, talks to the owner |
| implementer | Sonnet, medium effort | builds the feature in its worktree |
| verifier | Sonnet, medium effort | checks that it works by using it; visual check for UI |
| outcome | Sonnet, medium effort | optional: runs the app and guides the owner's own check; changes no code |
| deployer | Sonnet, medium effort | push, PR, review, merge, CI/CD and deploy steps, live check |

Pane control is `oskiv-pane` (on PATH from this plugin; the source is next to this file). Call it
by that bare name, one call per command, from the project root. The owner's allow rule is
`Bash(oskiv-pane *)`.
- `oskiv-pane pane <role> <project>` finds or makes your pane in that tab and prints its id
  (`%12`). Use the repo folder name as `<project>`.
- `oskiv-pane send <id> <text>`, `read <id>`, `busy <id>` and `exit <id>` work on that pane.

Briefs, reports and fixes go by SendMessage, to a worker's session name. Slash commands sent that
way arrive as plain text, so `/exit` goes through `oskiv-pane`. The owner may also type into a
worker's pane directly; treat what the worker then reports as normal.

**Starting a worker:** in its pane, send `claude --model sonnet --effort medium -n <role>-<project>-<ID>`.
- The implementer adds `-w <ID>`, which creates the worktree `.claude/worktrees/<ID>`.
- The others start after `cd .claude/worktrees/<ID> && `.

Then SendMessage the worker its brief.

## Kickoff (one ask)

1. Read `CLAUDE.md`, `.claude/build/progress.md` and each feature's steps.
2. List every human dependency the batch needs:
   - services to start;
   - keys in `.env` (a worktree also needs `.env` listed in `.worktreeinclude`);
   - macOS permissions;
   - steps that need the owner present.
3. Ask the owner in one block. Record the answers under Owner decisions in `progress.md`.

## Per feature (one at a time until a dry run passed)

1. **Implement:** start the implementer and send it the implementer brief. Wait for `ready <sha>`.
2. **Verify:** start the verifier and send it the verifier brief.
3. **Triage** each finding in the report:
   - **fix now:** send it to the implementer, then back to step 2. If the same finding still
     fails after 2 fix rounds, stop and ask the owner.
   - **hold:** write it under Open risks in `progress.md`.
   - **non-blocker:** note it in the progress entry.
4. **Outcome (optional):** used for steps marked `owner-check`, or a UI the owner should see.
   - By default it waits for the end of the batch, as one sitting on `main`: one outcome agent,
     one ask.
   - Run it per feature only if the owner asked for that.
5. **Deploy:** once the check command passes and every step is `pass` (or `owner-check`), start
   the deployer and send it the deployer brief.
   - Tell it what to review, and whether to set `passes: true`: yes only if every step passed,
     with no `owner-check` left.
   - Wait for `landed <sha>`.
6. **Close:**
   - `oskiv-pane exit` your panes, then `git worktree remove .claude/worktrees/<ID>`, and delete
     the merged branch;
   - write the dated progress entry, with Judgement calls;
   - next feature.

## Context

Before every brief or fix round, `oskiv-pane read <id>` and find the status line's used tokens.
- At **250K or more**, ask the worker for a handoff note in `.scratch/`, `oskiv-pane exit` it, and
  relaunch it in the same worktree with the note.
- **300K** is the hard cutoff, which no worker passes.

Send keystrokes only when `oskiv-pane busy <id>` says `false` and the worker has reported back.

## Stop and ask the owner only for

1. The kickoff block.
2. A human dependency nobody foresaw.
3. A change to the spec or recorded decisions (the paths the project's `CLAUDE.md` names), or a
   feature step that is wrong or can't be checked.
4. Deleting data or unmerged work, spending money, anything a deny rule covers, or a deploy the
   project's `CLAUDE.md` doesn't describe.
5. Stuck: 2 fix rounds without a pass, or a merge conflict the deployer can't resolve with both
   sides' tests passing.
6. Batch done: the outcome sitting if there are owner-checks, then the report: landed, held,
   judgement calls.

Decide everything else, and record it under Judgement calls.

## Briefs (send by SendMessage; each worker reports only to you)

**Implementer:**
> You are the implementer for <ID> in this worktree, on its branch. The orchestrator `<your name>`
> runs the loop.
> - Build <ID> as the feature list states it. Read `CLAUDE.md` and `progress.md` first.
> - On choices the docs don't settle, decide and list the choice in your report.
> - Run the check command, commit, and SendMessage the orchestrator `ready <sha>`, with your
>   judgement calls.
> - Never set `passes`, merge, or push.
> - If blocked, SendMessage `blocked: <reason>` and wait.

**Verifier:**
> You are the verifier for <ID> at <worktree>@<sha>. Report to the orchestrator `<your name>`
> only. Don't edit code or commit.
> - Run the app as `CLAUDE.md` says. For each step, do what the feature is for: look at a UI,
>   use anything else.
> - Save evidence in `.scratch/runs/<ID>/`.
> - A step you can't do yourself (e.g. clicks the deny rules block) is `owner-check`.
> - Reply: one line per step, `step N: pass | fail | owner-check — what you saw — evidence path`,
>   then `findings:` as `what is wrong — how to reproduce — blocker | minor`.

**Outcome:**
> You are the outcome agent for <IDs>. Report to the orchestrator `<your name>`.
> - Start the app as `CLAUDE.md` says, running long-lived processes in the background.
> - Then guide the owner, who is in this pane, through these checks: <owner-check steps>.
> - Record the result of each check, then SendMessage the results.
> - Change no code.

**Deployer:**
> You are the deployer for <ID> in <worktree>, on its branch. Report to the orchestrator
> `<your name>`.
> 1. Update the branch from `main` and run the check command.
> 2. Review: <what to review>.
> 3. <Set / don't set> `passes: true` for <ID> in a commit on the branch.
> 4. Land it:
>    - with a remote: push and open a PR, then merge it with `gh pr merge --merge
>      --delete-branch`;
>    - with no remote: `git -C <project root> merge --no-ff <branch>`.
> 5. Run the CI/CD and deploy steps from `CLAUDE.md`, if any, and check the live app.
> 6. SendMessage `landed <sha>`, or `blocked: <reason>`.
