# Outer loop for orchestrated lanes (proposal)

**Status:** applied 2026-10-21 (oskiv 1.0.2); was a proposal earlier that day. Revised the same day with the owner's rulings, relayed by the
macjev orchestrator (§6). Nothing here is applied.
**Checked against:** Claude Code 2.1.306 (`claude --help`); official docs for hooks, statusline,
cross-session messaging, permissions and permission modes (read 2026-10-21); the iTerm2 scripting
dictionary (`iTerm.app/Contents/Resources/iTerm2.sdef`); macjev `CLAUDE.md` (with the uncommitted
owner edit), `.claude/settings.json` and `docs/research/2026-10-19-prd-to-features-and-outer-loop.md`.

**Terms:**
- **orchestrator:** the one session that runs the loop and the only one that talks to the owner.
- **lane:** one feature in flight: an implementer pane and a verifier pane.
- **implementer:** writes the feature in its own worktree and branch.
- **verifier:** checks that the feature works by using it (a UI is checked by looking at it); it
  never edits code.
- **brief:** the message the orchestrator sends a worker to start it on a feature.

## 1. Roles and flow

```
owner ──"land F010–F014"──▶ ORCHESTRATOR ──(one question block, up front)──▶ owner
                                │
          per feature           ▼
   ┌─ iTerm2 tab: [implementer pane | verifier pane]   (one tab holds up to 2 lanes = 4 panes)
   │
   │ 1 brief ──────────────▶ IMPLEMENTER   claude -n impl-F010 -w F010
   │                          builds on its branch, runs the check command, commits
   │ 2 "ready <sha>" ◀────────┘
   │ 3 brief ──────────────▶ VERIFIER      claude -n verify-F010, in the same worktree
   │                          runs the app, does each step, collects evidence
   │ 4 report ◀───────────────┘            (never to the implementer)
   │ 5 triage each finding:  fix now ─▶ implementer, then back to 2 (2 rounds, then ask the owner)
   │                         hold     ─▶ progress.md "Open risks"
   │                         non-blocker ─▶ the progress entry
   │ 6 merge gate: check command on the branch + verifier passed every step
   │      (click-based steps are batched for the owner, see below)
   │      → merge into main locally, flip `passes` in the merge commit, write the progress entry
   │      → with a remote, push main (no prompt: see §5.2)
   └ 7 /exit both panes, remove the worktree, next feature
```

- **Messages:** briefs, reports and fix requests go by SendMessage between named sessions. The
  docs say a slash command sent this way "arrives as plain text. Claude Code never executes it", so
  pane control (start `claude`, `/exit`, `/clear`) goes through iTerm2: its own `write text` and
  `split vertically`, not System Events keystrokes.
- **Same permission mode for all:** run every session in auto mode. Messages between sessions in
  prompting modes (default, auto, acceptEdits, dontAsk) are delivered; a session that bypasses
  permissions holds them for approval.
- **`passes` counts only on main:** workers never flip it. Only the orchestrator flips it, in the
  merge commit, after the verifier's report shows every step passing.
- **Click-based UI checks:**
  - Default: the verifier marks steps that need clicks as `owner-check`. The orchestrator merges
    the rest of the feature and leaves `passes` false.
  - At the end of the batch, it asks the owner once for all owner-checks, then flips the features
    whose checks passed.
  - A project can later let its verifier act instead. It lifts its deny rules for the verifier and
    says so in its CLAUDE.md verify recipe; the skill then treats those steps as ordinary steps.
- **One lane first.** Move to two once a dry run on a small feature has gone end to end.

## 2. Where each piece lives

