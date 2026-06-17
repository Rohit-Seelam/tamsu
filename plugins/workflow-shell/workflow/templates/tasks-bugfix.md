---
type: bugfix
status: draft
---

# Tasks: <name>

## Spec coverage
- Reproduction confirmed → T1
- Fix → T2
- Regression test → T3
- Adjacent paths verified → T4

## Tasks

- [ ] T1 — Confirm reproduction in test environment
  - **Deliverable:** failing test that reproduces the bug
  - **Touches:** <test file>
  - **Estimate:** S

- [ ] T2 — Apply fix
  - **Deliverable:** the failing test from T1 now passes
  - **Touches:** <code files>
  - **Estimate:** S | M

- [ ] T3 — Add named regression test
  - **Deliverable:** explicit named test referencing the bug (e.g. `test_login_500_on_safari_v17`)
  - **Touches:** <test file>
  - **Estimate:** S

- [ ] T4 — Verify adjacent paths
  - **Deliverable:** quick checklist confirming fix didn't break adjacent code paths listed in `spec.md` Risk section
  - **Touches:** (read-only verification)
  - **Estimate:** S

## Dependencies
T2 blocks on T1; T3 can run alongside T2; T4 blocks on T2.

## Sequencing notes
T1 first — never apply a fix without a failing test that proves the bug exists.
