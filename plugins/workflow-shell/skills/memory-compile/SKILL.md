---
name: memory-compile
description: Compile raw session .jsonl files in sessions/*/raw/ into compact markdown summaries in sessions/*/compiled/. Run by SessionEnd hook; user-invocable for backfill.
allowed-tools: Read, Write, Bash
argument-hint: "[--since <ISO-date>] [--agent <name>]"
---

# Memory: compile

Compile raw session transcripts into markdown summaries. Reads `.jsonl`, writes `.md`.

## Steps

1. Find raw files matching the optional `--since` filter:
   ```bash
   find .claude/sessions -path '*/raw/*.jsonl' -newer <ref> -print
   ```
2. For each raw file:
   - Determine target: replace `/raw/` with `/compiled/`; replace extension `.jsonl` → `.md`.
   - If target already exists and is newer → skip.
   - Else read raw, run summarization (claude-agent-sdk subprocess or built-in summarizer).
3. Compiled markdown structure:
   ```markdown
   ---
   session_id: <uuid>
   agent: main | <subagent-name>
   started: <ISO>
   ended: <ISO>
   feature_ids: [NNN-slug]
   ---

   # Summary
   <one paragraph>

   # Decisions
   - <bullet>

   # Open threads
   - <bullet>

   # File touches
   - <path> (read|write|edit)
   ```
4. Print `wrote N compiled summaries`.

## Notes

- This skill does NOT extract memories. That's `memory:extract` — separate, deferred for now.
- The compilation prompt lives in `skills/memory/compile/scripts/prompt.md` (not yet authored — placeholder).
