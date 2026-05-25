from __future__ import annotations

from pathlib import Path

from scripts import check_postgres_schema_drift


def write_schema(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def test_normalization_ignores_trailing_whitespace_and_final_newlines(tmp_path: Path) -> None:
    docs_schema = write_schema(
        tmp_path / "docs.sql",
        "CREATE TABLE projects (\n    id UUID PRIMARY KEY\n);\n\n",
    )
    init_schema = write_schema(
        tmp_path / "init.sql",
        "CREATE TABLE projects (   \n    id UUID PRIMARY KEY   \n);",
    )

    assert check_postgres_schema_drift.schemas_match(docs_schema, init_schema)


def test_schema_drift_fails_for_substantive_content_change(tmp_path: Path) -> None:
    docs_schema = write_schema(
        tmp_path / "docs.sql",
        "CREATE TABLE projects (\n    id UUID PRIMARY KEY\n);\n",
    )
    init_schema = write_schema(
        tmp_path / "init.sql",
        "CREATE TABLE projects (\n    id TEXT PRIMARY KEY\n);\n",
    )

    assert not check_postgres_schema_drift.schemas_match(docs_schema, init_schema)
    diff = check_postgres_schema_drift.unified_diff(docs_schema, init_schema)

    assert "-    id UUID PRIMARY KEY" in diff
    assert "+    id TEXT PRIMARY KEY" in diff


def test_main_returns_zero_when_schemas_match(tmp_path: Path, capsys) -> None:
    docs_schema = write_schema(tmp_path / "docs.sql", "CREATE TABLE projects (id UUID);\n")
    init_schema = write_schema(tmp_path / "init.sql", "CREATE TABLE projects (id UUID);")

    exit_code = check_postgres_schema_drift.main(
        ["--docs-schema", str(docs_schema), "--init-schema", str(init_schema)]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "PASS Postgres schema drift" in output


def test_main_returns_nonzero_and_prints_diff_when_schemas_drift(
    tmp_path: Path, capsys
) -> None:
    docs_schema = write_schema(tmp_path / "docs.sql", "CREATE TABLE projects (id UUID);\n")
    init_schema = write_schema(tmp_path / "init.sql", "CREATE TABLE projects (id TEXT);\n")

    exit_code = check_postgres_schema_drift.main(
        ["--docs-schema", str(docs_schema), "--init-schema", str(init_schema)]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL Postgres schema drift" in output
    assert "--- " in output
    assert "+++ " in output
    assert "-CREATE TABLE projects (id UUID);" in output
    assert "+CREATE TABLE projects (id TEXT);" in output
