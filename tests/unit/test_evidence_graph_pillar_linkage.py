from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

import pytest

from evidence_graph import evidence_linker
from evidence_graph.evidence_linker import (
    DeepReadResult,
    PillarLink,
    deep_read_sources_for_pillars,
    link_claim_to_pillar,
    list_sources_for_pillar,
    upsert_pillar,
)


# ---------------------------------------------------------------------------
# Test-scoped monkey patch: let the linker accept arbitrary string ids in
# the fake graph. In production the ids will be canonical UUIDs from
# source_register.id and thesis_pillars.id; the fake uses human-readable
# labels for readability, so we relax the coercion here.
# ---------------------------------------------------------------------------


def _passthrough_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    # Fake ids: wrap the string in a deterministic v5 UUID so the
    # Postgres-side types stay valid even though the underlying identity
    # is a label. Production callers always pass real UUIDs.
    return uuid.uuid5(uuid.NAMESPACE_DNS, str(value))


@pytest.fixture(autouse=True)
def _relax_uuid_coercion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evidence_linker, "_coerce_uuid", _passthrough_uuid)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeCypherRunner:
    """Deterministic in-memory Neo4j stub.

    Holds a small graph of (node_id -> props) and (src, rel, dst) edges.
    Implements just enough of the patterns used by evidence_linker:
      - upsert_pillar   -> MERGE Pillar + HAS_PILLAR edge
      - link_claim_to_pillar -> MERGE SUPPORTS_PILLAR edge
      - list_sources_for_pillar -> MATCH pillar <-SUPPORTS- claim -SUPPORTED_BY-> source
    """

    def __init__(self) -> None:
        # node_id -> {label, props}
        self.nodes: dict[str, dict[str, Any]] = {}
        # (src_id, rel_type, dst_id) -> {props}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    # --- helpers used by tests -------------------------------------------------

    def add_node(self, node_id: str, label: str, **props: Any) -> None:
        self.nodes[node_id] = {"label": label, "props": props}

    def add_edge(self, src: str, rel: str, dst: str, **props: Any) -> None:
        self.edges[(src, rel, dst)] = props

    # --- runner contract -------------------------------------------------------

    def __call__(self, query: str, params: dict[str, Any]) -> Iterable[dict[str, Any]]:
        q = " ".join(query.split())  # collapse whitespace

        # upsert_pillar
        if q.startswith("MERGE (p:Project") and "MERGE (pl:Pillar" in q:
            project_id = params["project_id"]
            pillar_id = params["pillar_id"]
            self.add_node(project_id, "Project", id=project_id)
            self.add_node(
                pillar_id,
                "Pillar",
                id=pillar_id,
                project_id=project_id,
                thesis_version_id=params["thesis_version_id"],
                pillar_index=params["pillar_index"],
                statement=params["statement"],
                pillar_type=params["pillar_type"],
            )
            self.add_edge(project_id, "HAS_PILLAR", pillar_id)
            return [{"pillar_id": pillar_id}]

        # link_claim_to_pillar
        if "MERGE (c)-[r:SUPPORTS_PILLAR" in q:
            claim_id = params["claim_id"]
            pillar_id = params["pillar_id"]
            project_id = params["project_id"]
            if (
                claim_id not in self.nodes
                or self.nodes[claim_id]["label"] != "Claim"
                or pillar_id not in self.nodes
                or self.nodes[pillar_id]["label"] != "Pillar"
            ):
                return []
            self.add_edge(
                claim_id,
                "SUPPORTS_PILLAR",
                pillar_id,
                pillar_id=pillar_id,
                confidence=params["confidence"],
            )
            return [{"claim_id": claim_id, "pillar_id": pillar_id}]

        # list_sources_for_pillar
        if "MATCH (pl:Pillar" in q and "MATCH (pl)<-[sp:SUPPORTS_PILLAR" in q:
            pillar_id = params["pillar_id"]
            project_id = params["project_id"]
            pillar = self.nodes.get(pillar_id)
            if not pillar or pillar["label"] != "Pillar":
                return []
            if pillar["props"].get("project_id") != project_id:
                return []

            # claim nodes that SUPPORTS_PILLAR this pillar
            claim_ids = [
                src
                for (src, rel, dst), edge_props in self.edges.items()
                if rel == "SUPPORTS_PILLAR" and dst == pillar_id
            ]
            source_ids: set[str] = set()
            for claim_id in claim_ids:
                for (src, rel, dst), edge_props in self.edges.items():
                    if (
                        rel == "SUPPORTED_BY"
                        and src == claim_id
                        and dst in self.nodes
                        and self.nodes[dst]["label"] == "Source"
                        and self.nodes[dst]["props"].get("status") == "active"
                    ):
                        source_ids.add(dst)
            return [{"source_id": sid} for sid in sorted(source_ids)]

        raise AssertionError(f"FakeCypherRunner: unhandled query: {q[:80]}...")


