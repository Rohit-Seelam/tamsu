---
type: bugfix
status: draft
---

# Spec: <name>

## Reproduction
Steps to reproduce, exactly as observed.

1. ...
2. ...

**Environment:** <OS, browser/runtime, version, relevant config>

## Expected vs actual
- **Expected:** ...
- **Actual:** ...

## First-seen / first-reported
When and where the bug was first noticed (commit, deploy, ticket). Helps scope blast radius.

## Root cause hypothesis
What we currently think is broken and why. Confirmed or revised during `implement`.

## Acceptance criteria
1. The reproduction no longer produces the bug.
2. A regression test exists, named to reference the bug.
3. <Adjacent affected paths still work — list them.>

**Docs-bug variant:** for documentation bugs (e.g. README claims a feature that doesn't exist, an agent file describes a behavior that doesn't work), the "regression test" can be a grep-based assertion that the broken phrasing is gone and the corrected phrasing is present. See `specs/009-fix-orchestrator-delegation-doc/regression-check.md` for an example. Constitutional Rule 1 (tests) is satisfied: the grep check fails before the fix, passes after.

## Risk
Other code paths this change touches. What we need to be careful not to break.

## Out of scope
Adjacent issues found during investigation that should be filed separately.

## Constitution check
- [ ] Rule 1 — <how this complies>
