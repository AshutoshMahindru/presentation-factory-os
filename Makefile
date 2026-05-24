.PHONY: compile test no-agent-db-imports validate validate-json validate-yaml

compile:
	python -m compileall system evidence_graph retrieval_engine financial_model agents tool_server jobs api

test:
	pytest

no-agent-db-imports:
	python scripts/check_no_agent_db_imports.py

validate-json:
	python scripts/validate_json_schemas.py

validate-yaml:
	python scripts/validate_yaml.py

validate: compile validate-json validate-yaml no-agent-db-imports test


validate-sql-live:
	docker cp infra/postgres/init/001_schema.sql pfos-postgres-dev:/tmp/001_schema.sql
	docker compose -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -f /tmp/001_schema.sql
