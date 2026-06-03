from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

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


def test_thesis_evolution_creates_incrementing_versions(monkeypatch) -> None:
    repository = FakeThesisRepository()
    monkeypatch.setattr(workflow, "create_thesis_repository", lambda: repository)
    project_id = uuid4()

    first = client.post(
        f"/projects/{project_id}/thesis-versions",
        json={
            "thesis_statement": "Initial thesis.",
            "pillars": [
                {
                    "pillar_index": 0,
                    "pillar_type": "claim",
                    "statement": "Initial claim.",
                }
            ],
        },
    )
    second = client.post(
        f"/projects/{project_id}/thesis-versions",
        json={
            "thesis_statement": "Refined thesis.",
            "pillars": [
                {
                    "pillar_index": 0,
                    "pillar_type": "claim",
                    "statement": "Refined claim.",
                }
            ],
        },
    )

    assert first.status_code == 200
    assert first.json()["version_number"] == 1
    assert second.status_code == 200
    assert second.json()["version_number"] == 2

    current = client.get(f"/projects/{project_id}/thesis-versions/current")
    assert current.status_code == 200
    assert current.json()["version_number"] == 2
    assert current.json()["thesis_statement"] == "Refined thesis."


def test_thesis_evolution_rejects_malformed_pillar_payload(monkeypatch) -> None:
    repository = FakeThesisRepository()
    monkeypatch.setattr(workflow, "create_thesis_repository", lambda: repository)

    response = client.post(
        f"/projects/{uuid4()}/thesis-versions",
        json={
            "thesis_statement": "Malformed thesis.",
            "pillars": [{"pillar_index": 0, "pillar_type": "claim"}],
        },
    )

    assert response.status_code == 422
    assert repository.versions_by_project == {}
