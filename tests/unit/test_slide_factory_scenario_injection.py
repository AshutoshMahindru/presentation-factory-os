from deck_builder.slide_factory import SlideFactory, inject_scenario_financial_refs


def slide():
    return {
        "slide_id": "slide_001",
        "job": {
            "type": "explain_unit_economics",
            "required_evidence": ["source_001"],
        },
        "content": {
            "headline": "Unit economics hold under pressure",
            "body": "Contribution margin improves to 38% by month 18.",
            "chart_id": None,
            "evidence_refs": ["source_001"],
            "financial_refs": [],
        },
        "visual_quality": "code_generated",
        "materiality": "high",
    }


def test_injects_validated_refs_for_requested_scenario_only() -> None:
    injected = inject_scenario_financial_refs(
        slide(),
        scenario="downside",
        financial_cells=[
            {
                "cell_ref": "FM!CM_M18_DOWNSIDE",
                "scenario": "downside",
                "validation_status": "validated",
            },
            {
                "cell_ref": "FM!CM_M18_BASE",
                "scenario": "base",
                "validation_status": "validated",
            },
            {
                "cell_ref": "FM!UNVALIDATED",
                "scenario": "downside",
                "validation_status": "failed",
            },
        ],
    )

    assert injected["content"]["financial_refs"] == ["FM!CM_M18_DOWNSIDE"]
    assert injected["provenance"]["financial_scenario"]["scenario"] == "downside"


def test_slide_factory_preserves_existing_refs_and_does_not_mutate_input() -> None:
    base_slide = slide()
    base_slide["content"]["financial_refs"] = ["FM!EXISTING"]

    injected = SlideFactory().build_slide(
        base_slide,
        scenario="downside",
        financial_cells={
            "FM!CM_M18_DOWNSIDE": {
                "scenario": "downside",
                "validation_status": "validated",
            }
        },
    )

    assert injected["content"]["financial_refs"] == [
        "FM!EXISTING",
        "FM!CM_M18_DOWNSIDE",
    ]
    assert base_slide["content"]["financial_refs"] == ["FM!EXISTING"]


def test_build_slide_combines_auto_refs_with_scenario_financial_refs() -> None:
    injected = SlideFactory().build_slide(
        slide(),
        source_refs=["source_002"],
        scenario="downside",
        financial_cells=[
            {
                "cell_ref": "FM!CM_M18_DOWNSIDE",
                "scenario": "downside",
                "validation_status": "validated",
            }
        ],
    )

    assert injected["job"]["required_evidence"] == ["source_001", "source_002"]
    assert injected["content"]["evidence_refs"] == ["source_001", "source_002"]
    assert injected["content"]["financial_refs"] == ["FM!CM_M18_DOWNSIDE"]
    assert injected["provenance"]["financial_scenario"]["scenario"] == "downside"
