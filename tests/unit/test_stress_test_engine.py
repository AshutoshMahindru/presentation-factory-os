import pytest

from financial_model.stress_test_engine import (
    ScenarioDependency,
    StressTestEngine,
    StressTestValidationError,
    build_stress_test_metadata,
    run_stress_test,
)


def dependency():
    return ScenarioDependency(
        project_id="project_001",
        scenario="downside",
        depends_on_scenario="base",
        dependency_type="downside",
        rationale="Revenue pressure case",
    )


def test_build_metadata_records_declared_scenario_dependency() -> None:
    metadata = build_stress_test_metadata(
        dependency(),
        cell_refs=["FM!REV_BASE"],
        shocks={"FM!REV_BASE": -0.1},
    )

    assert metadata["deterministic"] is True
    assert metadata["scenario"] == "downside"
    assert metadata["depends_on_scenario"] == "base"
    assert metadata["dependency_type"] == "downside"
    assert metadata["cell_refs"] == ("FM!REV_BASE",)


def test_rejects_self_dependency() -> None:
    engine = StressTestEngine()

    with pytest.raises(StressTestValidationError, match="cannot point to themselves"):
        engine.validate_dependency(
            {
                "project_id": "project_001",
                "scenario": "base",
                "depends_on_scenario": "base",
                "dependency_type": "downside",
            }
        )


def test_run_stress_test_clones_base_cells_into_stressed_scenario() -> None:
    result = run_stress_test(
        [
            {
                "project_id": "project_001",
                "scenario": "base",
                "cell_ref": "FM!REV_BASE",
                "label": "Revenue",
                "value": 100.0,
                "formula": "=A1",
            }
        ],
        dependency(),
        shocks={"FM!REV_BASE": -0.2},
    )

    assert result.scenario == "downside"
    assert len(result.stressed_cells) == 1
    assert result.stressed_cells[0]["scenario"] == "downside"
    assert result.stressed_cells[0]["value"] == 80.0
    assert result.stressed_cells[0]["validation_status"] == "validated"
    assert result.stressed_cells[0]["stress_test_metadata"]["depends_on_scenario"] == "base"
