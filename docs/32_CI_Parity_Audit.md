# CI Parity Audit

## Purpose

Audit CI parity versus local PFOS v3.2.4 validation after local Docker
stabilization. This is a documentation-only audit of the current repository
state; it does not change Docker, Makefile targets, app behavior, source
lifecycle behavior, or outbox worker behavior.

## Audited Inputs

- `Makefile`
- `.github/workflows` when present
- `scripts/`
- `tests/integration/`
- `tests/load/`
- `docker-compose.apps.yaml`
- `docs/18_CI_CD_Schema_Validation.md`

No `.github/workflows` directory is present in this checkout. The only CI
workflow definition found during this audit is the illustrative workflow in
`docs/18_CI_CD_Schema_Validation.md`.

## Current Local Validation Surface

`make validate` currently runs:

```bash
make compile
make validate-json
make validate-yaml
make no-agent-db-imports
make test
```

This covers Python compilation, checked-in JSON Schema validity, checked-in
YAML parsing under `docs/`, the agent raw database import guard, and the full
pytest suite.

`make validate-live` currently runs:

```bash
make docker-up
make validate-sql-live
make docker-doctor
make validate
```

This starts the local app stack, applies the live Postgres schema bootstrap,
runs the Docker environment doctor, then runs the same local validation suite.

## Parity Matrix

| Validation area | Local command | Current local coverage | CI coverage in repo | Parity status |
| --- | --- | --- | --- | --- |
| Local validation bundle | `make validate` | Compile, JSON schemas, YAML docs, no-agent DB imports, full pytest | No checked-in workflow | Gap: local only |
| Live validation bundle | `make validate-live` | Starts Docker services, applies Postgres schema, runs docker doctor, then `make validate` | `docs/18` proposes service-backed CI but no workflow exists | Gap: documented only |
| Docker doctor | `make docker-doctor` | Checks Docker CLI, Compose CLI, compose file presence, expected services, and required Postgres tables when reachable | Not present in a checked-in workflow | Gap: local only |
| JSON schema validation | `make validate-json` | `scripts/validate_json_schemas.py` validates four schema files in `docs/` | `docs/18` includes equivalent inline validation | Partial: no enforced CI |
| YAML validation | `make validate-yaml` | `scripts/validate_yaml.py` parses `docs/*.yaml` | `docs/18` includes equivalent inline validation | Partial: no enforced CI |
| SQL validation | `make validate-sql-live` | Applies `infra/postgres/init/001_schema.sql` inside the local Postgres container | `docs/18` proposes validating `docs/04_Database_Schemas.sql` against CI Postgres | Mismatch: different SQL source files |
| Cypher validation | `make validate-cypher-live` | Target exists and applies `infra/neo4j/constraints.cypher` to local Neo4j | `docs/18` proposes validating `docs/05_Evidence_Graph_Cypher.cypher` | Gap: not included in `validate` or `validate-live`; source file mismatch |
| No-agent-DB-import guard | `make no-agent-db-imports` | `scripts/check_no_agent_db_imports.py` rejects raw database imports under `agents/**/*.py` | `docs/18` includes equivalent inline check | Partial: no enforced CI |
| Full pytest suite | `make test` | Runs configured pytest suite under `tests` with a Python shim on `PATH` | `docs/18` proposes `pytest` | Partial: no enforced CI |
| Required source lifecycle/outbox integration tests | `make test` | Runs all discovered integration tests, including outbox and source lifecycle tests that contain test bodies | `docs/18` lists required focused tests | Partial: some named files are empty or weaker than documented intent |
| Load-test readiness | No Makefile target | `tests/load/test_outbox_queue_load.py` and `tests/load/test_source_retraction_queue_load.py` exist but are empty | `docs/18` documents load-test expectations | Gap: placeholder files only |

## Detailed Findings

### 1. Checked-In CI Is Missing

There is no `.github/workflows` directory in the repository checkout. As a
result, CI parity cannot currently be measured against an enforced workflow.
The repository has a local validation contract in `Makefile` and a documented
CI template in `docs/18_CI_CD_Schema_Validation.md`, but no checked-in GitHub
Actions workflow actually runs those commands.

Recommended follow-up: add a checked-in CI workflow that calls Makefile targets
instead of duplicating validation logic inline.

### 2. `docs/18` Has Drifted From The Makefile

