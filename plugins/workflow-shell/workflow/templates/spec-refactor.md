---
type: refactor
status: draft
---

# Spec: <name>

## Scope
Files or modules being refactored. Concrete list, not vague area.

## Why
What's wrong with the current code that justifies the refactor. "Cleanup" alone is insufficient — name the cost (slow tests, repeated bugs, blocked feature, etc.).

## Behavior preservation
This refactor changes NOTHING about external behavior. Existing tests must continue to pass without modification (mechanical renames only).

## Acceptance criteria
1. All existing tests pass without modification (or with mechanical renames documented in the diff).
2. <Specific structural change> verifiable how: <command / observation>
3. No new public surface introduced.
4. No behavior change observable from outside the refactored unit.

## Out of scope
- Behavior changes (those are features).
- Adjacent cleanup (file separate refactors).
- Performance changes unless explicitly listed in AC.

## Rollback plan
How to revert mid-refactor if a hidden coupling surfaces. Per-milestone rollback expected; see `plan-refactor.md`.

## Constitution check
- [ ] Rule 1 — <how this complies>
