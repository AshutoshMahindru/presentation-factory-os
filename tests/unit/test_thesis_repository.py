from uuid import uuid4

import pytest

from system.thesis_repository import ThesisRepository


pytestmark = pytest.mark.skip(reason="Requires a db_pool fixture or live Postgres test harness.")


class TestThesisRepository:
    @pytest.fixture
    def repo(self, db_pool):
        return ThesisRepository(db_pool)

    def test_create_and_get_latest(self, repo):
        pid = uuid4()
        v = repo.create_thesis_version(pid, 1, "AI will transform healthcare by 2028.")
        assert v.project_id == pid
        assert v.version_number == 1
        assert "healthcare" in v.thesis_statement

        latest = repo.get_latest_thesis(pid)
        assert latest is not None
        assert latest.id == v.id

    def test_convergence_score(self, repo):
        pid = uuid4()
        v = repo.create_thesis_version(pid, 1, "Test thesis.")
        repo.update_convergence_score(v.id, 0.95)

        latest = repo.get_latest_thesis(pid)
        assert latest.convergence_score == pytest.approx(0.95)

    def test_pillars(self, repo):
        pid = uuid4()
        v = repo.create_thesis_version(pid, 1, "Thesis with pillars.")
        p1 = repo.create_pillar(v.id, 0, "data", "Market grew 40%")
        p2 = repo.create_pillar(v.id, 1, "claim", "We will capture 30% share")

        pillars = repo.get_pillars(v.id)
        assert len(pillars) == 2
        assert pillars[0].pillar_index == 0
        assert pillars[1].pillar_type == "claim"

    def test_pillar_stress(self, repo):
        pid = uuid4()
        v = repo.create_thesis_version(pid, 1, "Thesis.")
        p = repo.create_pillar(v.id, 0, "financial", "Margin improves to 38%")
        repo.mark_pillar_stressed(p.id)

        stressed = repo.get_pillars(v.id)
        assert stressed[0].stress_status == "stressed"

    def test_research_loop(self, repo):
        pid = uuid4()
        loop = repo.start_research_loop(pid, 1)
        assert loop.status == "running"
        assert loop.loop_number == 1

        repo.finalize_research_loop(loop.id, 0.02, 12, "converged")
        updated = repo.get_loop(loop.id)
        assert updated.status == "converged"
        assert updated.sources_discovered_count == 12
        assert updated.completed_at is not None
