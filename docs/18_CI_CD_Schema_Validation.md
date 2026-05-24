# CI/CD Schema Validation

## GitHub Actions workflow

Create `.github/workflows/validate.yml`:

```yaml
name: validate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: pfos_test
          POSTGRES_USER: pfos
          POSTGRES_PASSWORD: pfos_test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U pfos -d pfos_test"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      neo4j:
        image: neo4j:5
        env:
          NEO4J_AUTH: neo4j/pfos_neo4j_password
        ports:
          - 7474:7474
          - 7687:7687

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install validation dependencies
        run: |
          python -m pip install --upgrade pip
          pip install datamodel-code-generator jsonschema pydantic psycopg2-binary neo4j pytest pyyaml

      - name: Generate pydantic models from JSON schemas
        run: |
          mkdir -p generated/schemas
          datamodel-codegen --input docs/06_SlideJobDefinition.schema.json --input-file-type jsonschema --output generated/schemas/slide_job_definition.py
          datamodel-codegen --input docs/07_StandardContextPayload.schema.json --input-file-type jsonschema --output generated/schemas/standard_context_payload.py
          datamodel-codegen --input docs/21_DesignTokens.schema.json --input-file-type jsonschema --output generated/schemas/design_tokens.py
          datamodel-codegen --input docs/22_AudienceProfile.schema.json --input-file-type jsonschema --output generated/schemas/audience_profile.py

      - name: Check generated schema drift
        run: |
          git diff --exit-code generated/schemas || (echo "Generated schemas are out of date. Run make codegen." && exit 1)

      - name: Validate JSON schemas
        run: |
          python - <<'PY'
          import json
          from jsonschema.validators import validator_for
          for path in ["docs/06_SlideJobDefinition.schema.json", "docs/07_StandardContextPayload.schema.json", "docs/21_DesignTokens.schema.json", "docs/22_AudienceProfile.schema.json"]:
              schema = json.load(open(path))
              cls = validator_for(schema)
              cls.check_schema(schema)
          PY

      - name: Validate YAML parses
        run: |
          python - <<'PY'
          import yaml, pathlib
          for path in pathlib.Path('docs').glob('*.yaml'):
              yaml.safe_load(path.read_text())
              print(f'parsed {path}')
          PY

      - name: Validate SQL against Postgres
        env:
          PGPASSWORD: pfos_test_password
        run: |
          psql -h localhost -U pfos -d pfos_test -f docs/04_Database_Schemas.sql

      - name: Validate Cypher against Neo4j
        env:
          NEO4J_PASSWORD: pfos_neo4j_password
        run: |
          for i in {1..20}; do
            cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" && break
            sleep 3
          done
          cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" --file docs/05_Evidence_Graph_Cypher.cypher

      - name: Enforce no raw DB imports in agents
        run: |
          python - <<'PY'
          from pathlib import Path
          banned = ["neo4j", "psycopg2", "asyncpg", "sqlalchemy", "qdrant_client", "pymongo", "redis"]
          failed = []
          for path in Path('agents').glob('**/*.py'):
              text = path.read_text()
              for item in banned:
                  if f'import {item}' in text or f'from {item}' in text:
                      failed.append((str(path), item))
          if failed:
              raise SystemExit(f'Raw DB imports found in agents: {failed}')
          PY

      - name: Run tests
        run: pytest

      - name: Required integration tests
        run: |
          pytest tests/integration/test_outbox_eventual_consistency.py
          pytest tests/integration/test_outbox_neo4j_failure_retry_backoff.py
          pytest tests/integration/test_source_retraction_cascade.py
          pytest tests/integration/test_agent_network_isolation.py
```

## Makefile targets

```makefile
.PHONY: codegen test validate validate-ci validate-json validate-yaml validate-sql validate-cypher no-agent-db-imports outbox-integration-test load-test

codegen:
	mkdir -p generated/schemas
	datamodel-codegen --input docs/06_SlideJobDefinition.schema.json --input-file-type jsonschema --output generated/schemas/slide_job_definition.py
	datamodel-codegen --input docs/07_StandardContextPayload.schema.json --input-file-type jsonschema --output generated/schemas/standard_context_payload.py
	datamodel-codegen --input docs/21_DesignTokens.schema.json --input-file-type jsonschema --output generated/schemas/design_tokens.py
	datamodel-codegen --input docs/22_AudienceProfile.schema.json --input-file-type jsonschema --output generated/schemas/audience_profile.py

test:
	pytest

validate: validate-json validate-yaml validate-sql no-agent-db-imports test
	@echo "Local validate excludes validate-cypher because Neo4j must be running. Use make validate-ci inside CI or after docker compose is up."

validate-ci: validate-json validate-yaml validate-sql validate-cypher no-agent-db-imports test outbox-integration-test

# Local validation intentionally excludes validate-cypher because it requires a running Neo4j container.
# CI runs validate-cypher against the Neo4j service container. Use validate-ci for parity.

validate-json:
	python scripts/validate_json_schemas.py

validate-yaml:
	python scripts/validate_yaml.py

validate-sql:
	psql "$${DATABASE_URL}" -f docs/04_Database_Schemas.sql

no-agent-db-imports:
	python scripts/check_no_agent_db_imports.py

validate-cypher:
	cat infra/neo4j/constraints.cypher | cypher-shell -u neo4j -p $${NEO4J_PASSWORD:-presentation_factory_password} --file -

outbox-integration-test:
	pytest tests/integration/test_outbox_eventual_consistency.py tests/integration/test_outbox_neo4j_failure_retry_backoff.py tests/integration/test_agent_network_isolation.py

load-test:
	pytest tests/load/test_outbox_queue_load.py tests/load/test_source_retraction_queue_load.py
```

