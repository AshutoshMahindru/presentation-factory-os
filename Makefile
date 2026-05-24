.PHONY: compile test no-agent-db-imports validate validate-json validate-yaml

PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest
PYTHON_SHIM_DIR ?= /tmp/pfos-python-shim

compile:
	$(PYTHON) -m compileall system evidence_graph retrieval_engine financial_model agents tool_server jobs api

test:
	mkdir -p "$(PYTHON_SHIM_DIR)"
	ln -sf "$$(command -v $(PYTHON))" "$(PYTHON_SHIM_DIR)/python"
	PATH="$(PYTHON_SHIM_DIR):$$PATH" $(PYTEST)

no-agent-db-imports:
	$(PYTHON) scripts/check_no_agent_db_imports.py

validate-json:
	$(PYTHON) scripts/validate_json_schemas.py

validate-yaml:
	$(PYTHON) scripts/validate_yaml.py

validate: compile validate-json validate-yaml no-agent-db-imports test


validate-sql-live:
	docker cp infra/postgres/init/001_schema.sql pfos-postgres-dev:/tmp/001_schema.sql
	docker compose -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -f /tmp/001_schema.sql


validate-cypher-live:
	docker cp infra/neo4j/constraints.cypher pfos-neo4j-dev:/tmp/constraints.cypher
	docker compose -f docker-compose.apps.yaml exec -T neo4j cypher-shell -u neo4j -p pfos_neo4j_password --file /tmp/constraints.cypher
