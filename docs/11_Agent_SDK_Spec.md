# Agent SDK Spec

## Core rule

Agents hold no database credentials.

Agents are not allowed to import database drivers, instantiate graph clients, read `.env` database credentials, or write directly to Postgres, Neo4j, or Qdrant. Agents operate through four HTTP clients only; the fourth is a narrow workflow client for provenance and metrics writes, not database access.

## Allowed clients

| Client | Port | Purpose |
|---|---:|---|
| `RetrievalClient` | 8002 | Query the unified retrieval engine and receive standard context payloads |
| `ToolClient` | 8003 | Generate charts, diagrams, tables, exports, screenshots, and degraded outputs |
| `LLMClient` | 4000 | Route local and remote model calls through LiteLLM |
| `WorkflowClient` | 8000 | Write provenance and metrics through deterministic workflow endpoints only |

## Python pseudocode

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional
import os
import httpx

@dataclass
class AgentSDK:
    retrieval_base_url: str = "http://retrieval-engine:8002"
    tool_base_url: str = "http://tool-server:8003"
    llm_base_url: str = "http://litellm-proxy:4000"
    workflow_base_url: str = "http://workflow-service:8000"
    timeout_seconds: int = 120

    def retrieve(self, project_id: str, query: str, mode_hint: Optional[str] = None) -> Dict[str, Any]:
        payload = {"project_id": project_id, "query": query, "mode_hint": mode_hint}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.retrieval_base_url}/retrieve", json=payload)
            response.raise_for_status()
            return response.json()

    def call_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.tool_base_url}/tools/{tool_name}", json=payload)
            response.raise_for_status()
            return response.json()

    def generate(self, model: str, messages: list[dict], temperature: float = 0.0) -> Dict[str, Any]:
        payload = {"model": model, "messages": messages, "temperature": temperature}
        master_key = os.environ.get("LITELLM_MASTER_KEY")
        if not master_key:
            raise RuntimeError("LITELLM_MASTER_KEY must be injected into the agent container.")
        headers = {"Authorization": f"Bearer {master_key}"}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.llm_base_url}/v1/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    def write_provenance(self, project_id: str, entity_type: str, entity_id: str, action: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "project_id": project_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "metadata": metadata,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.workflow_base_url}/provenance", json=payload)
            response.raise_for_status()
            return response.json()

    def log_metric(self, name: str, value: float, labels: Dict[str, str]) -> None:
        payload = {"name": name, "value": value, "labels": labels}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.workflow_base_url}/metrics", json=payload)
            response.raise_for_status()
```

## Enforcement

### CI import ban

CI fails if any file in `agents/` imports raw database clients.

Banned imports:

```text
neo4j
psycopg2
asyncpg
sqlalchemy
qdrant_client
pymongo
redis
```

A simple enforcement test:

```python
from pathlib import Path

BANNED = ["neo4j", "psycopg2", "asyncpg", "sqlalchemy", "qdrant_client", "pymongo", "redis"]

def test_agents_do_not_import_raw_db_clients():
    for path in Path("agents").glob("**/*.py"):
        text = path.read_text()
        for banned in BANNED:
            assert f"import {banned}" not in text
            assert f"from {banned}" not in text
```

### Network policies

Docker network policies prevent agent containers from reaching Postgres, Neo4j, or Qdrant hostnames. Agent traffic is allowed only to:

```text
retrieval-engine:8002
tool-server:8003
litellm-proxy:4000
workflow-service:8000
```

### Credential policy

Database URLs must exist only in infrastructure and service containers that own deterministic logic. Agent containers receive no `POSTGRES_URL`, `NEO4J_URI`, or `QDRANT_URL` environment variables.


## Financial Ingestion Boundary

The financial agent may not call `pandas.read_excel()`, `xlwings`, or workbook parsers directly. Excel ingestion must go through `ToolClient.call_tool("parse_excel_ast", ...)`, which invokes `POST /tools/parse_excel_ast` on the tool-server. The tool-server emits deterministic cell graph JSON containing formulas, values, dependencies, workbook hash, parser name, and parser version. LLMs may suggest labels and scenario tags only after this deterministic parser output exists.

## Infrastructure-level database isolation

The DB-import ban is necessary but not sufficient. `16_Docker_Compose_Complete.yaml` also enforces the same boundary at network level:

- `agent-service` attaches only to `pfos_agent_runtime`.
- Postgres, Neo4j, and Qdrant attach to `pfos_data` and are not present on `pfos_agent_runtime`.
- Agents may reach only `workflow-service:8000`, `retrieval-engine:8002`, `tool-server:8003`, and `litellm-proxy:4000` by Docker service name.
- CI must include `tests/integration/test_agent_network_isolation.py` to verify that `agent-service` cannot resolve or connect to `postgres`, `neo4j`, or `qdrant`.
