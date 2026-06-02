from retrieval_engine.router import classify_source_query, route_to_source_register


class TestRetrievalRouter:
    def test_classify_discovery(self):
        assert classify_source_query("Find sources about AI regulation") == "source_discovery"
        assert classify_source_query("Discover new market reports") == "source_discovery"
        assert classify_source_query("Register this PDF") == "source_discovery"

    def test_classify_lifecycle(self):
        assert classify_source_query("Retract source 123") == "source_lifecycle"
        assert classify_source_query("Check source status") == "source_lifecycle"
        assert classify_source_query("Archive old sources") == "source_lifecycle"

    def test_classify_general(self):
        assert classify_source_query("What is the thesis?") == "general"
        assert classify_source_query("Explain unit economics") == "general"

    def test_route_source_discovery(self):
        result = route_to_source_register("Find sources", {"project_id": "proj-1", "query": "AI"})
        assert result["mode"] == "source_register"
        assert result["status_filter"] == "active"

    def test_route_source_lifecycle(self):
        result = route_to_source_register("Retract source", {"project_id": "proj-1", "query": "old"})
        assert result["mode"] == "source_register"
        assert result["status_filter"] is None
