---
type: refactor
status: draft
---

# Tasks: <name>

## Plan coverage
Maps to `plan.md` milestones.

## Tasks

### Milestone 1: prep
- [ ] T1.1 — Pin current behavior with characterization tests
  - **Deliverable:** new tests describing observable behavior
  - **Touches:** <test files>
  - **Estimate:** M
- [ ] T1.2 — Inventory callers of the refactored unit
  - **Deliverable:** caller list in `notes.md` or as PR description draft
  - **Touches:** (read-only)
  - **Estimate:** S

### Milestone 2: transform
- [ ] T2.1 — <transform step>
  - **Touches:** <files>
  - **Tests must remain green:** <list cited by name>
  - **Estimate:** M | L
- [ ] T2.2 — ...

### Milestone 3: cleanup
- [ ] T3.1 — Delete dead code identified in T2
- [ ] T3.2 — Remove characterization tests if redundant with existing tests
- [ ] T3.3 — Update docs/comments touched by the rename

## Behavior-preservation gate
After each milestone, ALL pre-existing tests must pass before the next milestone starts. If a test must change, log it under "Disputed behavior" in `plan.md` and pause for user review — that's a spec violation.

## Dependencies
- T2.x blocks on milestone 1 done.
- T3.x blocks on milestone 2 done.

## Parallelizable
T1.1 and T1.2 — concurrent. Otherwise serial within a milestone.
