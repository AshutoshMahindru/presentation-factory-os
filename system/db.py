from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any


DATABASE_URL_ENV = "DATABASE_URL"
POSTGRES_URL_ENV = "POSTGRES_URL"
DEFAULT_POOL_MIN_SIZE = 1
DEFAULT_POOL_MAX_SIZE = 5
DEFAULT_COMPOSE_FILE = "docker-compose.apps.yaml"

_pool: Any | None = None
_pool_database_url: str | None = None


def resolve_database_url(
    database_url: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    if database_url:
        return database_url

    source_env = env if env is not None else os.environ
    return source_env.get(DATABASE_URL_ENV) or source_env.get(POSTGRES_URL_ENV)


def require_database_url(
    database_url: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    resolved = resolve_database_url(database_url=database_url, env=env)
    if not resolved:
        raise RuntimeError(
            f"Postgres database URL is required; set {DATABASE_URL_ENV} or {POSTGRES_URL_ENV}"
        )
    return resolved


def open_pool(
    database_url: str | None = None,
    *,
    min_size: int = DEFAULT_POOL_MIN_SIZE,
    max_size: int | None = None,
) -> Any:
    global _pool, _pool_database_url

    if database_url is None and _pool is not None:
        return _pool

    resolved_url = require_database_url(database_url)
    if _pool is not None and _pool_database_url == resolved_url:
        return _pool

    close_pool()

    ConnectionPool = _load_connection_pool()
    resolved_max_size = max_size if max_size is not None else _resolve_pool_max_size()
    _pool = ConnectionPool(
        conninfo=resolved_url,
        min_size=min_size,
        max_size=resolved_max_size,
        open=True,
    )
    _pool_database_url = resolved_url
    return _pool


def close_pool() -> None:
    global _pool, _pool_database_url

    if _pool is not None:
        _pool.close()
    _pool = None
    _pool_database_url = None


@contextmanager
def get_connection(
    database_url: str | None = None,
    *,
    autocommit: bool = False,
    row_factory: Any | None = None,
    options: str | None = None,
    use_pool: bool = True,
) -> Iterator[Any]:
    if use_pool and row_factory is None and options is None:
        try:
            pool = open_pool(database_url)
        except RuntimeError as exc:
            if "psycopg_pool" not in str(exc):
                raise
        else:
            with pool.connection() as connection:
                original_autocommit = connection.autocommit
                connection.autocommit = autocommit
                try:
                    yield connection
                finally:
                    connection.autocommit = original_autocommit
            return

    connection = _connect(
        require_database_url(database_url),
        autocommit=autocommit,
        row_factory=row_factory,
        options=options,
    )
    try:
        with connection:
            yield connection
    finally:
        pass


@contextmanager
def transaction(database_url: str | None = None) -> Iterator[Any]:
    with get_connection(database_url=database_url, autocommit=False) as connection:
        with connection.transaction():
            yield connection


def execute_psql(sql: str, database_url: str | None = None) -> subprocess.CompletedProcess[str]:
    if resolve_database_url(database_url) is None:
        return _execute_sql_via_docker_psql(sql)

    try:
        stdout = _execute_sql_as_psql_text(sql=sql, database_url=database_url)
    except Exception as exc:  # pragma: no cover - concrete failures are environment-specific.
        return subprocess.CompletedProcess(
            args=["system.db.execute_psql"],
            returncode=1,
            stdout="",
            stderr=str(exc),
        )

    return subprocess.CompletedProcess(
        args=["system.db.execute_psql"],
        returncode=0,
        stdout=stdout,
        stderr="",
    )


def _execute_sql_via_docker_psql(sql: str) -> subprocess.CompletedProcess[str]:
    compose_file = os.environ.get("COMPOSE_FILE", DEFAULT_COMPOSE_FILE)
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            compose_file,
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
            sql,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _execute_sql_as_psql_text(sql: str, database_url: str | None = None) -> str:
    lines: list[str] = []
    with get_connection(database_url=database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            while True:
                if cursor.description is not None:
                    lines.extend(_format_row(row) for row in cursor.fetchall())
                if not _move_to_next_result_set(cursor):
                    break

    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _format_row(row: Any) -> str:
    values = row.values() if isinstance(row, Mapping) else row
    return "|".join(_format_value(value) for value in values)


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def _move_to_next_result_set(cursor: Any) -> bool:
    nextset = getattr(cursor, "nextset", None)
    if nextset is None:
        return False
    return bool(nextset())


def _connect(database_url: str, **kwargs: Any) -> Any:
    import psycopg

    return psycopg.connect(database_url, **{key: value for key, value in kwargs.items() if value is not None})


def _load_connection_pool() -> Any:
    try:
        from psycopg_pool import ConnectionPool
    except ImportError as exc:  # pragma: no cover - depends on installed extras.
        raise RuntimeError("psycopg_pool is required; install psycopg[binary,pool]") from exc
    return ConnectionPool


def _resolve_pool_max_size() -> int:
    raw_value = os.environ.get("PFOS_DB_POOL_MAX_SIZE")
    if not raw_value:
        return DEFAULT_POOL_MAX_SIZE
    return int(raw_value)
