from retrieval_engine.structured_retriever import search_source_register


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