class FakePool:
    """Minimal psycopg_pool.ConnectionPool stub for the linker's
    _fetch_pillars_from_postgres and _update_search_coverage paths.

    Stores pillars and source rows in memory; raises if a fixture is missing.
    """

    def __init__(self) -> None:
        self.pillars: list[dict[str, Any]] = []
        self.sources: dict[str, dict[str, Any]] = {}  # id -> mutable row
        # Test-observable log of every UPDATE source_register search_coverage.
        self._coverage_writes: list[tuple[str, list[dict[str, Any]]]] = []

    def add_pillar(
        self,
        pillar_id: str,
        pillar_index: int,
        pillar_type: str,
        statement: str,
    ) -> None:
        self.pillars.append(
            {
                "id": pillar_id,
                "pillar_index": pillar_index,
                "pillar_type": pillar_type,
                "statement": statement,
            }
        )

    def add_source(self, source_id: str, search_coverage: list | None = None) -> None:
        # Coerce the id through the same UUID-v5 path the linker uses, so
        # lookups by str() match the keys in self.sources.
        from evidence_graph import evidence_linker
        coerced = evidence_linker._coerce_uuid(source_id)
        self.sources[str(coerced)] = {"search_coverage": list(search_coverage or [])}

    def connection(self):  # type: ignore[no-untyped-def]
        outer = self

        class _CM:
            def __enter__(self_inner):  # type: ignore[no-untyped-def]
                return _FakeConn(outer)

            def __exit__(self_inner, *exc: Any) -> bool:  # type: ignore[no-untyped-def]
                return False

        return _CM()


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn
        self._result: list[dict[str, Any]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: tuple = ()) -> None:
        sql_norm = " ".join(sql.split())
        # SELECT pillars
        if "FROM thesis_pillars" in sql_norm and "WHERE thesis_version_id" in sql_norm:
            thesis_version_id = params[0]
            # We don't filter by thesis_version here — the fake pool keeps all pillars
            # in one project; the linker should pass the right id and we just return
            # every pillar we know about for simplicity.
            self._result = [dict(p) for p in self._conn._pool.pillars]
            return
        # UPDATE source_register search_coverage
        if "UPDATE source_register" in sql_norm and "search_coverage" in sql_norm:
            entry_json, source_id = params
            entry_list = json.loads(entry_json)
            # The production code passes a UUID (via _coerce_uuid); the test
            # may monkey-patch _coerce_uuid to return a UUID derived from
            # the string label, so we compare with str() on both sides.
            source_id_str = str(source_id)
            if source_id_str not in {str(s) for s in self._conn._pool.sources}:
                # Silent no-op for unknown sources — matches the behavior of the
                # real UPDATE which affects 0 rows.
                self._result = []
                return
            self._conn._pool.sources[source_id_str]["search_coverage"].extend(entry_list)
            self._conn._pool._coverage_writes.append((source_id_str, entry_list))
            self._result = []
            return
        raise AssertionError(f"_FakeCursor: unhandled SQL: {sql_norm[:80]}...")

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._result)

    def fetchone(self) -> dict[str, Any] | None:
        return self._result[0] if self._result else None


class _FakeConn:
    def __init__(self, pool: FakePool) -> None:
        self._pool = pool

    def cursor(self, row_factory: Any = None) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests: upsert_pillar
# ---------------------------------------------------------------------------


def test_upsert_pillar_creates_pillar_node_and_project_edge() -> None:
    runner = FakeCypherRunner()
    pillar_id = upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-1",
        pillar_index=0,
        pillar_type="claim",
        statement="Margins are expanding.",
    )
    assert pillar_id == "pillar-1"
    assert "pillar-1" in runner.nodes
    assert "proj-1" in runner.nodes
    assert ("proj-1", "HAS_PILLAR", "pillar-1") in runner.edges


def test_upsert_pillar_rejects_invalid_pillar_type() -> None:
    runner = FakeCypherRunner()
    with pytest.raises(ValueError, match="Unsupported pillar_type"):
        upsert_pillar(
            runner,
            project_id="proj-1",
            thesis_version_id="thesis-1",
            pillar_id="pillar-bad",
            pillar_index=0,
            pillar_type="hypothesis",
            statement="x",
        )


