from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "20_Cross_Reference_Matrix.md"
RELEASE_CHECKLIST = ROOT / "docs" / "33_Release_Checklist_v3.2.4.md"
STEP_115 = ROOT / ".pfos" / "baby_steps" / "115_aggregate_project_health_endpoint.yaml"
STEP_124 = ROOT / ".pfos" / "baby_steps" / "124_sql_canonicalization_drift_check.yaml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_step(path: Path) -> dict:
    return yaml.safe_load(_read(path))


def test_release_checklist_matches_step_115_project_health_endpoint() -> None:
    step = _load_step(STEP_115)
    checklist = _read(RELEASE_CHECKLIST)
    matrix = _read(MATRIX)

    assert step["step_id"] == 115
    assert "aggregate_project_health_endpoint" == step["name"]
    assert "tests/integration/test_project_health_endpoint.py" in step["files_expected"]

    assert "tests/integration/test_project_health_endpoint.py" in checklist
    assert "aggregate project health" in checklist
    assert "aggregate health remains planned" not in checklist
    assert "Project health dashboard read-only" in matrix
    assert "does not drive transitions directly" in matrix


def test_release_checklist_and_matrix_match_step_124_sql_canonicalization() -> None:
    step = _load_step(STEP_124)
    checklist = _read(RELEASE_CHECKLIST)
    matrix = _read(MATRIX)

    assert step["step_id"] == 124
    assert "sql_canonicalization_drift_check" == step["name"]
    assert "python3 scripts/check_sql_canonical.py" in step["validation_commands"]

    assert "make validate-sql-canonical" in checklist
    assert "docs/04_Database_Schemas.sql" in checklist
    assert "infra/postgres/init/001_schema.sql" in checklist
    assert "choose and enforce a canonical source" not in checklist
    assert "SQL canonicalization matches deployable schema" in matrix
    assert "make validate-sql-canonical" in matrix
