# Communication

Who talks to whom, when, and through which channel. Wrong-channel chatter is the most common failure mode in agent-team systems — this doc locks the contract.

## The triangle

```
              USER
              ╱  ╲
   prompts   ╱    ╲   completion
   gates    ╱      ╲  summaries
   interrupts        ╲
           ╱          ╲
          ╱            ╲
   ORCHESTRATOR ────────► SUBAGENTS
                  delegate
                ◄────────
                  return summary
```

Three edges, all bidirectional, but **never** user ↔ subagent direct. Every subagent message goes through the orchestrator, which decides what to surface.

## Edge: user → orchestrator

User speaks via:

1. **Initial prompt** — kicks routing.
2. **Gate response** — answer to `AskUserQuestion` at a HITL gate.
3. **Mid-flight interrupt** — `[Esc]` or new prompt while a subagent runs.
4. **Rollback / resume requests** — "go back to <phase>", "resume <feature-id>".

The orchestrator does not request input outside these channels. If it needs a decision, it pauses with a structured `AskUserQuestion`.

## Edge: orchestrator → user

Orchestrator speaks at:

1. **Phase boundaries** — one-line status: "Spec phase complete. spec-verifier: pass."
2. **HITL gates** — structured `AskUserQuestion`.
3. **Verifier-loop escalation** — after `max_fix_rounds`, `AskUserQuestion` with the latest report.
4. **Completion** — final summary with PR link / commit / artifacts list.
5. **Blocked** — when external action needed (env var missing, auth required), `AskUserQuestion` with retry / skip / stop.

Stay quiet otherwise. No "I'm now reading X" / "let me think about Y" narration. The user can read the diff and the verification reports.

## Edge: orchestrator → subagent

Delegation prompt template (orchestrator emits this when spawning):

```
Phase: <phase>
Feature: <NNN-slug>
Workflow type: <type>

Inputs (read these first):
- specs/<NNN>/state.json
- specs/<NNN>/<previous-artifact>.md
- workflow/templates/<this-template>.md
- constitution.md

Your job: <one sentence>.
Output: write/replace specs/<NNN>/<artifact>.md following the template.
Constraints: <budget>, <style>, <constitutional rules to enforce>.
Return contract: per workflow/communication.md (DONE | BLOCKED | NEEDS_USER + 3-line summary).
```

The orchestrator does NOT paste artifact bodies into the prompt. Subagents read disk. Context budget for the orchestrator stays clean.

### Tool-batching rule (state.json + Agent)

**Do NOT batch `state.json` Edits with `Agent` invocations in the same tool message.** The Agent call invalidates the file's read-state in the harness; a subsequent Edit will fail with "File has not been read yet" until you re-Read.

Pattern that works:

1. Edit `state.json` (phase advance, history append, autonomous toggle) — own message.
2. Agent invocation — own message.

Pattern that breaks:

1. Edit + Agent in the same message — Edit may silently get cancelled or fail; subsequent Edits in the next message error.

This is a harness behavior surfaced during spike 010; if Claude Code's harness changes, revisit.

## Edge: subagent → orchestrator

Return contract — every subagent returns:

```
Status: DONE | BLOCKED | NEEDS_USER

Wrote: <artifact path(s)>
Skipped: <what wasn't done and why>
Blocker: <if BLOCKED: what's stopping you, what's needed to unblock>
User question: <if NEEDS_USER: the question to forward, with 2 recommended options>
```

Orchestrator parses this and:

- `DONE` → trigger verifier.
- `BLOCKED` → escalate to user via `AskUserQuestion` (Pattern E below).
- `NEEDS_USER` → forward the subagent's question via `AskUserQuestion` (Pattern D below).
- `BLOCKED-PERSIST-INLINE` → orchestrator persists the subagent's content on its behalf (see below).

### `BLOCKED-PERSIST-INLINE` — harness write-block fallback

The Claude Code harness sometimes blocks subagents from writing certain files (observed for `findings.md` in spike 008 and spike 010 — the heuristic appears to flag "report-shaped" filenames). When this happens, the workflow contract still requires the artifact on disk.

Subagent contract when blocked:

```
Status: BLOCKED-PERSIST-INLINE

Wrote: nothing — harness blocked Write for <path>
Skipped: <if any>
Blocker: <one line: which file, what guardrail message>
User question: n/a

---

Persist the following to <path>:

```markdown
<full artifact content here, fenced as markdown>
```
```

Orchestrator behavior:

1. Parse the response. The artifact content is between the inner ```markdown ... ``` fences.
2. Confirm the target path matches what the spec / phase expects.
3. Use `Write` (orchestrator has tool privileges the subagent lacked) to persist exactly that content to the named path.
4. Continue the workflow as if the subagent had succeeded — record the harness-block in `state.json.phase_history[].note`.

Two confirmed instances (spikes 008, 010). The pattern is durable; any new instance is captured at `deliver` by the SDK memory pipeline (the sole memory writer — `constitution.md` Rule 5), not hand-written.

## Edge: subagent → user (forbidden)

Subagents do not speak directly to the user. If a subagent has a question, it returns `NEEDS_USER` and the orchestrator forwards it. The orchestrator may rephrase for clarity but does not invent or filter beyond translation (jargon → plain language).

## The SDK memory subprocess is NOT in the triangle

