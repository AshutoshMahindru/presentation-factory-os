from __future__ import annotations

from collections.abc import Iterator

import pytest

from system import db


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.rows = rows or []
        self.description = ("result",) if self.rows else None
        self.executed_sql: str | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def nextset(self) -> bool:
        return False


class FakeTransaction:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeTransaction:
        self.entered = True
        return self

    def __exit__(self, *args: object) -> None:
        self.exited = True


class FakeConnection:
    def __init__(self, cursor: FakeCursor | None = None, autocommit: bool = False) -> None:
        self.autocommit = autocommit
        self.cursor_obj = cursor or FakeCursor()
        self.transaction_obj = FakeTransaction()
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeConnection:
        self.entered = True
        return self

    def __exit__(self, *args: object) -> None:
        self.exited = True

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj


class FakePool:
    instances: list[FakePool] = []

    def __init__(self, conninfo: str, min_size: int, max_size: int, open: bool) -> None:
        self.conninfo = conninfo
        self.min_size = min_size
        self.max_size = max_size
        self.open = open
        self.closed = False
        self.connection_obj = FakeConnection()
        FakePool.instances.append(self)

    def connection(self) -> FakeConnection:
        return self.connection_obj

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def reset_pool() -> Iterator[None]:
    db.close_pool()
    FakePool.instances.clear()
    yield
    db.close_pool()
    FakePool.instances.clear()


def test_resolve_database_url_prefers_explicit_then_database_url_then_postgres_url() -> None:
    env = {
        "DATABASE_URL": "postgresql://database",
        "POSTGRES_URL": "postgresql://postgres",
    }

    assert db.resolve_database_url("postgresql://explicit", env=env) == "postgresql://explicit"
    assert db.resolve_database_url(env=env) == "postgresql://database"
    assert db.resolve_database_url(env={"POSTGRES_URL": "postgresql://postgres"}) == "postgresql://postgres"
    assert db.resolve_database_url(env={}) is None


def test_require_database_url_raises_when_missing() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL or POSTGRES_URL"):
        db.require_database_url(env={})


def test_get_connection_uses_direct_psycopg_connection_when_pool_is_unavailable(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    connection = FakeConnection()

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        calls.append((database_url, kwargs))
        return connection

    monkeypatch.setattr(db, "_connect", fake_connect)
    monkeypatch.setattr(
        db,
        "_load_connection_pool",
        lambda: (_ for _ in ()).throw(RuntimeError("psycopg_pool unavailable")),
    )

    with db.get_connection("postgresql://direct", autocommit=True) as resolved:
        assert resolved is connection

    assert calls == [("postgresql://direct", {"autocommit": True, "row_factory": None, "options": None})]
    assert connection.entered is True
    assert connection.exited is True


def test_transaction_context_opens_connection_transaction(monkeypatch) -> None:
    connection = FakeConnection()

    monkeypatch.setattr(db, "_connect", lambda *args, **kwargs: connection)
    monkeypatch.setattr(
        db,
        "_load_connection_pool",
        lambda: (_ for _ in ()).throw(RuntimeError("psycopg_pool unavailable")),
    )

    with db.transaction("postgresql://tx") as resolved:
        assert resolved is connection
        assert connection.transaction_obj.entered is True

    assert connection.transaction_obj.exited is True


def test_pool_lifecycle_reuses_and_closes_pool(monkeypatch) -> None:
    monkeypatch.setattr(db, "_load_connection_pool", lambda: FakePool)

    pool = db.open_pool("postgresql://pooled", min_size=2, max_size=7)
    reused = db.open_pool()

    assert reused is pool
    assert pool.conninfo == "postgresql://pooled"
    assert pool.min_size == 2
    assert pool.max_size == 7
    assert pool.open is True

    with db.get_connection(autocommit=True) as connection:
        assert connection is pool.connection_obj
        assert connection.autocommit is True

    assert pool.connection_obj.autocommit is False

    db.close_pool()

    assert pool.closed is True


def test_execute_psql_formats_rows_like_psql_text(monkeypatch) -> None:
    cursor = FakeCursor(rows=[("alpha", None, True, False, {"b": 2, "a": 1})])
    connection = FakeConnection(cursor=cursor)

    monkeypatch.setattr(db, "_connect", lambda *args, **kwargs: connection)
    monkeypatch.setattr(
        db,
        "_load_connection_pool",
        lambda: (_ for _ in ()).throw(RuntimeError("psycopg_pool unavailable")),
    )

    result = db.execute_psql("SELECT 1;", database_url="postgresql://db")

    assert result.returncode == 0
    assert result.stdout == 'alpha||t|f|{"a":1,"b":2}\n'
    assert cursor.executed_sql == "SELECT 1;"


def test_execute_psql_falls_back_to_local_compose_psql_when_no_database_url_is_available(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    captured: dict[str, object] = {}

    class FakeResult:
        returncode = 0
        stdout = "1\n"
        stderr = ""

    def fake_run(args: list[str], **kwargs: object) -> FakeResult:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeResult()

    monkeypatch.setattr(db.subprocess, "run", fake_run)

    result = db.execute_psql("SELECT 1;")

    assert result.returncode == 0
    assert result.stdout == "1\n"
    assert captured["args"] == [
        "docker",
        "compose",
        "-f",
        "docker-compose.apps.yaml",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "pfos",
        "-d",
        "pfos",
        "-v",
        "ON_ERROR_STOP=1",
        "-A",
        "-t",
        "-F",
        "|",
        "-c",
        "SELECT 1;",
    ]
