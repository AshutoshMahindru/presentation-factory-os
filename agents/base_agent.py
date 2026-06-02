from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class BaseAgent:
    @staticmethod
    def _validate_json_schema(data: Any, schema: dict[str, Any]) -> None:
        try:
            from jsonschema import validate
        except ImportError:
            BaseAgent._validate_minimal_schema(data)
            return

        validate(instance=data, schema=schema)

    @staticmethod
    def _validate_minimal_schema(data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("Data must be a dict")
        if "sources" in data and not isinstance(data["sources"], list):
            raise ValueError("'sources' must be a list")
        if "findings" in data and not isinstance(data["findings"], list):
            raise ValueError("'findings' must be a list")


class WorkflowClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def _get(self, path: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", path, None)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def create_source(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/projects/{project_id}/sources", payload)

    def create_thesis_version(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._post(f"/projects/{project_id}/thesis-versions", payload)

    def get_current_thesis(self, project_id: str) -> dict[str, Any] | None:
        return self._get(f"/projects/{project_id}/thesis-versions/current")

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}


class LLMClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def complete(
        self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000
    ) -> str:
        payload = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