## Rules

1. Schema changes require regenerated `.py` models.
2. YAML changes require cross-reference update in `20_Cross_Reference_Matrix.md`.
3. CI fails on generated-code drift.
4. CI fails on invalid SQL.
5. CI fails on invalid JSON Schema.
6. CI fails on YAML parse errors.
7. CI fails on invalid Cypher constraints.
8. CI fails if agents import raw database clients.
9. CI fails if phase names diverge across SQL, state machine, approval ledger, and implementation tests.


## Additional v3.2.4 Consistency Tests

Unit tests live under `tests/unit/`. Integration tests live under `tests/integration/`. Load tests live under `tests/load/`. Do not mix these paths across docs.

- `tests/integration/test_outbox_eventual_consistency.py`: inserts a Postgres event plus outbox row, simulates Neo4j retry, and asserts phase transition is blocked until processed.
- `tests/integration/test_outbox_neo4j_failure_retry_backoff.py`: stops or blocks Neo4j, verifies outbox `error_count` increments, retry backoff follows `[5, 30, 120, 300, 600]`, then restores Neo4j and verifies eventual processing.
- `tests/integration/test_agent_network_isolation.py`: executes connection attempts from inside `agent-service` to `postgres:5432`, `neo4j:7687`, and `qdrant:6333`; each attempt must fail by DNS resolution failure or connection timeout. The assertion must inspect TCP-level failure, not merely absence of database environment variables. The canonical command is `docker compose exec -T agent-service sh -lc "nc -zvw2 postgres 5432"`, repeated for `neo4j 7687` and `qdrant 6333`, expecting non-zero exit code with DNS resolution failure, connection timeout, or network unreachable.
- `tests/integration/test_retreat_archives_downstream_drafts.py`: retreats a project and asserts downstream artifacts become `stale_due_to_retreat`, not deleted.
- `tests/integration/test_financial_ingestion_requires_ast.py`: rejects Excel-origin financial cells without allow-listed parser provenance.
- `tests/integration/test_source_retraction_cascade.py`: injects 500 supported claims and asserts async queued cascade uses batches of 50 and blocks affected projects immediately.
- `tests/load/test_outbox_queue_load.py`: validates 50 concurrent outbox items drain within 60 seconds after Neo4j recovers, with zero failed rows.
- `tests/load/test_source_retraction_queue_load.py`: validates 100 concurrent retractions with up to 500 claims each, batch size 50, initial block within 5 seconds, and standard cascade SLA of 30 seconds for each 500-claim cascade.

CI must parse `docs/23_Financial_Ingestion_Pipeline.yaml` during YAML validation and include it in cross-reference drift checks.

- Phase-name enum changes require synchronized updates to `04_Database_Schemas.sql`, `08_StateMachine_Spec.yaml`, generated code enums, API validators, and UI phase labels.
- Outbox integration tests must simulate Neo4j failure, verify retry/backoff, and confirm eventual processing before affected phase transitions unblock.

#### Canonical network isolation test body

```python
# tests/integration/test_agent_network_isolation.py
import subprocess

BLOCKED_TARGETS = [("postgres", 5432), ("neo4j", 7687), ("qdrant", 6333)]


def run_agent_nc(host: str, port: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "compose", "exec", "-T", "agent-service",
            "sh", "-lc", f"nc -zvw2 {host} {port}",
        ],
        text=True,
        capture_output=True,
        timeout=8,
        check=False,
    )


def test_agent_service_cannot_open_tcp_connections_to_data_stores():
    for host, port in BLOCKED_TARGETS:
        result = run_agent_nc(host, port)
        combined = (result.stdout + result.stderr).lower()
        assert result.returncode != 0, f"agent-service unexpectedly connected to {host}:{port}"
        assert any(
            marker in combined
            for marker in [
                "bad address",
                "name or service not known",
                "temporary failure in name resolution",
                "timed out",
                "network unreachable",
                "connection refused",
            ]
        ), combined
```