# ---------------------------------------------------------------------------
# Tests: link_claim_to_pillar
# ---------------------------------------------------------------------------


def test_link_claim_to_pillar_creates_edge_with_confidence() -> None:
    runner = FakeCypherRunner()
    runner.add_node("claim-1", "Claim", id="claim-1", project_id="proj-1")
    upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-1",
        pillar_index=0,
        pillar_type="claim",
        statement="x",
    )
    link_claim_to_pillar(
        runner,
        project_id="proj-1",
        claim_id="claim-1",
        pillar_id="pillar-1",
        confidence=0.8,
    )
    assert ("claim-1", "SUPPORTS_PILLAR", "pillar-1") in runner.edges
    assert runner.edges[("claim-1", "SUPPORTS_PILLAR", "pillar-1")]["confidence"] == 0.8


def test_link_claim_to_pillar_rejects_out_of_range_confidence() -> None:
    runner = FakeCypherRunner()
    with pytest.raises(ValueError, match="confidence must be in"):
        link_claim_to_pillar(
            runner,
            project_id="proj-1",
            claim_id="claim-1",
            pillar_id="pillar-1",
            confidence=1.5,
        )


def test_link_claim_to_pillar_raises_when_claim_missing() -> None:
    runner = FakeCypherRunner()
    upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-1",
        pillar_index=0,
        pillar_type="claim",
        statement="x",
    )
    with pytest.raises(ValueError, match="no Claim"):
        link_claim_to_pillar(
            runner,
            project_id="proj-1",
            claim_id="claim-missing",
            pillar_id="pillar-1",
        )


# ---------------------------------------------------------------------------
# Tests: list_sources_for_pillar
# ---------------------------------------------------------------------------


def test_list_sources_for_pillar_returns_distinct_active_sources() -> None:
    runner = FakeCypherRunner()
    upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-1",
        pillar_index=0,
        pillar_type="data",
        statement="x",
    )
    runner.add_node("claim-1", "Claim", id="claim-1", project_id="proj-1")
    runner.add_node("claim-2", "Claim", id="claim-2", project_id="proj-1")
    runner.add_node("source-A", "Source", id="source-A", status="active")
    runner.add_node("source-B", "Source", id="source-B", status="active")
    runner.add_node("source-C", "Source", id="source-C", status="retracted")  # excluded
    # claim-1 -> pillar-1; both claims -> source-A; claim-2 -> source-B
    runner.add_edge("claim-1", "SUPPORTS_PILLAR", "pillar-1", pillar_id="pillar-1", confidence=1.0)
    runner.add_edge("claim-2", "SUPPORTS_PILLAR", "pillar-1", pillar_id="pillar-1", confidence=0.9)
    runner.add_edge("claim-1", "SUPPORTED_BY", "source-A", source_id="source-A")
    runner.add_edge("claim-2", "SUPPORTED_BY", "source-A", source_id="source-A")
    runner.add_edge("claim-2", "SUPPORTED_BY", "source-B", source_id="source-B")
    runner.add_edge("claim-1", "SUPPORTED_BY", "source-C", source_id="source-C")  # excluded

    sources = list_sources_for_pillar(runner, project_id="proj-1", pillar_id="pillar-1")
    assert sources == ("source-A", "source-B")  # sorted, distinct, no retracted


def test_list_sources_for_pillar_empty_when_no_claims() -> None:
    runner = FakeCypherRunner()
    upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-orphan",
        pillar_index=0,
        pillar_type="claim",
        statement="x",
    )
    assert list_sources_for_pillar(runner, project_id="proj-1", pillar_id="pillar-orphan") == ()


# ---------------------------------------------------------------------------
# Tests: deep_read_sources_for_pillars (end-to-end over the fakes)
# ---------------------------------------------------------------------------


