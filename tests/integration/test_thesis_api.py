from __future__ import annotations

from dataclasses import dataclass
from fastapi.testclient import TestClient
from uuid import UUID, uuid4

import api.workflow as workflow


client = TestClient(workflow.app)


@dataclass(frozen=True)
class FakeThesisVersion:
    id: UUID
    project_id: UUID
    version_number: int
    thesis_statement: str
    convergence_score: float | None
    created_at: str


@dataclass(frozen=True)
class FakeThesisPillar:
    id: UUID
    thesis_version_id: UUID
    pillar_index: int
    pillar_type: str
    statement: str
    stress_status: str


class FakeThesisRepository:
    def __init__(self) -> None:
        self.versions_by_project: dict[UUID, list[FakeThesisVersion]] = {}
        self.pillars_by_version: dict[UUID, list[FakeThesisPillar]] = {}

    def create_thesis_version(
        self,
        project_id: UUID,
        version_number: int,
        thesis_statement: str,
    ) -> FakeThesisVersion:
        version = FakeThesisVersion(
            id=uuid4(),
            project_id=project_id,
            version_number=version_number,
            thesis_statement=thesis_statement,
            convergence_score=None,
            created_at="2026-01-01T00:00:00Z",
        )
        self.versions_by_project.setdefault(project_id, []).append(version)
        return version

    def get_latest_thesis(self, project_id: UUID) -> FakeThesisVersion | None:
        versions = self.versions_by_project.get(project_id, [])
        return versions[-1] if versions else None

    def create_pillar(
        self,
        thesis_version_id: UUID,
        pillar_index: int,
        pillar_type: str,
        statement: str,
    ) -> FakeThesisPillar:
        pillar = FakeThesisPillar(
            id=uuid4(),
            thesis_version_id=thesis_version_id,
            pillar_index=pillar_index,
            pillar_type=pillar_type,
            statement=statement,
            stress_status="unstressed",
        )
        self.pillars_by_version.setdefault(thesis_version_id, []).append(pillar)
        return pillar

    def get_pillars(self, thesis_version_id: UUID) -> list[FakeThesisPillar]:
        return self.pillars_by_version.get(thesis_version_id, [])


class TestThesisApi:
    def test_create_thesis_version(self, monkeypatch):
        repository = FakeThesisRepository()
        monkeypatch.setattr(workflow, "create_thesis_repository", lambda: repository)
        project_id = uuid4()

        payload = {
            "thesis_statement": "AI will transform healthcare by 2028.",
            "pillars": [
                {"pillar_index": 0, "pillar_type": "data", "statement": "Market $500B"},
                {"pillar_index": 1, "pillar_type": "claim", "statement": "Regulatory clarity emerging"},
            ]
        }
        resp = client.post(f"/projects/{project_id}/thesis-versions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["version_number"] == 1
        version_id = UUID(data["id"])
        assert repository.versions_by_project[project_id][0].thesis_statement == (
            "AI will transform healthcare by 2028."
        )
        assert [pillar.statement for pillar in repository.pillars_by_version[version_id]] == [
            "Market $500B",
            "Regulatory clarity emerging",
        ]

    def test_get_current_thesis(self, monkeypatch):
        repository = FakeThesisRepository()
        monkeypatch.setattr(workflow, "create_thesis_repository", lambda: repository)
        project_id = uuid4()

        # First create
        payload = {
            "thesis_statement": "Test.",
            "pillars": [{"pillar_index": 0, "pillar_type": "narrative", "statement": "Story."}]
        }
        client.post(f"/projects/{project_id}/thesis-versions", json=payload)

        resp = client.get(f"/projects/{project_id}/thesis-versions/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thesis_statement"] == "Test."
        assert len(data["pillars"]) == 1
        assert data["pillars"][0]["pillar_type"] == "narrative"
        assert data["pillars"][0]["stress_status"] == "unstressed"

    def test_no_thesis_returns_none(self, monkeypatch):
        repository = FakeThesisRepository()
        monkeypatch.setattr(workflow, "create_thesis_repository", lambda: repository)

        resp = client.get(f"/projects/{uuid4()}/thesis-versions/current")
        assert resp.status_code == 200
        assert resp.json() is None
