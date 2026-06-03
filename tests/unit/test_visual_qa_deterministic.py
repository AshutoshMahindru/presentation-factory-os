from deck_builder.visual_qa_deterministic import DeterministicVisualQA
from system.visual_qa_deterministic_validator import validate_visual_qa_result
from system.visual_qa_repository import InMemoryVisualQARepository


def valid_slide():
    return {
        "slide_id": "slide_001",
        "materiality": "high",
        "visual_quality": "code_generated",
        "content": {
            "headline": "Renewal expansion is the base case",
            "body": "Retention evidence supports the operating plan.",
            "evidence_refs": ["src_001"],
        },
    }


def test_deterministic_visual_qa_passes_clean_material_slide():
    result = DeterministicVisualQA().score_slide(valid_slide())

    assert result.status == "passed"
    assert result.score >= 0.72
    assert result.findings == ()


def test_deterministic_visual_qa_fails_degraded_visual():
    slide = valid_slide()
    slide["visual_quality"] = "degraded"

    result = DeterministicVisualQA().score_slide(slide)

    assert result.status == "failed"
    assert "degraded_visual" in result.findings


def test_visual_qa_repository_records_latest_result():
    repo = InMemoryVisualQARepository()
    record = repo.record_result(
        project_id="project_001",
        artifact_id="deck_001",
        status="passed",
        score=0.91,
        findings=(),
    )

    assert repo.latest_for_artifact("project_001", "deck_001") == record
    assert repo.list_project_results("project_001")[0]["score"] == 0.91


def test_visual_qa_result_validator_rejects_bad_shape():
    assert validate_visual_qa_result({"status": "unknown", "score": 2, "findings": "x"}) == [
        "status must be passed or failed",
        "score must be between 0 and 1",
        "findings must be a list or tuple",
    ]
