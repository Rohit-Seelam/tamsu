---
name: general
description: Always-on rules. Apply to every file in this repo regardless of language or area.
always: true
---

# General rules

## Imports / dependencies

- Don't add a new top-level dependency without a one-line note in the spec or PR explaining why.
- Prefer stdlib over third-party when the function is already in stdlib.

## Comments

- Default: no comments. Identifiers should explain what.
- One-line WHY comments allowed for non-obvious constraints, workarounds, or invariants.
- Never write "this function does X" — that's what the function name is for.
- Never reference issue numbers, PR numbers, or "added for X" in comments — those go in commit messages.

## Errors

- No silent suppression. Catch-all blocks that swallow exceptions are constitutional violations.
- All errors include enough context to identify the originating call.
- Don't log secrets. Don't log full request bodies (PII).

## Logging

- Structured logging only. JSON or key=value. No `printf` debugging in committed code.
- Log levels: debug / info / warn / error. No `trace`, no `fatal` (that's panic-level).

## Naming

- File names: kebab-case for markdown, snake_case for Go (testfile_test.go), kebab-case for TS/TSX.
- No abbreviations except universally understood (id, url, http, db).
- Private symbols start lowercase in Go; in TS, prefix with `_` for module-internal helpers.

## Tests

- Every new behavior gets a test. Bugfixes get a named regression test.
- No skipped tests without an attached TODO and tracking spec.
- No mocks of internal code. Mock at I/O boundaries only (HTTP clients, DB, filesystem).

## Delegation

- Post-spec-phase orchestrator delegation prompts SHOULD be ≤20 lines.
- They MUST cite artifact inputs by `path` (or `path#heading` for a specific section) rather than inlining artifact bodies — subagents read disk.
- The ONLY inlined content permitted is the fixed delegation-template fields from `workflow/communication.md` "Edge: orchestrator → subagent" (the canonical template home — not restated here).
- `cross-checker` flags inlined artifact bodies (beyond the permitted template fields) as a violation.
