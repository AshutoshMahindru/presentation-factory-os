from uuid import uuid4

import pytest

from system.source_register_repository import SourceRegisterRepository


class TestSourceRegisterRepository:
    @pytest.fixture
    def repo(self, db_pool):
        return SourceRegisterRepository(db_pool)

    def test_create_and_get(self, repo):
        pid = uuid4()
        row = repo.create(
            project_id=pid,
            uri="https://example.com/report.pdf",
            title="Annual Report",
            source_type="pdf",
            normalized_text="The revenue grew by 40% in Q3.",
            quality_score={"authority": 0.9, "recency": 0.8},
        )
        assert row.project_id == pid
        assert row.uri == "https://example.com/report.pdf"
        assert row.source_type == "pdf"
        assert row.status == "active"
        assert row.quality_score == {"authority": 0.9, "recency": 0.8}

        fetched = repo.get(row.id)
        assert fetched is not None
        assert fetched.content_hash == row.content_hash

    def test_content_hash_deduplication(self, repo):
        pid = uuid4()
        text = "Same content."
        r1 = repo.create(pid, "http://a.com", "A", "web", text)
        r2 = repo.create(pid, "http://b.com", "B", "web", text)
        assert r1.content_hash == r2.content_hash
        assert r1.id == r2.id

    def test_list_by_project(self, repo):
        pid = uuid4()
        repo.create(pid, "http://a.com", "A", "web", "text a")
        repo.create(pid, "http://b.com", "B", "web", "text b")
        rows = repo.list_by_project(pid)
        assert len(rows) == 2

    def test_update_search_coverage(self, repo):
        pid = uuid4()
        row = repo.create(pid, "http://a.com", "A", "web", "text a")
        thesis = uuid4()
        pillars = [uuid4(), uuid4()]
        repo.update_search_coverage(row.id, thesis, pillars)

        updated = repo.get(row.id)
        assert len(updated.search_coverage) == 1
        assert updated.search_coverage[0]["thesis_version_id"] == str(thesis)

    def test_retraction(self, repo):
        pid = uuid4()
        row = repo.create(pid, "http://a.com", "A", "web", "text a")
        repo.mark_retracted(row.id)

        updated = repo.get(row.id)
        assert updated.status == "retracted"
