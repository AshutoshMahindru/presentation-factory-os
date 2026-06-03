from retrieval_engine.structured_retriever import search_source_register


SOURCES = [
    {
        "id": "src-1",
        "project_id": "proj-1",
        "uri": "https://example.com/ai-market.pdf",
        "title": "AI Market Report",
        "source_type": "pdf",
        "content_hash": "abc123",
        "status": "active",
        "quality_score": {"authority": 0.9},
        "search_coverage": [{"thesis_version_id": "thesis-1", "pillar_ids": ["pillar-1"]}],
    },
    {
        "id": "src-2",
        "project_id": "proj-1",
        "uri": "https://example.com/old-market",
        "title": "Retracted Market Note",
        "source_type": "web",
        "content_hash": "def456",
        "status": "retracted",
    },
    {
        "id": "src-3",
        "project_id": "proj-2",
        "uri": "https://example.com/ai-market-other",
        "title": "Other Project",
        "source_type": "web",
        "content_hash": "ghi789",
        "status": "active",
    },
]


class TestStructuredRetriever:
    def test_search_source_register_returns_dict(self):
        result = search_source_register("proj-1", query="test", status="active")
        assert isinstance(result, dict)
        assert result["mode"] == "source_register"
        assert result["project_id"] == "proj-1"
        assert result["status_filter"] == "active"
        assert "results" in result
        assert "count" in result

    def test_source_register_with_retracted(self):
        result = search_source_register("proj-1", query="old", include_retracted=True)
        assert result["status_filter"] is None  # all statuses when include_retracted

    def test_source_register_no_retracted(self):
        result = search_source_register("proj-1", query="new", include_retracted=False)
        assert result["status_filter"] == "active"

    def test_search_source_register_filters_project_status_and_query(self):
        result = search_source_register(
            "proj-1",
            query="market",
            status="active",
            sources=SOURCES,
        )

        assert result["count"] == 1
        assert result["results"][0]["id"] == "src-1"
        assert result["results"][0]["quality_score"] == {"authority": 0.9}
        assert result["results"][0]["search_coverage"] == [
            {"thesis_version_id": "thesis-1", "pillar_ids": ["pillar-1"]}
        ]

    def test_search_source_register_include_retracted_searches_all_statuses(self):
        result = search_source_register(
            "proj-1",
            query="market",
            include_retracted=True,
            sources=SOURCES,
        )

        assert result["status_filter"] is None
        assert [item["id"] for item in result["results"]] == ["src-1", "src-2"]

    def test_search_source_register_applies_limit_after_filtering(self):
        result = search_source_register(
            "proj-1",
            query="market",
            include_retracted=True,
            limit=1,
            sources=SOURCES,
        )

        assert result["limit"] == 1
        assert result["count"] == 1
        assert [item["id"] for item in result["results"]] == ["src-1"]
