import pytest
from fastapi.testclient import TestClient

# Import would vary based on actual app structure
# Stub: assumes api.workflow exports 'app'


class TestThesisApi:
    def test_create_thesis_version(self, client: TestClient):
        payload = {
            "thesis_statement": "AI will transform healthcare by 2028.",
            "pillars": [
                {"pillar_index": 0, "pillar_type": "data", "statement": "Market $500B"},
                {"pillar_index": 1, "pillar_type": "claim", "statement": "Regulatory clarity emerging"},
            ]
        }
        resp = client.post("/projects/proj-1/thesis-versions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["version_number"] == 1

    def test_get_current_thesis(self, client: TestClient):
        # First create
        payload = {
            "thesis_statement": "Test.",
            "pillars": [{"pillar_index": 0, "pillar_type": "narrative", "statement": "Story."}]
        }
        client.post("/projects/proj-2/thesis-versions", json=payload)

        resp = client.get("/projects/proj-2/thesis-versions/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thesis_statement"] == "Test."
        assert len(data["pillars"]) == 1

    def test_no_thesis_returns_none(self, client: TestClient):
        resp = client.get("/projects/proj-999/thesis-versions/current")
        assert resp.status_code == 200
        assert resp.json() is None
