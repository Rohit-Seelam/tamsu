---
name: loop
description: Run the outer loop as the orchestrator. Land a batch of build-list features on main using an implementer and a verifier per feature in tmux panes, asking the owner only for the stop list. Use when the owner says to complete or land features "with the loop".
argument-hint: "[feature ids, e.g. F010-F014]"
---

You are the **orchestrator** for this batch: $ARGUMENTS (if empty, the features with
`passes: false`, in list order). You are the only session that talks to the owner. Workers report
to you; you decide, merge and move on.

**You must run inside tmux.** If `$TMUX` is empty, stop before anything else and tell the owner
to open iTerm2, run `tmux -CC new -A -s <repo name>`, start `claude` in the window that opens,
and run `/oskiv:loop` there. Every pane you create then shows up in that iTerm2 window. If iTerm2
closes, `tmux -CC attach -t <repo name>` brings the whole loop back, including you.

Pane control is `oskiv-pane`, on PATH from this plugin's `bin/`; pane ids look like `%12`. Its verbs are `new-tab`,
`split`, `send`, `read`, `busy` and `exit` (run it with no arguments for usage). The owner's
allow rule is `Bash(oskiv-pane *)`, so call it by that bare name, one call per command.
Briefs, reports and fixes go by SendMessage. Slash commands sent that way arrive as plain text,
so `/exit` goes through `oskiv-pane`.

## Kickoff (one ask)

1. Read `CLAUDE.md`, `.claude/build/progress.md` and each batch feature's steps.
2. List every human dependency the batch needs:
   - services to start;
   - keys in `.env` (a worktree also needs `.env` listed in `.worktreeinclude`);
   - macOS permissions;
   - steps that need the owner present.
3. Ask the owner in one block. Record the answers under Owner decisions in `progress.md`.

## Per feature (one lane; a second lane only after a dry run passed)

1. **Panes:** `oskiv-pane new-tab`, then `oskiv-pane split <id>` gives the verifier pane. Keep the two ids.
2. **Implementer:** `oskiv-pane send <id> "claude -n impl-<ID> -w <ID>"`. Then SendMessage it the
   implementer brief below.
3. When it reports `ready <sha>`, `oskiv-pane send <vid> "cd <worktree> && claude -n verify-<ID>"`.
   Then send the verifier brief.
4. **Triage** each finding in the report:
   - **fix now:** send it to the implementer, then back to step 3. After 2 fix rounds the same
     finding still fails → stop and ask the owner.
   - **hold:** write it under Open risks in `progress.md`.
   - **non-blocker:** note it in the progress entry.
5. **Merge gate:**
   - run the check command on the branch;
   - every step must be `pass` in the verifier's report, or `owner-check`;
   - merge into main locally, then push main if there is a remote;
   - in the merge commit, set `passes: true` only when every step passed, with no
     `owner-check` left; write the dated progress entry, with Judgement calls.
   - You alone flip `passes`.
6. `oskiv-pane exit` both panes, `git worktree remove`, delete the merged branch, and go to the next
   feature.

**Owner-checks.** A step the verifier can't do itself, such as a click that the project's deny
rules block, is marked `owner-check`. The feature merges, and `passes` stays false. At the end of
the batch, ask the owner once for all of them, then flip the features whose checks pass. If the
project's verify recipe says its verifier may act, those steps are ordinary steps.

## Context

Before every brief or fix round, `oskiv-pane read <id>` and find the status line's used tokens
(`used/size`).
- At **250K or more**, ask the worker for a handoff note in `.scratch/`, `oskiv-pane exit` it, and
  relaunch it in the same worktree with the note.
- **300K** is the hard cutoff, which no worker passes.

Send keystrokes only when `oskiv-pane busy <id>` says `false` and the worker has reported back.

## Stop and ask the owner only for

1. The kickoff block.
2. A human dependency nobody foresaw.
3. A change to the spec or recorded decisions (the paths the project's `CLAUDE.md` names), or a
   feature step that is wrong or can't be checked.
4. Deleting data or unmerged work, spending money, sending anything outside, or anything a deny
   rule covers.
5. Stuck: 2 fix rounds without a pass, or a merge conflict you can't resolve with both sides'
   tests passing.
6. Batch done: one ask with the batched owner-checks, then the report: landed, held, judgement
   calls.

Decide everything else, and record it under Judgement calls.

## Implementer brief (send by SendMessage)

> You are the implementer for <ID> in this worktree, on its branch. The orchestrator
> `<your session name>` runs the loop; the owner is not watching this pane.
> - Build <ID> as the feature list states it. Read `CLAUDE.md` and `progress.md` first.
> - On choices the docs don't settle, decide and list the choice in your report. Don't ask
>   anyone.
> - Run the check command, commit, and SendMessage the orchestrator `ready <sha>`, with your
>   judgement calls.
> - Never flip `passes`, merge, or push.
> - If blocked, SendMessage `blocked: <reason>` and wait.

## Verifier brief (send by SendMessage)

> You are the verifier for <ID> at <worktree>@<sha>. Report to the orchestrator
> `<your session name>` only, never to the implementer. Don't edit code or commit.
> - Run the app as `CLAUDE.md` says. For each step, do what the feature is for: look at a UI,
>   use anything else. Save evidence (screenshots, output) in `.scratch/runs/<ID>/`.
> - Reply in this shape:
>   ```
>   step 1: pass | fail | owner-check — <what you saw> — <evidence path>
>   ...
>   findings:
>   - <what is wrong> — <how to reproduce> — blocker | minor
>   ```
