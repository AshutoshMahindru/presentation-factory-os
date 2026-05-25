# GitHub Actions Validation

## Purpose

Baby Step 89 adds the checked-in PFOS validation workflow at
`.github/workflows/validate.yml`. The workflow runs on pull requests, pushes to
`main`, and manual dispatches. It requires no secrets and does not configure any
remote LLM provider credentials.

## Python Version

The workflow uses `actions/setup-python@v6` with Python `3.14`. The PFOS package
declares `requires-python = ">=3.11"`, and the local post-RC validation path is
already producing Python 3.14 bytecode in this checkout.

If GitHub-hosted runner availability or dependency wheels regress, the intended
fallback is Python `3.13`, then `3.12`. That fallback should be made explicitly
in the workflow and noted here because it would mean CI is no longer testing the
same interpreter minor version requested for post-RC hardening.

## Jobs

### `validation`

The static validation job installs the project with:

```bash
pip install -e .
```

It then runs the fast repository checks:

```bash
python scripts/validate_yaml.py
make validate-json
make compile
make no-agent-db-imports
```

### `integration`

The service-backed integration job starts the existing Docker Compose stack:

```bash
make docker-up
```

This brings up the required local services, including Postgres, Neo4j, and
Qdrant. It then validates live Postgres and Neo4j state before running the full
repository validation contract:

```bash
make validate-sql-live
make validate-cypher-live
make docker-doctor
make validate
```

After `make validate`, the job reruns focused integration groups so failures are
easy to locate in the Actions log:

- API and control-plane integration tests.
- Source lifecycle and outbox integration tests.
- Deck/export validation tests.

The repository currently has an empty
`tests/integration/test_end_to_end_brief_to_export.py` placeholder, so the
workflow runs the executable deck/export gate, slide schema, and narrative arc
tests until a real deck/export E2E test is checked in.

### `load-test`

The load-test job is optional and only runs from `workflow_dispatch` when the
`run_load_tests` input is enabled. The current `tests/load/` files are empty,
so the job skips cleanly until executable load-test assertions are added.

## Service Strategy

The workflow uses the repository's existing Docker Compose stack instead of
duplicating service definitions as GitHub Actions `services`. This is necessary
because current integration tests execute commands inside `agent-service` and
assert the intended network boundaries between app services and data stores.

If full Compose startup becomes too heavy for GitHub-hosted runners, keep
`validation` as the fast gate, keep `integration` as the Docker-backed gate, and
continue to leave `load-test` manual until runtime and assertions are stable.
