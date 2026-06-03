from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.workflow as workflow


client = TestClient(workflow.app)


class FakeProjectRepository:
    def __init__(self, project=None) -> None:
        self.project = project

    def get_project(self, project_id: str):
        return self.project


def test_standalone_chat_presentation_endpoint_returns_preview() -> None:
    response = client.post(
        "/presentations/from-chat",
        json={
            "content": "Create a CFO presentation for PFOS unit economics.",
            "project_context": {
                "source_refs": ["source_finance"],
                "decision_required": "Approve economics review.",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["brief"]["audience"] == "cfo"
    assert payload["export_gate"]["export_allowed"] is True
    assert payload["web_preview"]["mime_type"] == "text/html"
    assert payload["export_metadata"]["formats"] == ["pptx", "pdf", "web", "speaker_notes"]


def test_project_chat_presentation_endpoint_injects_project_context(monkeypatch) -> None:
    monkeypatch.setattr(
        workflow,
        "project_repository",
        FakeProjectRepository(
            SimpleNamespace(
                project_id="project-1",
                audience="board",
                decision_required="Approve launch.",
            )
        ),
    )

    response = client.post(
        "/projects/project-1/presentations/from-chat",
        json={
            "content": "Make a presentation about PFOS launch readiness.",
            "project_context": {"source_refs": ["source_launch"]},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["brief"]["audience"] == "board"
    assert payload["brief"]["objective"] == "Approve launch."
    assert payload["evidence_gaps"] == []


def test_project_chat_presentation_endpoint_returns_404_for_missing_project(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository(None))

    response = client.post(
        "/projects/missing/presentations/from-chat",
        json={"content": "Create a board deck."},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {"error": "project_not_found"}
