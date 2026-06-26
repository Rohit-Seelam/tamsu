---
name: backend-go
description: Rules specific to Go backend code in `backend/` and `db/`.
paths: [backend/**, db/**]
---

# Backend Go rules

## Module layout

- `backend/<domain>/` — one package per domain (auth, billing, notes, ...).
- `backend/middleware/` — http middleware only.
- `backend/email/`, `backend/queue/` — I/O adapters; isolate so domain code doesn't import them directly.

## Error handling

- Return errors; do not panic from handlers.
- Wrap errors with `fmt.Errorf("auth: signup: %w", err)` — package prefix + operation + cause.
- HTTP handlers translate domain errors to status codes in one place per package: `errors.go`.

## Database

- Use sqlc-generated code. Hand-written queries only for migrations and ops scripts.
- No ORMs. No GORM. We picked sqlc deliberately.
- Migrations: see `rules/migrations.md`.

## Testing

- Table tests for any function with >2 cases.
- Use stdlib `testing` + `httptest` + `testify/require` for assertion sugar.
- No `testify/mock` for new code (decided 2026-04-26 in `memory/conventions.md`).

## HTTP

- Router: chi only. No gorilla/mux. No Gin.
- Routes registered in `backend/server/routes.go` — one place to see the full surface.
- All `/api/v1/*` paths go through the auth middleware (after spec 001).
