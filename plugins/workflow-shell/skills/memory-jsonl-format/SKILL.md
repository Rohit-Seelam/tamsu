---
name: memory-jsonl-format
description: Schema map for Claude Code session JSONL files. Self-improving — the SDK memory pipeline probes the live schema each run and updates this skill in place when deltas surface. Source of truth for parsing main session / subagent / tool-result JSONLs.
allowed-tools: Read, Bash, Edit, Write
argument-hint: "[--probe <jsonl-path>] [--update]"
---

# Memory: JSONL Format

Schema reference for the JSONL files Claude Code writes under `~/.claude/projects/<project-slug>/`. The SDK memory pipeline (`workflow/sdk-pipeline.md`) reads this skill before parsing transcripts.

## File locations

| Kind | Path | One per |
|---|---|---|
| Main session | `~/.claude/projects/<project-slug>/<session-uuid>.jsonl` | session |
| Subagent transcript | `~/.claude/projects/<project-slug>/<session-uuid>/subagents/agent-<id>.jsonl` | subagent invocation |
| Subagent metadata | `~/.claude/projects/<project-slug>/<session-uuid>/subagents/agent-<id>.meta.json` | subagent invocation |
| Tool result | `~/.claude/projects/<project-slug>/<session-uuid>/tool-results/<toolu_id>.txt` | tool call with large output |

`<project-slug>` = cwd path with `/` rewritten to `-` (e.g., `/Users/alice/Projects/foo` → `-Users-alice-Projects-foo`).

## Top-level line schema

Each line of a `*.jsonl` file is a JSON object. Observed keys (2026-05-12 baseline):

```
parentUuid, isSidechain, type, message, isMeta, uuid, timestamp,
userType, entrypoint, cwd, sessionId, version, gitBranch, slug,
promptId, requestId
```

- `uuid` and `parentUuid` form the message DAG (per-message linkage).
- `sessionId` matches the JSONL filename.
- `isSidechain: true` flags subagent invocation context. Subagent transcripts are FULLY externalized — main JSONLs contain `isSidechain: false` only. (Verified: zero `isSidechain: true` lines in any inspected main JSONL.)
- `timestamp` is ISO-8601.

## `type` enum

Observed values:

| `type` | Meaning |
|---|---|
| `assistant` | Assistant message (text + tool_use blocks) |
| `user` | User message OR tool_result |
| `attachment` | Pasted image / file reference |
| `permission-mode` | Mode change event (default / plan / etc.) |
| `last-prompt` | Marker for the most recent user prompt |
| `file-history-snapshot` | Periodic snapshot of edited file state |
| `system` | System-emitted event (see `subtype` below) |
| `queue-operation` | Internal queue event |

## `system.subtype` enum

When `type == "system"`, the `subtype` field carries the specific event:

| `subtype` | Carries |
|---|---|
| `compact_boundary` | `compactMetadata.{trigger, preTokens, postTokens, durationMs, preservedSegment.{headUuid, anchorUuid, tailUuid}}`. Marks an in-file `/compact` event — chapter break, NOT a new file. |
| `away_summary` | Background-task summary on user return |
| `turn_duration` | Per-turn timing telemetry |
| `stop_hook_summary` | Output of a Stop hook |
| `local_command` | Output of a `! <cmd>` invocation |
| `informational` | Generic informational system message |

## Subagent `.meta.json` shape

Paired with each `agent-<id>.jsonl`:

```json
{
  "agentType": "general-purpose",
  "description": "<the description string passed to the Agent tool>"
}
```

Fold the `agentType` + `description` into memory extraction so each subagent's role is preserved alongside its transcript.

## Compact-boundary handling

`compact_boundary` is an INLINE event in the same JSONL — not a separate file. Process as a chapter break:

- Events before the boundary = "pre-compact phase N".
- Events after the boundary = "post-compact phase N+1".
- `preservedSegment.{headUuid, anchorUuid, tailUuid}` names the kept-content boundary.

No deduplication needed; each event appears exactly once in the canonical JSONL.

The repo-local supplementary archive at `<repo>/.claude/sessions/mainagent/raw/<session-id>-segment-N.jsonl` (written by the `PreCompact` hook) is REDUNDANT, not canonical. SDK reads the in-file marker; the segment file exists for debugging.

## Self-improvement contract

On every SDK memory-pipeline invocation:

1. Sample the schema with `jq`:
   ```bash
   jq -r 'keys[]' "$JSONL" | sort -u
   jq -r 'select(.type=="system") | .subtype // "<none>"' "$JSONL" | sort -u
   ```
2. Compare against this skill's documented keys + enum values.
3. If delta detected (new top-level key, new `type` value, new `system.subtype` value), the SDK Edits this file in place to add the new entries — this is one of the few Edit-allowed paths for the SDK subprocess outside memory.
4. Log the delta in the SDK's run report; surface to user as a one-line note.

**Why a skill, not hardcoded:** Anthropic ships Claude Code updates frequently; schemas can shift between versions. A self-improving skill is the cheapest way to track upstream without breaking parsing.

## Failure modes

- `jq` not available → SDK falls back to Python `json.loads` per line; logs the fallback.
- Unknown top-level key not previously seen → add to this skill's "Top-level line schema" section, append to a "Recently added" list at the bottom, surface to user.
- Unknown `subtype` → same handling as above for the `subtype` enum table.

## Recently added (auto-maintained)

<!-- The SDK appends entries here on each delta. Most recent first. -->

(empty — baseline 2026-05-12)
