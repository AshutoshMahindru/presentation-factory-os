from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


# Type alias for a Neo4j query runner. The implementation is provided by the
# application; tests inject a fake. It must return an iterable of row mappings.
CypherRunner = Callable[[str, dict[str, Any]], Iterable[dict[str, Any]]]


VALID_PILLAR_TYPES: frozenset[str] = frozenset(
    {"claim", "data", "objection", "narrative", "financial"}
)


@dataclass(frozen=True)
class PillarLink:
    """Result of linking a single pillar to its supporting sources."""

    pillar_id: str
    pillar_index: int
    pillar_type: str
    statement: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeepReadResult:
    """Aggregate result of a deep_read_sources_for_pillars call."""

    project_id: str
    thesis_version_id: str
    pillar_links: tuple[PillarLink, ...] = ()

    def pillar_ids_with_no_sources(self) -> tuple[str, ...]:
        return tuple(p.pillar_id for p in self.pillar_links if not p.source_ids)

    def total_sources(self) -> int:
        return sum(len(p.source_ids) for p in self.pillar_links)


def _validate_pillar_type(pillar_type: str) -> None:
    if pillar_type not in VALID_PILLAR_TYPES:
        raise ValueError(
            f"Unsupported pillar_type {pillar_type!r}; "
            f"expected one of {sorted(VALID_PILLAR_TYPES)}"
        )


def upsert_pillar(
    runner: CypherRunner,
    *,
    project_id: str,
    thesis_version_id: str,
    pillar_id: str,
    pillar_index: int,
    pillar_type: str,
    statement: str,
) -> str:
    """Project a Postgres thesis_pillar into Neo4j as a (:Pillar) node.

    Idempotent: re-running updates statement/pillar_type.
    Returns the pillar id on success.
    """
    _validate_pillar_type(pillar_type)
    query = """
    MERGE (p:Project {id: $project_id})
    ON CREATE SET p.created_at = datetime()
    MERGE (pl:Pillar {id: $pillar_id})
    ON CREATE SET pl.created_at = datetime()
    SET pl.project_id = $project_id,
        pl.thesis_version_id = $thesis_version_id,
        pl.pillar_index = $pillar_index,
        pl.statement = $statement,
        pl.pillar_type = $pillar_type
    WITH pl
    MATCH (p:Project {id: $project_id})
    MERGE (p)-[:HAS_PILLAR]->(pl)
    RETURN pl.id AS pillar_id
    """
    rows = list(
        runner(
            query,
            {
                "project_id": project_id,
                "thesis_version_id": thesis_version_id,
                "pillar_id": pillar_id,
                "pillar_index": pillar_index,
                "pillar_type": pillar_type,
                "statement": statement,
            },
        )
    )
    if not rows:
        raise RuntimeError("upsert_pillar: Neo4j returned no rows")
    return str(rows[0]["pillar_id"])


