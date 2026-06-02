from __future__ import annotations

import json
import sys
from typing import Any

import pytest


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeUrlOpen:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    def __call__(self, request: Any, timeout: Any = None) -> _FakeResponse:  # type: ignore[no-untyped-def]
        self.calls.append((request.full_url, request.data, dict(request.headers)))
        return _FakeResponse({})


def test_workflow_client_post_sends_post_to_path() -> None:
    from agents.base_agent import WorkflowClient

    fake = _FakeUrlOpen()
    sys.modules["urllib.request"].urlopen = fake  # type: ignore[attr-defined]
    client = WorkflowClient(base_url="http://localhost:8000")
    client._post("/foo/bar", {"k": "v"})

    assert len(fake.calls) == 1
    url, body, headers = fake.calls[0]
    assert url == "http://localhost:8000/foo/bar"
    assert json.loads(body.decode("utf-8")) == {"k": "v"}
    assert headers.get("Content-type") == "application/json"
