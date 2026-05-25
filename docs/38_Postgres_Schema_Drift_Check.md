# Postgres Schema Drift Check

PFOS keeps the canonical documented Postgres schema in
`docs/04_Database_Schemas.sql` and the runtime bootstrap schema in
`infra/postgres/init/001_schema.sql`.

`make validate-sql-drift` compares those files and fails if their substantive
SQL content differs. The check normalizes trailing whitespace and final newline
differences only; table, index, constraint, function, trigger, or ordering
changes must be made in both files intentionally.

Run the check directly:

```sh
make validate-sql-drift
```

The target is also part of `make validate`, so schema drift blocks the standard
local validation gate.