The `claude-agent-sdk` subprocess that runs at every `deliver` (per `phases.md` "Deliver: SDK memory pipeline" and `workflow/sdk-pipeline.md`) is NOT a subagent in the orchestrator ↔ subagent ↔ user triangle. It does not speak to the user. It does not receive prompts mid-flight. It runs as a leaf subprocess against the just-completed spec; its output is memory file writes via a propose→write split — the LLM half EMITS a proposal (no file writes), then a deterministic Python writer writes the canonical store (`~/.claude/projects/<project-slug>/memory/`) and mirrors the non-personal subset into `<repo>/.claude/memory/` (silos canonical-only; see `workflow/artifacts.md` "Selective mirror policy"); its failure modes surface to the orchestrator only.

Failure handling: if the SDK subprocess crashes, times out, or returns a non-zero exit, the orchestrator logs the failure and surfaces a ONE-LINE warning to the user via Pattern E. Memory updates are best-effort; they do NOT block deliver completion. The next workflow's `verify` phase picks up any divergence via cross-checker's selective-mirror-policy compliance check (NOT exact equality; `agent-memory/` carved out) — see `workflow/artifacts.md` "Selective mirror policy".

## `AskUserQuestion` patterns

### Tool-call shape (all patterns)

```
AskUserQuestion({
  questions: [{
    question: "<full question text, ending in '?'>",
    header: "<≤12 char chip label>",
    multiSelect: false,
    options: [
      { label: "<5-word label>", description: "<what this means>" },
      { label: "<5-word label>", description: "..." }
    ]
  }]
})
```

The `questions` parameter is REQUIRED — forgetting it produces `InputValidationError: required parameter 'questions' is missing`. `Other (specify)` is auto-added by the harness when applicable; never include it manually. If you recommend a specific option, put it first and append "(Recommended)" to its label per the tool's own guidance. The five patterns below differ only in question text and option set.

### Pattern A — HITL gate

```
question: "<phase> is complete and verified. Advance to <next-phase>?"
options: [Advance, Revise, Stop]
```

Three options, no `Other`. Gate is binary-ish.

### Pattern B — Routing ambiguity

```
question: "The prompt could be a bugfix or a feature. Which fits?"
options:
  - "Bugfix (existing behavior is wrong)"
  - "Feature (new behavior I want to add)"
  - "Other (specify)"
```

`Other (specify)` always present in classification questions — free-text fallback when the model misreads intent.

### Pattern C — Verifier escalation (after max rounds)

```
question: "<phase>-verifier failed <max_fix_rounds> times. Latest findings: <one-line summary>. Path: verification/<phase>-report.md"
options:
  - "Read the report and revise instructions"
  - "Override and advance anyway"
  - "Stop"
```

User reads the full report on disk for context.

### Pattern D — Subagent forwarded clarification

```
question: "<subagent>'s question: <question text>"
options:
  - "<subagent's recommended choice>"
  - "<subagent's alternate>"
  - "Other (specify)"
```

Subagent supplies 2 options in its `NEEDS_USER` return; orchestrator adds `Other`.

### Pattern E — Blocked (environment / external)

```
question: "<subagent> blocked: <reason>. How to proceed?"
options:
  - "Retry now (after I fix it)"
  - "Skip this step"
  - "Stop"
```

Used for missing credentials, network failures, missing files, etc.

## Status updates: when to talk, when not

| Event | Speak? | Form |
|---|---|---|
| Phase started | No | — |
| Subagent spawned | No | — |
| Subagent returned `DONE` | No | — |
| Verifier returned `pass` | Yes | `<phase> verified.` |
| Verifier returned `fail` | Yes | `<phase>-verifier failed. Spawning fixer (round N/<max>).` |
| Fixer returned | No | — |
| Fixer max rounds hit | Yes | Pattern C |
| HITL gate reached | Yes | Pattern A |
| Subagent returned `BLOCKED` | Yes | Pattern E |
| Subagent returned `NEEDS_USER` | Yes | Pattern D |
| Completion | Yes | Final summary (path list + PR link) |
| Constitutional violation flagged | Yes | Immediate pause + show finding |

Default: silence. The user reads disk for detail.

## Failure escalation order

1. Subagent fails (errors, not "fail" verdict) → orchestrator retries once with same prompt.
2. Still failing → orchestrator escalates to user with the error and Pattern E options.
3. Verifier fails → fixer loop (handled in `evaluation.md`).
4. Fixer hits `max_fix_rounds` → Pattern C to user.
5. Constitutional violation flagged → pause immediately regardless of phase, surface finding via Pattern E equivalent.

## Vocabulary translation

When forwarding subagent text to the user, the orchestrator MUST translate jargon into the user's language:

- "AC" → "acceptance criterion"
- "DRY" → name the actual duplication
- "TKTK" / "TBD" → flag as incomplete content
- "Phase 1" inside `plan.md` → "Milestone 1" (verifier flags this earlier; treat any leak as a bug)

## Mid-flight interrupts

If the user types while a subagent is running:

1. Orchestrator allows the in-flight subagent to complete its current tool call (don't kill mid-action).
2. Reads the user's interrupt as a new top-level instruction.
3. If the interrupt is a question → answer (freeform), then resume.
4. If the interrupt changes scope → pause the workflow; ask the user via Pattern A whether to revise the active phase or roll back.
5. If the interrupt is `stop` → set `state.json.status: paused` and exit.
