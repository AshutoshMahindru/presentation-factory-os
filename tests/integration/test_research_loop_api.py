from __future__ import annotations

from dataclasses import dataclass
from fastapi.testclient import TestClient
from uuid import UUID, uuid4

import api.workflow as workflow


client = TestClient(workflow.app)


@dataclass(frozen=True)
class FakeResearchLoop:
    id: UUID
    project_id: UUID
    loop_number: int
    convergence_delta: float | None
    sources_discovered_count: int
    status: str
    created_at: str
    completed_at: str | None


class FakeThesisRepository:
    def __init__(self) -> None:
        self.loops: dict[UUID, FakeResearchLoop] = {}

    def start_research_loop(self, project_id: UUID, loop_number: int) -> FakeResearchLoop:
        loop = FakeResearchLoop(
            id=uuid4(),
            project_id=project_id,
            loop_number=loop_number,
            convergence_delta=None,
            sources_discovered_count=0,
            status="running",
            created_at="2026-01-01T00:00:00Z",
            completed_at=None,
        )
        self.loops[loop.id] = loop
        return loop

    def finalize_research_loop(
        self,
        loop_id: UUID,
        convergence_delta: float,
        sources_discovered_count: int,
        status: str,
    ) -> None:
        loop = self.loops[loop_id]
        self.loops[loop_id] = FakeResearchLoop(
            id=loop.id,
            project_id=loop.project_id,
            loop_number=loop.loop_number,
            convergence_delta=convergence_delta,
            sources_discovered_count=sources_discovered_count,
            status=status,
            created_at=loop.created_at,
            completed_at="2026-01-01T00:01:00Z",
        )


class TestResearchLoopApi:
    def test_start_loop(self, monkeypatch):
        repository = FakeThesisRepository()
        monkeypatch.setattr(workflow, "create_thesis_repository", lambda: repository)

        payload = {"loop_number": 1, "sources_discovered_count": 5}
        resp = client.post(f"/projects/{uuid4()}/research-loops/start", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["loop_number"] == 1
        assert data["status"] == "running"

    def test_finalize_loop(self, monkeypatch):
        repository = FakeThesisRepository()
        monkeypatch.setattr(workflow, "create_thesis_repository", lambda: repository)

        # First start
        start = client.post(f"/projects/{uuid4()}/research-loops/start", json={"loop_number": 1})
        loop_id = start.json()["id"]

        payload = {
            "convergence_delta": 0.03,
            "sources_discovered_count": 12,
            "status": "converged",
        }
        resp = client.post(f"/projects/proj-1/research-loops/{loop_id}/finalize", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "converged"
        assert data["convergence_delta"] == 0.03
