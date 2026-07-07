---
name: extraction-learnings
description: Self-updating heuristics for the SDK memory pipeline's extraction craft. Seeded with five baseline heuristics; the pipeline appends one dated bullet per novel heuristic emitted in a deliver. Owned by the SDK subprocess — no other agent edits it.
allowed-tools: Read, Edit, Write
argument-hint: "(read-only for non-pipeline agents)"
---

# Memory: Extraction Learnings

Complements `skills/memory/jsonl-format/SKILL.md`. The JSONL-format skill is the schema reference (input parsing); this skill is the **output craft** reference — how the SDK turns parsed transcripts into memory entries that future agents can act on.

## Scope and ownership

- **Owner.** The SDK memory pipeline (`hooks/sdk_memory_pipeline.py`). No other agent edits this file mid-workflow.
- **Loaded.** Bundled into the SDK system-prompt prefix (`WORKFLOW_FILES`) every run, so the heuristics compound over time.
- **Cap.** 200 lines OR 25 KB, whichever comes first. Overflow rolls to `extraction-learnings-archive.md` in this same directory (AC-13).

## Novel-heuristic marker protocol

When the SDK agent applies a heuristic that is NOT already in the list below, it MUST emit a single line in its final `ResultMessage`:

```
[learning] <one-line description of the heuristic, present tense>
```

The pipeline parses these markers post-run and appends one dated bullet per novel marker to the "Heuristics" list. Absence of any `[learning]` marker means no append — the file is unchanged.

Bullets are appended with the format:

```
- YYYY-MM-DD — <one-line heuristic>
```

## Heuristics

### 1. Cross-reference convention: `[[slug]]`

When a memory entry references another memory file, use `[[slug]]` where `slug` matches the target memory's `name:` frontmatter (kebab-case). Example: a project memory about spec 014 can link to `[[sdk-permission-model]]`. Future readers (and the SDK) treat `[[...]]` as a follow-link signal.

### 2. Supersession marker: `SUPERSEDED by [[other]]`

When a new memory supersedes an older one, do NOT delete the old file. Instead, prepend a one-line header to the old file: `**SUPERSEDED by [[<new-slug>]]** — <one-line reason>`. The MEMORY.md index entry for the superseded memory keeps its line but adds `[SUPERSEDED]` to the hook. This preserves the audit trail without polluting future agents' working set.

### 3. 25 KB / 200-line cap with sub-topic split

Topic files cap at 200 lines OR 25 KB. When a file approaches the cap, split on a natural sub-topic boundary (a `##` heading) into a new file. The original file's hook in MEMORY.md keeps the broad topic name; the new file gets its own MEMORY.md line with a narrower hook. Example: `sdk-014-open-items.md` → split out `sdk-014-mirror-budget.md` if mirror discussion grows past one section.

### 4. Teammate-vs-subagent attribution: `(teammate)` suffix

Subagents and teammates are different actors. Memory writes MUST distinguish:
- **Subagent.** Bare agent name: `product-manager authored spec`.
- **Teammate.** Agent name + `(teammate)` suffix: `backend-engineer-1 (teammate) implemented X`.
- **Never.** Raw session IDs, `agent-<id>` strings, or model names as actor labels.

The actor map in the SDK prompt (per AC-8) supplies the mapping for both — use it.

### 5. MEMORY.md index-line format

`MEMORY.md` is the index, not memory. Each entry is exactly one line, under ~150 characters:

```
- [Title](topics/file.md) — one-line hook
```

`Title` is human-readable; the file path is relative to `memory/`; the hook is a single sentence orienting future agents. Do NOT write memory content directly into MEMORY.md. The 200-line cap applies (lines past 200 are truncated by Claude Code at session start).

## Recently added (auto-maintained)

<!-- The SDK appends dated bullets here on each delta. Most recent first. -->

(empty — baseline 2026-05-17)
- 2026-06-02 — Treat parent-shell-cd as insufficient for grandchild-process working-directory inheritance; pin cwd= explicitly on subprocess invocation options at the innermost call layer.
- 2026-06-02 — When a verifier finds a phantom task reference in an AC coverage table (a label that survived a restructure), surface it as a minor cosmetic finding but capture the underlying lesson for the authoring agent's silo, because only cross-checker catches this class.
- 2026-06-11 — When a fix changes a labeled state-machine's CLI semantics, the prior round-trip test that asserted shape compatibility is the precise reason the bug shipped green — propose a shared topic distinguishing shape-roundtrip from semantic-roundtrip.
- 2026-06-11 — Treat any committed artifact named in a spec's Reproduction section as a regression fixture: an AC that asserts the artifact remains unchanged belongs alongside the corrective-behavior ACs.
