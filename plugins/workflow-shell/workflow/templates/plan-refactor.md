---
type: refactor
status: draft
---

# Plan: <name>

## Spec coverage
Pull file/module list from `spec.md`. Cite by `spec.md:section-or-line`.

## Strategy
Choose one and explain:

- [ ] In-place refactor
- [ ] Parallel implementation + cutover
- [ ] Strangler / branch-by-abstraction

Why this strategy over the others.

## Milestones
Each milestone preserves green tests at the boundary. **Never call these "phases."**

### Milestone 1: prep
- Pin current behavior with characterization tests if coverage is thin.
- Identify all callers of the refactored unit.
- **Done when:** all relevant behaviors are covered by passing tests.

### Milestone 2: transform
- Apply the structural change.
- All tests still pass at the end.
- **Done when:** structural goal met AND all tests green.

### Milestone 3: cleanup
- Delete dead code.
- Remove characterization tests if redundant with existing tests.
- **Done when:** no dead code; no duplicate tests.

## Behavior-preservation checks
Tests / observations that must remain green throughout. Cited by name.

- `test_<name>` — covers <behavior>
- ...

## Rollback strategy
Per-milestone rollback. Refactors should be revertable in 1 commit per milestone.

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hidden caller missed | med | Grep + type check before milestone 2 |
| ... | ... | ... |

## Open questions
**Empty before next HITL gate.**
