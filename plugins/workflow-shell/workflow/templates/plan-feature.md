---
type: feature
status: draft
---

# Plan: <name>

## Spec coverage
Which `spec.md` sections this plan addresses. Bullets cite `spec.md:section-or-line`.

- AC 1 → Milestone 1
- AC 2 → Milestone 2
- ...

## Approach
One paragraph — chosen approach and why over alternatives. Name what was rejected and why.

## Milestones
Numbered, ordered. Each independently shippable when possible. **Never call these "phases."**

### Milestone 1: <name>
- **Goal:** ...
- **Touches:** <files / modules>
- **Risk:** <what could go wrong>
- **Done when:** <observable check>

### Milestone 2: <name>
- **Goal:** ...
- **Touches:** ...
- **Risk:** ...
- **Done when:** ...

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| ... | low/med/high | ... |

## Rollback strategy
How to revert if shipped and broken. Per-milestone if the change is destructive.

## Open questions
**Empty before HITL gate** (this is at `tasks → implement`, not `plan → tasks`).