`docs/18_CI_CD_Schema_Validation.md` still describes targets such as
`validate-ci`, `validate-sql`, `validate-cypher`, `outbox-integration-test`,
and `load-test`. The current Makefile exposes `validate-live`,
`validate-sql-live`, and `validate-cypher-live` instead, and it does not define
`validate-ci`, `validate-sql`, `validate-cypher`, `outbox-integration-test`, or
`load-test`.

Recommended follow-up: update `docs/18` or add the missing targets in a
separate implementation step. For CI parity, the lower-risk path is to make CI
invoke the existing Makefile targets first.

### 3. SQL Validation Uses Different Source Files

The current Makefile validates live Postgres by copying
`infra/postgres/init/001_schema.sql` into the Postgres container and executing
it. The documented CI template validates `docs/04_Database_Schemas.sql`.

This means local live validation and the documented CI path are not asserting
the same SQL artifact.

Recommended follow-up: decide which SQL file is canonical for executable
schema validation, then align local and CI validation to that single source or
add an explicit drift check between the two artifacts.

### 4. Cypher Validation Is Available But Not In The Main Live Gate

The Makefile has `validate-cypher-live`, which applies
`infra/neo4j/constraints.cypher` to the local Neo4j container. However,
`validate-cypher-live` is not part of `make validate` or `make validate-live`.

The documented CI template validates `docs/05_Evidence_Graph_Cypher.cypher`,
which is a different Cypher source than the current local Makefile target.

Recommended follow-up: add Cypher validation to the live or CI gate after
choosing the canonical Cypher source file.

### 5. Docker Doctor Is Local-Only

`make docker-doctor` provides useful post-stabilization checks:

- Docker CLI availability.
- Docker Compose CLI availability.
- `docker-compose.apps.yaml` presence.
- Expected services defined in the compose file.
- Required Postgres tables when the database is reachable.

The documented CI template does not include this doctor, and no checked-in CI
workflow exists.

Recommended follow-up: run `make docker-doctor` in any Docker-backed CI job
after services are started and Postgres schema bootstrap has completed.

### 6. Required Integration Test Coverage Is Uneven

The following source lifecycle and outbox integration test files contain active
test bodies and are discovered by `make test`:

- `tests/integration/test_outbox_eventual_consistency.py`
- `tests/integration/test_outbox_neo4j_failure_retry_backoff.py`
- `tests/integration/test_outbox_neo4j_side_effect.py`
- `tests/integration/test_workflow_outbox_gate.py`
- `tests/integration/test_source_retraction_e2e_regression.py`
- `tests/integration/test_agent_network_isolation.py`

The following required or documented test files currently exist but are empty:

- `tests/integration/test_source_retraction_cascade.py`
- `tests/integration/test_source_retraction_500_claims_async.py`
- `tests/load/test_outbox_queue_load.py`
- `tests/load/test_source_retraction_queue_load.py`

The active `test_outbox_neo4j_failure_retry_backoff.py` verifies error count
and error recording for a forced outbox failure. It does not currently exercise
the full retry/backoff sequence described in `docs/18`.

The active `test_agent_network_isolation.py` verifies allowed service
connectivity and blocked datastore connectivity from `agent-service`, but it
does not assert the specific TCP failure marker set documented in `docs/18`.

Recommended follow-up: fill the empty required test files and either strengthen
the active tests to match `docs/18` or update `docs/18` to reflect the current
accepted behavior.

### 7. Load-Test Readiness Is Not Implemented

`tests/load/` exists and contains the expected load-test filenames, but both
files are empty. The current Makefile has no `load-test` target.

Recommended follow-up: treat load tests as not ready for CI gating until the
two load-test files contain executable assertions and a Makefile or CI entry
point exists.

## Recommended CI Parity Contract

For a future implementation PR, the lowest-drift CI contract should call local
targets directly:

```bash
make validate
make docker-up
make validate-sql-live
make validate-cypher-live
make docker-doctor
```

If CI runtime allows Docker-backed integration tests, prefer:

```bash
make validate-live
make validate-cypher-live
```

Before making load tests gating, add executable tests under `tests/load/` and a
stable target such as:

```bash
make load-test
```

## Current Audit Conclusion

Local validation is coherent for Python compilation, JSON schema validation,
YAML parsing, the no-agent-DB-import guard, and the full pytest suite. Docker
stabilization added a useful local live path through `validate-live` and
`docker-doctor`.

CI parity is incomplete because no checked-in CI workflow exists, the documented
CI template has drifted from the Makefile, SQL and Cypher validation reference
different source files across local and documented CI paths, Cypher validation
is not part of the main live validation gate, and load-test readiness is still
placeholder-only.
