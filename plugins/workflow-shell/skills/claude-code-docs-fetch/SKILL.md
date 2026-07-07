---
name: claude-code-docs-fetch
description: Fetch the canonical Anthropic Claude Code docs index; detect deltas from the cached docs map; update `links.json` in place. Owned by `agents/research/claude-code-docs.md`; not directly user-invokable.
allowed-tools: WebFetch, Read, Write, Edit, Bash
argument-hint: "(no args; or --force to ignore cache)"
---

# Claude Code Docs Fetch

A self-updating docs map for Claude Code. Run on every consultation that needs current upstream data.

## Inputs

- `skills/research/claude-code-docs-fetch/links.json` — the cached docs map (see "Metadata file" below).
- Primary docs index URL: `https://docs.claude.com/llms-full.txt`.
- Fallback: `https://docs.claude.com/` (the human-readable index).

## Output

- `skills/research/claude-code-docs-fetch/links.json` — updated in place with the current map + `last_fetched` timestamp + a `last_delta` block describing what changed.

## Steps

1. **Read** `links.json`. If missing or invalid, treat as empty cache.
2. **WebFetch** the primary URL. If 4xx/5xx, fall back to the index URL and parse links from HTML.
3. **Parse** the response into a list of `{url, title, section, last_seen}` entries. Section is the doc category (hooks, skills, agents, settings, MCP, …).
4. **Compute delta** against cached `links.json`:
   - `new_pages` — URLs in fetched but not in cache.
   - `removed_pages` — URLs in cache but not in fetched.
   - `version_bumped` — URLs in both, but whose section or `last_modified` (if available) differs.
5. **Update** `links.json`:
   - Replace `pages` with the fetched list.
   - Set `last_fetched` to the current ISO timestamp.
   - Set `last_delta` with the three lists from step 4.
6. **Optional** — run `claude --version` and store the captured version under `claude_version` in `links.json`.
7. **Return** the delta summary to the calling agent.

## Metadata file shape

`links.json`:

```json
{
  "last_fetched": "2026-05-13T16:00:00Z",
  "claude_version": "2.1.32",
  "primary_url": "https://docs.claude.com/llms-full.txt",
  "fallback_url": "https://docs.claude.com/",
  "pages": [
    {
      "url": "https://docs.claude.com/en/docs/claude-code/hooks",
      "title": "Hooks",
      "section": "claude-code",
      "last_seen": "2026-05-13T16:00:00Z"
    }
  ],
  "last_delta": {
    "new_pages": [],
    "removed_pages": [],
    "version_bumped": []
  }
}
```

`links.json` is REQUIRED — without it, delta detection is impossible. The file ships seeded with a baseline docs map as of 2026-05-09 (not empty `{}`).

## Self-update contract

On every invocation, this skill updates its own `links.json`. This is intentional: the skill is its own state. The `claude-code-docs` agent does NOT edit project files; the skill self-updates inside its own folder. Cross-checker does NOT flag this as a Constitution Rule 7 violation because the skill's metadata is single-source-of-truth for "what docs exist upstream right now."

## Context-window note

This skill maintains a MAP (URL list), not a copy of the doc bodies. The agent reads pages dynamically via WebFetch on demand, scoped to the question at hand. Only the metadata file gets stored long-term.

## Failure modes

- Both primary and fallback URL unreachable → return cached `links.json` content with a warning; do not zero the cache.
- Parse failure on HTML fallback → log unknown shape to `links.json.parse_warnings[]`; agent surfaces the warning to the orchestrator.
- Write to `links.json` blocked → return delta in memory to the agent; agent surfaces via `BLOCKED-PERSIST-INLINE` per `workflow/communication.md`.

## Out of scope (scaffolding note)

The actual fetcher script and delta-detection algorithm are scaffolding-grade for spec 012's implement phase. The live runtime (full HTML parsing, version-pinning rules, retry policy) lands in a follow-up `feature` workflow per `specs/012-workflow-contract-v2/spec.md`'s out-of-scope list.
