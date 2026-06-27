---
name: migrations
description: Rules for database migration files in `db/migrations/`.
paths: [db/migrations/**]
---

# Migration rules

## Forward-only

We do not write down migrations. (This line is the decision of record; a longer rationale lives in `memory/topics/conventions.md` only when the memory store is populated — i.e. with the `workflow-memory-pipeline` plugin installed.)

## Naming

- Format: `NNNN_<verb>_<noun>.sql`. Zero-padded 4-digit sequence.
- Examples: `0007_create_users.sql`, `0011_create_subscriptions.sql`, `0012_add_billing_event_id_index.sql`.

## Additive only

- Add columns: nullable or with a default.
- Do not drop columns in the same migration that adds them. Drop only after a deploy cycle proves nothing reads the old column.
- Do not rename columns. Add new + backfill + drop old in three migrations.

## Backfills

- Inline backfills are acceptable for small tables (<10k rows). For larger tables, use a separate background script and reference it in the spec's `plan.md` rollback section.

## Rollback

- Rollback path is documented in the spec's `plan.md`, not in the migration file.
- Common rollback shape: feature flag off → optional new code path off → eventually drop the migration's effects in a future forward-only migration.

## CI

- Migration adds an entry to `db/migrations.go` for sqlc generation.
- `make db-migrate-test` must pass before merging.
