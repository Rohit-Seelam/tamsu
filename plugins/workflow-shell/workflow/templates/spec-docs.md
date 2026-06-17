---
type: docs
status: draft
---

# Spec: <name>

## Scope
Concrete file list of doc(s) to be created, edited, or deleted. Not a vague area.

## Why
What's wrong with the current docs that justifies this change. Name the cost — confused contributors, contract gap, drift between two files. "Cleanup" alone is insufficient.

## Target state
What the docs will say after the change. Brief for trivial edits; detailed for redesigns.

## Target files
Explicit list of files to create / edit / delete. The verifier diffs `git status` against this list.

## Acceptance criteria
Mechanically checkable assertions. For docs specs, "tests" are grep-based or structural (e.g., "section 'X' exists in file Y"; "no occurrence of word 'currency' in agents/research/"). Numbered.

1. <assertion>
2. <assertion>

## Risk and rollback
Default: `git revert <commit>` on the implement-phase commit. Flag any aspects that aren't `git revert`-safe (typically none).

## Out of scope
Explicit exclusions. Reference adjacent specs/PRDs that DO cover them, or "(planned)" with rationale.

## Constitution check
- [ ] Rule 1 — `n/a` (pure-docs spec; no behavior to test)
- [ ] Rule 2 — <or `n/a`>
- [ ] Rule 3 — <`git revert` is the rollback path>
- [ ] Rule 4 — <or `n/a`>
- [ ] Rule 5 — <how memory hygiene applies, if at all>
- [ ] Rule 6 — <verifier authority — typically `n/a` to call out>
- [ ] Rule 7 — <one-source-of-truth — HIGHEST RISK for docs specs touching multiple files>

## Open questions
**Empty before HITL gate.**

<!-- Optional sections — uncomment if needed:
## Sub-designs
For large docs specs that decompose into linked sub-files. Each sub-file under `specs/<NNN>/design/<NN>-<topic>.md` with: target state, departures from current state, target file list, acceptance criteria.

## Supersession note
When this spec supersedes part of an earlier spec or finding. Cite source via path:line.
-->
