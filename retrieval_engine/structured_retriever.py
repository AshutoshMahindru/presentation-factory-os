from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


# --- Step 104: Source Register search ---


def _source_matches_query(source: Mapping[str, Any], query: str | None) -> bool:
    if not query:
        return True
    needle = query.casefold()
    fields = (
        source.get("uri"),
        source.get("title"),
        source.get("source_type"),
        source.get("content_hash"),
    )
    return any(needle in str(value).casefold() for value in fields if value is not None)


def _source_result(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": source.get("id"),
        "project_id": source.get("project_id"),
        "uri": source.get("uri"),
        "title": source.get("title"),
        "source_type": source.get("source_type"),
        "content_hash": source.get("content_hash"),
        "status": source.get("status", "active"),
        "quality_score": source.get("quality_score", {}),
        "search_coverage": source.get("search_coverage", []),
    }


def search_source_register(
    project_id: str,
    query: str | None = None,
    status: str | None = "active",
    include_retracted: bool = False,
    limit: int = 20,
    sources: Iterable[Mapping[str, Any]] | None = None,
) -> dict:
    """Hybrid search over source_register by metadata and content hash."""
    # In production: this also queries Qdrant for semantic similarity.
    # For now, exact substring match on URI/title and content hash prefix.
    # NOTE: In real usage, pool is injected. The optional sources iterable
    # keeps the contract deterministic and unit-testable without a live DB.
    effective_status = None if include_retracted else status
    bounded_limit = max(0, limit)

    results = []
    for source in sources or ():
        if str(source.get("project_id")) != str(project_id):
            continue
        if (
            effective_status is not None
            and source.get("status", "active") != effective_status
        ):
            continue
        if not _source_matches_query(source, query):
            continue
        results.append(_source_result(source))
        if len(results) >= bounded_limit:
            break

    return {
        "mode": "source_register",
        "project_id": project_id,
        "query": query,
        "status_filter": effective_status,
        "limit": bounded_limit,
        "results": results,
        "count": len(results),
    }
