# DB Connection Strategy

PFOS application repositories use `system.db` as the shared Postgres access
boundary. Repository public methods stay stable; private `_psql(sql)` adapters
now delegate to the shared helper instead of shelling out to Docker.

## URL Resolution

Database URL resolution is centralized in `system.db.resolve_database_url`:

1. Explicit `database_url` argument.
2. `DATABASE_URL`.
3. `POSTGRES_URL`.

Callers that require a configured database should use
`system.db.require_database_url`, which raises a deterministic error if no URL
is available.

## Connection Helpers

`system.db` exposes:

- `get_connection(...)`: context manager for a psycopg connection.
- `transaction(...)`: context manager that opens a connection transaction.
- `open_pool(...)`: optional module-level psycopg pool initialization.
- `close_pool()`: closes and clears the module-level pool.
- `execute_psql(sql, ...)`: compatibility adapter for current repository
  internals that returns a `subprocess.CompletedProcess`-shaped result with
  pipe-delimited stdout.

The helper uses `psycopg_pool` when the pool extra is installed and a pooled
connection is requested. If the pool extra is unavailable in a local bootstrap,
`get_connection` falls back to a direct `psycopg.connect` connection so unit
tests and simple scripts can still exercise the adapter surface.

For local validation compatibility, `execute_psql` falls back to the existing
Docker Compose `psql` execution path when neither `DATABASE_URL` nor
`POSTGRES_URL` is configured. Production services should set one of the
database URL environment variables so psycopg connection handling is used.

## Repository Migration Notes

Current repositories retain their existing method signatures and `_psql(sql)`
test seam. Unit tests that monkeypatch `_psql` continue to work.

Future repository hardening should move SQL toward parameterized psycopg cursor
execution behind this same module. That should be done incrementally and without
schema changes or API behavior changes.
