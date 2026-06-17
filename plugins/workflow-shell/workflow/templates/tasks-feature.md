---
type: feature
status: draft
---

# Tasks: <name>

## Plan coverage
Maps to `plan.md` milestones. Cite `plan.md:milestone-N`.

## Tasks

### Milestone 1: <name>
- [ ] T1.1 — <action>
  - **Touches:** <files>
  - **Deliverable:** <what's done at the end>
  - **Test:** <test case to add or modify>
  - **Estimate:** S | M | L
- [ ] T1.2 — ...

### Milestone 2: <name>
- [ ] T2.1 — ...
- [ ] T2.2 — ...

## Dependencies
- T2.1 blocks on T1.3
- T3.x blocks on milestone 2 done
- ...

## Parallelizable
Tasks safe to run concurrently (no shared file surface).

- T1.1 and T1.2 — no shared files
- ...

## Sequencing notes
Anything non-obvious about ordering — not just dependencies.
