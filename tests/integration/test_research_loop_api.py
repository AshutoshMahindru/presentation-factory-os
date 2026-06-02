import pytest
from fastapi.testclient import TestClient

# Stub: assumes api.workflow exports app


class TestResearchLoopApi:
    def test_start_loop(self, client: TestClient):
        payload = {"loop_number": 1, "sources_discovered_count": 5}
        resp = client.post("/projects/proj-1/research-loops/start", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["loop_number"] == 1
        assert data["status"] == "running"

    def test_finalize_loop(self, client: TestClient):
        # First start
        start = client.post("/projects/proj-1/research-loops/start", json={"loop_number": 1})
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
