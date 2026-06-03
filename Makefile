.PHONY: compile test no-agent-db-imports codegen-phase-enums validate validate-python validate-ui validate-json validate-yaml validate-sql-drift validate-sql-canonical validate-phase-enums smoke-source-lifecycle-outbox docker-ps docker-up docker-down docker-reset-dev docker-doctor validate-live validate-sql-live validate-cypher-live

PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest
PYTHON_SHIM_DIR ?= /tmp/pfos-python-shim
COMPOSE_PROJECT_NAME ?= pfos-dev
COMPOSE_FILE ?= docker-compose.apps.yaml
DOCKER_COMPOSE ?= docker compose -p $(COMPOSE_PROJECT_NAME) -f $(COMPOSE_FILE)
DOCKER_SERVICES ?= postgres neo4j qdrant workflow-service retrieval-engine tool-server agent-service

compile:
	$(PYTHON) -m compileall system evidence_graph retrieval_engine financial_model agents tool_server jobs api

test:
	mkdir -p "$(PYTHON_SHIM_DIR)"
	ln -sf "$$(command -v $(PYTHON))" "$(PYTHON_SHIM_DIR)/python"
	COMPOSE_PROJECT_NAME="$(COMPOSE_PROJECT_NAME)" PATH="$(PYTHON_SHIM_DIR):$$PATH" $(PYTEST)

no-agent-db-imports:
	$(PYTHON) scripts/check_no_agent_db_imports.py

codegen-phase-enums:
	$(PYTHON) scripts/generate_phase_enums.py

validate-phase-enums:
	$(PYTHON) scripts/generate_phase_enums.py --check

smoke-source-lifecycle-outbox:
	$(PYTHON) scripts/source_lifecycle_outbox_smoke.py

validate-json:
	$(PYTHON) scripts/validate_json_schemas.py

validate-yaml:
	$(PYTHON) scripts/validate_yaml.py

validate-sql-drift:
	$(PYTHON) scripts/check_postgres_schema_drift.py

validate-sql-canonical:
	$(PYTHON) scripts/check_sql_canonical.py

validate-python: compile validate-json validate-yaml validate-sql-drift validate-sql-canonical validate-phase-enums no-agent-db-imports test

validate-ui:
	npm ci
	npm --workspace ui exec playwright install chromium
	npm --workspace ui run validate

validate: validate-python validate-ui

docker-ps:
	$(DOCKER_COMPOSE) ps

docker-up:
	$(DOCKER_COMPOSE) up -d $(DOCKER_SERVICES)

docker-down:
	$(DOCKER_COMPOSE) down --remove-orphans

docker-reset-dev:
	$(DOCKER_COMPOSE) down --remove-orphans --volumes
	$(DOCKER_COMPOSE) up -d $(DOCKER_SERVICES)
	$(MAKE) validate-sql-live

docker-doctor:
	$(PYTHON) scripts/check_docker_env.py --compose-project-name "$(COMPOSE_PROJECT_NAME)" --compose-file "$(COMPOSE_FILE)"

validate-live: docker-up validate-sql-live docker-doctor
	PFOS_RUN_LIVE_TESTS=1 $(MAKE) validate

validate-sql-live:
	$(DOCKER_COMPOSE) exec -T postgres psql -U pfos -d pfos -f infra/postgres/init/001_schema.sql
	$(DOCKER_COMPOSE) cp infra/postgres/init/001_schema.sql postgres:/tmp/001_schema.sql
	$(DOCKER_COMPOSE) exec -T postgres sh -lc 'for i in $$(seq 1 30); do pg_isready -U pfos -d pfos >/dev/null 2>&1 && exit 0; sleep 1; done; pg_isready -U pfos -d pfos'
	$(DOCKER_COMPOSE) exec -T postgres psql -U pfos -d pfos -f /tmp/001_schema.sql


validate-cypher-live:
	$(DOCKER_COMPOSE) exec -T neo4j cypher-shell -u neo4j -p pfos_neo4j_password < tests/cypher/validate_constraints.cypher
	$(DOCKER_COMPOSE) cp infra/neo4j/constraints.cypher neo4j:/tmp/constraints.cypher
	$(DOCKER_COMPOSE) exec -T neo4j cypher-shell -u neo4j -p pfos_neo4j_password --file /tmp/constraints.cypher
