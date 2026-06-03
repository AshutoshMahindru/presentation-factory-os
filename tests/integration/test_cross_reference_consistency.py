from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "20_Cross_Reference_Matrix.md"
RELEASE_CHECKLIST = ROOT / "docs" / "33_Release_Checklist_v3.2.4.md"
STEP_MAP = ROOT / "docs" / "43_PFOS_v2_Clean_Integer_Step_Map.md"
STEP_123 = ROOT / ".pfos" / "baby_steps" / "123_chat_session_schema_api.yaml"
STEP_124 = ROOT / ".pfos" / "baby_steps" / "124_intake_chat_orchestrator.yaml"
STEP_125 = ROOT / ".pfos" / "baby_steps" / "125_ci_workflow_sql_canonicalization.yaml"
STEP_164 = ROOT / ".pfos" / "baby_steps" / "164_design_override_panel_audit.yaml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_step(path: Path) -> dict:
    return yaml.safe_load(_read(path))


def test_clean_v2_step_map_defines_integer_sequence() -> None:
    step_123 = _load_step(STEP_123)
    step_124 = _load_step(STEP_124)
    step_164 = _load_step(STEP_164)
    step_map = _read(STEP_MAP)

    assert step_123["step_id"] == 123
    assert step_123["name"] == "chat_session_schema_api"
    assert step_124["step_id"] == 124
    assert step_124["name"] == "intake_chat_orchestrator"
    assert step_164["step_id"] == 164
    assert step_164["name"] == "design_override_panel_audit"

    assert "124.5" in step_map
    assert "Clean step" in step_map
    assert "Step 164" in step_map


def test_release_checklist_matches_implemented_project_health_endpoint() -> None:
    checklist = _read(RELEASE_CHECKLIST)
    matrix = _read(MATRIX)

    assert "tests/integration/test_project_health_endpoint.py" in checklist
    assert "aggregate project health" in checklist
    assert "aggregate health remains planned" not in checklist
    assert "Project health dashboard read-only" in matrix
    assert "does not drive transitions directly" in matrix


def test_release_checklist_and_matrix_match_step_124_sql_canonicalization() -> None:
    step = _load_step(STEP_125)
    checklist = _read(RELEASE_CHECKLIST)
    matrix = _read(MATRIX)

    assert step["step_id"] == 125
    assert "ci_workflow_sql_canonicalization" == step["name"]
    assert "scripts/check_sql_canonical.py" in step["files_expected"]

    assert "make validate-sql-canonical" in checklist
    assert "docs/04_Database_Schemas.sql" in checklist
    assert "infra/postgres/init/001_schema.sql" in checklist
    assert "choose and enforce a canonical source" not in checklist
    assert "SQL canonicalization matches deployable schema" in matrix
    assert "make validate-sql-canonical" in matrix
