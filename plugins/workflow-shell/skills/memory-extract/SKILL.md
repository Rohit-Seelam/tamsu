---
name: memory-extract
description: Extract durable facts and decisions from compiled session summaries into memory/topics/. Deferred — placeholder skill, not yet implemented.
allowed-tools: Read, Write
argument-hint: "[--since <ISO-date>]"
disable-model-invocation: true
---

# Memory: extract

**STATUS: deferred.** Placeholder.

## Why deferred

The first transform (raw → compiled) is sufficient for the current workflow; auto-extraction has historically over-promoted noise. Extraction will land after we have a corpus of compiled sessions (≥30) to evaluate signal-to-noise.

## Future shape

When implemented, this skill will:

1. Read `sessions/*/compiled/*.md` since last extraction.
2. Identify candidate memories matching the four types in CLAUDE.md auto-memory: `user`, `feedback`, `project`, `reference`.
3. For each candidate, check against existing entries in `memory/topics/<topic>.md` for duplicates.
4. Append new entries; flag duplicates for user review.
5. Update `memory/MEMORY.md` index.

`disable-model-invocation: true` blocks auto-load until ready.
