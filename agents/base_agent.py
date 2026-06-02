from __future__ import annotations

import json
import urllib.request
from typing import Any


class BaseAgent:
    @staticmethod
    def _validate_json_schema(data: Any, schema: dict[str, Any]) -> None:
        try:
            from jsonschema import validate, ValidationError
            validate(instance=data, schema=schema)
        except ImportError:
            if not isinstance(data, dict):
                raise ValueError("Data must be a dict")
            if "sources" not in data:
                raise ValueError("Missing 'sources' key")
            if not isinstance(data["sources"], list):
                raise ValueError("'sources' must be a list")
            for src in data["sources"]:
                if not isinstance(src, dict):
                    raise ValueError("Each source must be a dict")
                if "uri" not in src or not isinstance(src["uri"], str):
                    raise ValueError("Each source must have string 'uri'")
                if "source_type" not in src:
                    raise ValueError("Each source must have 'source_type'")


class WorkflowClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def create_source(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/projects/{project_id}/sources"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


class LLMClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000) -> str:
        payload = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]



    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def create_thesis_version(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/projects/{project_id}/thesis-versions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_current_thesis(self, project_id: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/projects/{project_id}/thesis-versions/current"
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