def test_deep_read_writes_search_coverage_to_each_supporting_source() -> None:
    pool = FakePool()
    runner = FakeCypherRunner()
    # After _coerce_uuid, the string labels become deterministic v5 UUIDs.
    source_a_uuid = str(evidence_linker._coerce_uuid("source-A"))
    source_b_uuid = str(evidence_linker._coerce_uuid("source-B"))

    pool.add_pillar("pillar-1", 0, "data", "Margins are expanding.")
    pool.add_pillar("pillar-2", 1, "narrative", "Founder-led culture is a moat.")
    pool.add_source("source-A")
    pool.add_source("source-B")

    # Pillar 1 -> claim-1 -> source-A
    upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-1",
        pillar_index=0,
        pillar_type="data",
        statement="Margins are expanding.",
    )
    runner.add_node("claim-1", "Claim", id="claim-1", project_id="proj-1")
    runner.add_edge("claim-1", "SUPPORTS_PILLAR", "pillar-1", pillar_id="pillar-1", confidence=1.0)
    runner.add_node("source-A", "Source", id="source-A", status="active")
    runner.add_edge("claim-1", "SUPPORTED_BY", "source-A")

    # Pillar 2 -> claim-2 -> source-B
    upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-2",
        pillar_index=1,
        pillar_type="narrative",
        statement="Founder-led culture is a moat.",
    )
    runner.add_node("claim-2", "Claim", id="claim-2", project_id="proj-1")
    runner.add_edge("claim-2", "SUPPORTS_PILLAR", "pillar-2", pillar_id="pillar-2", confidence=0.7)
    runner.add_node("source-B", "Source", id="source-B", status="active")
    runner.add_edge("claim-2", "SUPPORTED_BY", "source-B")

    result = deep_read_sources_for_pillars(
        pool,
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
    )

    assert isinstance(result, DeepReadResult)
    assert result.project_id == "proj-1"
    assert result.thesis_version_id == "thesis-1"
    assert len(result.pillar_links) == 2
    assert result.total_sources() == 2
    assert result.pillar_ids_with_no_sources() == ()

    # Each source got exactly one coverage entry
    assert len(pool._coverage_writes) == 2  # type: ignore[attr-defined]
    written_sources = {sid for sid, _ in pool._coverage_writes}  # type: ignore[attr-defined]
    assert written_sources == {source_a_uuid, source_b_uuid}
    for source_id, entries in pool._coverage_writes:  # type: ignore[attr-defined]
        assert entries[0]["thesis_version_id"] == "thesis-1"
        expected_pillar = "pillar-1" if source_id == source_a_uuid else "pillar-2"
        assert entries[0]["pillar_ids"] == [expected_pillar]


def test_deep_read_returns_pillars_with_no_sources_for_coverage_audit() -> None:
    pool = FakePool()
    runner = FakeCypherRunner()

    pool.add_pillar("pillar-empty", 0, "claim", "Unsupported thesis pillar.")
    upsert_pillar(
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
        pillar_id="pillar-empty",
        pillar_index=0,
        pillar_type="claim",
        statement="Unsupported thesis pillar.",
    )
    # No claims, no sources.

    result = deep_read_sources_for_pillars(
        pool,
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
    )

    assert result.pillar_ids_with_no_sources() == ("pillar-empty",)
    assert result.total_sources() == 0
    # No coverage writes when there are no sources.
    assert pool._coverage_writes == []  # type: ignore[attr-defined]


def test_deep_read_aggregates_multiple_pillars_per_source() -> None:
    pool = FakePool()
    runner = FakeCypherRunner()

    pool.add_pillar("pillar-1", 0, "data", "P1")
    pool.add_pillar("pillar-2", 1, "narrative", "P2")
    pool.add_source("source-shared")

    for pid, idx, ptype, stmt in [
        ("pillar-1", 0, "data", "P1"),
        ("pillar-2", 1, "narrative", "P2"),
    ]:
        upsert_pillar(
            runner,
            project_id="proj-1",
            thesis_version_id="thesis-1",
            pillar_id=pid,
            pillar_index=idx,
            pillar_type=ptype,
            statement=stmt,
        )
    runner.add_node("claim-1", "Claim", id="claim-1", project_id="proj-1")
    runner.add_edge("claim-1", "SUPPORTS_PILLAR", "pillar-1", pillar_id="pillar-1", confidence=1.0)
    runner.add_edge("claim-1", "SUPPORTS_PILLAR", "pillar-2", pillar_id="pillar-2", confidence=0.9)
    runner.add_node("source-shared", "Source", id="source-shared", status="active")
    runner.add_edge("claim-1", "SUPPORTED_BY", "source-shared")

    result = deep_read_sources_for_pillars(
        pool,
        runner,
        project_id="proj-1",
        thesis_version_id="thesis-1",
    )
    # 1 distinct source backs 2 pillars (sum of source-pillar pairs is 2).
    assert result.total_sources() == 2

    # One write to source-shared with BOTH pillars
    assert len(pool._coverage_writes) == 1  # type: ignore[attr-defined]
    sid, entries = pool._coverage_writes[0]  # type: ignore[attr-defined]
    assert sid == str(evidence_linker._coerce_uuid("source-shared"))
    assert entries[0]["pillar_ids"] == ["pillar-1", "pillar-2"]
