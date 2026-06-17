---
name: tests
description: Rules for test files. Applies to backend `*_test.go` and frontend `*.test.ts(x)`.
paths: [backend/**/*_test.go, frontend/**/*.test.ts, frontend/**/*.test.tsx]
---

# Test rules

## Naming

- Backend: `Test<Subject>_<Behavior>` — e.g., `TestLogin_SetsSessionCookie`.
- Frontend: `describe('<Subject>', () => { it('<behavior>', ...) })` — same pattern, just JS-ish.
- Regression tests for bugfixes: include the bug context in the name. `TestLogin_TrailingSemicolonInCookieHeader` (spec 002).

## Structure

- Arrange / Act / Assert. Comment-free; whitespace separates the three.
- Table tests when >2 cases. Use `t.Run` so each row is reportable.

## Coverage

- Every spec acceptance criterion has at least one named test.
- `cross-checker` runs an AC ↔ test name mapping in the verify phase.

## Skipping

- `t.Skip("flaky — see flaky-tests.md")` is allowed only with a reason and a tracking entry.
- Skipped tests with no reason → `major` finding from `qa-engineer`.

## Fixtures

- Test data in `<package>/testdata/` (Go) or `<feature>/__fixtures__/` (frontend).
- Don't hand-write JSON if it can be generated from the same types as production code.

## Assertions

- Backend: `require.NoError(t, err)`, `require.Equal(t, want, got)` — fail-fast.
- Frontend: `expect(...).toBe(...)`. Avoid `.toEqual` for primitives.