def link_claim_to_pillar(
    runner: CypherRunner,
    *,
    project_id: str,
    claim_id: str,
    pillar_id: str,
    confidence: float = 1.0,
) -> None:
    """Create a Claim -[SUPPORTS_PILLAR]-> Pillar edge. Idempotent.

    Confidence is the agent-assigned score in [0.0, 1.0]. The linker only
    stores it; the deep_read step is read-only on this edge.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0.0, 1.0], got {confidence!r}")
    query = """
    MATCH (c:Claim {id: $claim_id, project_id: $project_id})
    MATCH (pl:Pillar {id: $pillar_id, project_id: $project_id})
    MERGE (c)-[r:SUPPORTS_PILLAR {pillar_id: $pillar_id}]->(pl)
    ON CREATE SET r.created_at = datetime(), r.confidence = $confidence
    ON MATCH SET r.confidence = $confidence
    RETURN c.id AS claim_id, pl.id AS pillar_id
    """
    rows = list(
        runner(
            query,
            {
                "project_id": project_id,
                "claim_id": claim_id,
                "pillar_id": pillar_id,
                "confidence": confidence,
            },
        )
    )
    if not rows:
        raise ValueError(
            f"link_claim_to_pillar: no Claim {claim_id!r} and/or Pillar {pillar_id!r} "
            f"for project {project_id!r}"
        )


def list_sources_for_pillar(
    runner: CypherRunner,
    *,
    project_id: str,
    pillar_id: str,
) -> tuple[str, ...]:
    """Return distinct active source ids that ultimately back a pillar.

    Traverses Pillar <-SUPPORTS_PILLAR- Claim -SUPPORTED_BY-> Source (active).
    Returns an empty tuple if the pillar has no supporting claims or no
    active sources.
    """
    query = """
    MATCH (pl:Pillar {id: $pillar_id, project_id: $project_id})
    MATCH (pl)<-[sp:SUPPORTS_PILLAR]-(c:Claim)
    MATCH (c)-[sb:SUPPORTED_BY]->(s:Source {status: 'active'})
    RETURN DISTINCT s.id AS source_id
    ORDER BY source_id
    """
    rows = runner(
        query,
        {"project_id": project_id, "pillar_id": pillar_id},
    )
    return tuple(str(r["source_id"]) for r in rows)


def _fetch_pillars_from_postgres(
    pool: ConnectionPool,
    thesis_version_id: str | UUID,
) -> list[dict[str, Any]]:
    """Read pillars for a thesis version, ordered by pillar_index."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text AS id, pillar_index, pillar_type, statement
                FROM thesis_pillars
                WHERE thesis_version_id = %s
                ORDER BY pillar_index ASC
                """,
                (str(thesis_version_id),),
            )
            return list(cur.fetchall())


def _coerce_uuid(value: str | UUID) -> UUID:
    """Accept either a UUID instance or a canonical string and return a UUID.

    The Neo4j side of the linker works in string ids (cypher params), but
    the Postgres side requires real UUID objects. This keeps the call sites
    simple and the type boundary explicit.
    """
    if isinstance(value, UUID):
        return value
    return uuid.UUID(str(value))


def _update_search_coverage(
    pool: ConnectionPool,
    *,
    source_id: str,
    thesis_version_id: str,
    pillar_ids: list[str],
) -> None:
    """Append a {thesis_version_id, pillar_ids} entry to source_register.search_coverage."""
    if not pillar_ids:
        return
    entry = {
        "thesis_version_id": thesis_version_id,
        "pillar_ids": pillar_ids,
    }
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE source_register
                SET search_coverage = search_coverage || %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                """,
                (json.dumps([entry]), _coerce_uuid(source_id)),
            )
            conn.commit()


def deep_read_sources_for_pillars(
    pool: ConnectionPool,
    runner: CypherRunner,
    *,
    project_id: str,
    thesis_version_id: str,
) -> DeepReadResult:
    """Read the pillars of a thesis, resolve them to supporting sources via
    the Neo4j evidence graph, and write the result back into
    source_register.search_coverage (Postgres).

    Steps (all deterministic, no LLM in this function):
      1. Load pillars from Postgres (thesis_pillars).
      2. For each pillar, list active sources via Neo4j (Pillar -> Claim -> Source).
      3. For each source id, append a {thesis_version_id, pillar_ids} entry to
         source_register.search_coverage in Postgres.
      4. Return a DeepReadResult summarizing the linkage.

    Pillars that have no supporting claims or no active sources are still
    returned in the result so the caller can detect coverage gaps.
    """
    pillars = _fetch_pillars_from_postgres(pool, thesis_version_id)

    # Build pillar -> sources map.
    pillar_links: list[PillarLink] = []
    for pillar in pillars:
        source_ids = list_sources_for_pillar(
            runner,
            project_id=project_id,
            pillar_id=str(pillar["id"]),
        )
        pillar_links.append(
            PillarLink(
                pillar_id=str(pillar["id"]),
                pillar_index=int(pillar["pillar_index"]),
                pillar_type=str(pillar["pillar_type"]),
                statement=str(pillar["statement"]),
                source_ids=tuple(source_ids),
            )
        )

    # Invert: source_id -> pillar_ids (preserve deterministic ordering by pillar_index).
    source_to_pillars: dict[str, list[str]] = {}
    for link in pillar_links:
        for source_id in link.source_ids:
            source_to_pillars.setdefault(source_id, []).append(link.pillar_id)

    for source_id, pillar_ids in source_to_pillars.items():
        _update_search_coverage(
            pool,
            source_id=source_id,
            thesis_version_id=thesis_version_id,
            pillar_ids=pillar_ids,
        )

    return DeepReadResult(
        project_id=project_id,
        thesis_version_id=str(thesis_version_id),
        pillar_links=tuple(pillar_links),
    )
