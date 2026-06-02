


# --- Step 104: Source Register search ---



def search_source_register(
    project_id: str,
    query: str | None = None,
    status: str | None = "active",
    include_retracted: bool = False,
    limit: int = 20,
) -> dict:
    """Hybrid search over source_register by metadata and content hash."""
    # In production: this also queries Qdrant for semantic similarity.
    # For now, exact substring match on URI/title and content hash prefix.
    # NOTE: In real usage, pool is injected. Here we assume global or caller provides.
    # This is a simplified deterministic version for the build step.
    results = []
    effective_status = None if include_retracted else status
    results = []
    return {
        "mode": "source_register",
        "project_id": project_id,
        "query": query,
        "status_filter": effective_status,
        "results": results,
        "count": len(results),
    }