| Place | What goes there |
|---|---|
| `user/CLAUDE.md` | **Nothing new.** Workers learn their role from the brief, and the orchestrator from the skill. A line that is always loaded would also reach sessions that are not in a loop. |
| `user/settings.json` | The ask-rule removal in §5.2, and the `Bash(oskiv-pane *)` allow rule (§5.1). |
| oskiv `skills/loop/SKILL.md` (new; `/oskiv:loop`) | The orchestrator's procedure: kickoff questions, the flow above, triage, merge gate, stop list, context rule. Brief templates for the implementer and the verifier, including the report format: one line per step (pass/fail, evidence path in `.scratch/`), then findings. |
| oskiv `bin/oskiv-pane` (new) | The only way the loop touches iTerm2, on PATH while the plugin is enabled. Fixed verbs: `new-tab`, `split`, `send <pane> <text>`, `read <pane>`, `busy <pane>`, `exit <pane>`. It only ever addresses iTerm2. |
| oskiv `templates/CLAUDE.md` | Replace "Ask all rulings together" with "decide and record" (macjev's wording) plus `{{project stop items}}`. In Git, the orchestrator may merge a branch that passed the gate; pushing `main` stays with the owner. Add a `{{how to run the app and check a feature by hand}}` slot for verifiers. |
| oskiv `templates/build/` | README: `passes` flips only in the commit that lands on main. `progress.md` entry gains **Judgement calls**. |
| Project | Its run and check commands, the verify recipe (for example, the cua-driver read tools in macjev), its own stop items (`docs/product/`, `docs/decisions/`, real-Mac runs), `.worktreeinclude` listing `.env`, and its deny rules (macjev's cua-driver denies stay). |

## 3. Context management

**Recommendation: no hooks. Start each feature in a fresh process; the orchestrator checks a
worker's context only before sending a fix round.**

- **New feature = new process.** The orchestrator types `/exit` into the pane and launches
  `claude -n impl-F011 -w F011`. This is cleaner than `/clear`, because `/clear` keeps the old
  working directory, and each feature needs its own worktree.
- **Within a feature: a fixed token cutoff (owner ruling).**
  - **When:** before every new brief or fix round, the orchestrator reads the worker's pane
    (`oskiv-pane read` → iTerm2 `contents`).
  - **What it reads:** the status line's used-token count, which is `used_percentage` ×
    `context_window_size`. tamsu's status line prints it as `used/size`, from `current_usage`.
  - **Hard cutoff, 300K tokens:** the worker must never go past it.
  - **Relaunch point, 250K tokens:** the orchestrator checks only between rounds, and one round
    can add tens of thousands of tokens. So at a check showing 250K or more, it acts before
    sending more work: it asks the worker for a handoff note in `.scratch/`, `/exit`s it and
    relaunches it in the same worktree. The 50K margin is a first guess; adjust it after the dry
    run by looking at how much one round actually adds.
- **Keystrokes only at a prompt:** send `/exit` or `/clear` only after the worker has reported
  back. Check first with iTerm2's `is processing` property.

**Why not the hooks:**
- No hook input carries context-window usage. Only the status line gets it
  (`context_window.used_percentage`, `context_window_size`, `exceeds_200k_tokens`).
- No hook can run `/clear` or `/compact`. A hook can only block a prompt or a stop.
- **The window is 1M.** Per the model-config docs (code.claude.com/docs/en/model-config, relayed
  by the orchestrator), `"model": "opus"` runs Opus 5.5 at 1M by default, and `opus[1m]` has no
  effect on Opus 4.7 and later. The uncommitted `"model": "opus"` stays.
- **What the orchestrator reads:** `context_window.used_percentage` × `context_window_size`, as
  tokens. `used_percentage` counts input tokens only, and the status line already prints the
  product.
- **Why the relaunch must fire early:** auto-compact would start at about 967K, but
  `autoCompactEnabled` is false, so a worker that fills its window stops. The 300K cutoff is far
  below that.
- The owner gets a sound when the orchestrator stops through `agentPushNotifEnabled`, which is
  already on. A stop-sound hook would add nothing.

## 4. Stop list (only the orchestrator stops; workers report "blocked: <reason>" to it)

1. **Kickoff, once per batch:** the orchestrator lists every human dependency the batch's
   features need and asks in one block:
   - services to start;
   - keys in `.env`;
   - macOS permissions;
   - steps that need the owner present.
2. **A human dependency nobody foresaw**, of the same kinds.
3. **A change to what was decided:** the product spec or recorded decisions (each project names
   these paths), or a feature step that is wrong or can't be checked.
4. **Hard to undo or leaves the machine:**
   - deleting data or branches that hold unmerged work;
   - spending money or sending anything outside;
   - anything a deny rule covers.

   Pushing `main` after a passed merge gate is not a stop (owner ruling).
5. **Stuck:** the same finding still fails after 2 fix rounds, or the merge has a conflict the
   orchestrator can't resolve while keeping both sides' tests passing.
6. **Batch done:** one ask that carries the batched owner-checks, then a report of what landed,
   what was held, and the judgement calls.

Every other choice is decided and recorded under Judgement calls.

## 5. Permissions the owner would grant

1. **iTerm2 control.**
   - Add `Bash(oskiv-pane *)` to `allow` in `user/settings.json`.
     - Applied 2026-10-21. The ruling had placed this rule in `~/.claude/settings.local.json`,
       but the settings docs list no user-level `settings.local.json`; that file exists only at
       project scope.
     - Shipping the script in the plugin's `bin/` puts it on PATH. The rule then needs no home
       path, so it can sit in public `user/`, and it survives version bumps (the plugin cache
       path contains the version).
   - The rule only fits a script with fixed verbs. The docs say a Bash rule "isn't a security
     boundary around the program", so `Bash(osascript *iTerm*)` would match any AppleScript that
     contains "iTerm".
   - macOS: no Accessibility is needed if only iTerm2's own AppleScript is used, not System
     Events. Whether iTerm2 scripting itself raises an Automation prompt is unverified: the dry
     run shows it.
2. **Merging and pushing without a prompt** (owner ruling: fully autonomous).
   - A local `git merge` into main hits no user rule.
   - Auto mode still prompts for ask rules, and an allow can't override an ask. So the loop only
     runs without prompts if the ask rules go.
   - Exact change to `user/settings.json`: delete the whole `"ask"` array, all three rules:

     ```diff
     -    "ask": [
     -      "Bash(git push origin main*)",
     -      "Bash(git push * main*)",
     -      "Bash(gh pr merge*)"
     -    ],
     ```

     The ruling named two rules. The third, `git push origin main*`, matches the same pushes, so
     it has to go too, or every push still prompts.
   - The `deny` list stays unchanged: `.env`, `.env.local`, `*.pem` and `*.key` reads, force push,
     and `--no-verify`.
   - **Risk that remains:**
     - The change is user-level, so every session in every repo can push `main` and merge PRs
       without asking, not only the loop.
     - On the loop's side, the only gate before the remote is the merge gate (check command plus
       verifier). A wrong verdict lands on the remote `main`. It can be fixed with a revert,
       because force push stays denied.
     - Bash rules match the command text, so even today they are not a hard boundary.
     - Optional server-side guard: GitHub branch protection on `main` that requires the CI check
       to pass. The owner sets it in GitHub; the loop never changes it.
3. **Verifier acting on a UI.**
   - macjev denies every cua-driver action, so a verifier can only read windows.
   - Default (owner ruling): click-based steps are batched for the owner at the end of the batch
     (§1).
   - Later, a project can lift its deny rules for the verifier, in its own settings.
4. **Nothing else is needed:**
   - cross-session messaging is on by default (v2.1.224+);
   - force push and `--no-verify` stay denied;
   - no CLAUDE.md or settings edits by the loop.

## 6. Owner rulings (2026-10-21, relayed by the macjev orchestrator)

1. **Fully autonomous:** remove the user-level ask rules and keep the denies (§5.2).
2. **One lane first;** two after a dry run passes.
3. **Two fix rounds,** then the orchestrator stops and asks.
4. **`passes`:** only the orchestrator flips it, in the merge commit.
5. **Pane rule:** goes in `~/.claude/settings.local.json`. Changed when applied: it is
   `Bash(oskiv-pane *)` in `user/settings.json` (§5.1).
6. **Click-based UI checks:** the owner does them in person, batched in one ask at the end of the
   batch. A project may later let its verifier act.
7. **Context:** the owner wants the 1M window. The cutoff is a fixed 300K tokens, checked before
   every brief or fix round, with a 250K relaunch point (§3). It replaces the earlier 60% rule.
8. **Settings:** the uncommitted `teammateMode: "in-process"` and Opus 5.5 effort `medium` stay.
   `baseline.md` was updated to match.

**Settled since:** plain `opus` gives 1M on Opus 5.5 (§3).

**Still open:**
- Should `claude --tmux -w` launch the panes? **Rec.:** no. `teammateMode` stays in-process, and
  `oskiv-pane` is needed anyway for `/exit` and reading panes.

## 7. Remove from today's docs (to avoid double rules)

- oskiv `templates/CLAUDE.md`: replace "Ask all rulings together, each with a recommendation".
- macjev `CLAUDE.md`:
  - keep only its own stop items (`docs/product/`, `docs/decisions/`, real-Mac runs) and point to
    the template wording;
  - drop the orchestrator sentence in Git, which moves to the skill.
- macjev `progress.md` Owner decisions: add a dated entry that supersedes "I merge into main";
  don't delete the old one.
- tamsu `docs/architecture/baseline.md`:
  - "Rulings are asked together" → decide and record;
  - "`main` is mine: I review PRs in batches and merge" → in loop mode, the orchestrator merges
    and pushes after the merge gate;
  - the `ask` row of the permission table goes;
  - move "Autonomous building" from Direction into the design.

  Only the `teammateMode` line is changed now (ruling 8). The rest waits until the proposal is
  applied.
- The macjev research note stays as research. Its §2 items 3–4 (merge gate, `.worktreeinclude`)
  are covered here.
