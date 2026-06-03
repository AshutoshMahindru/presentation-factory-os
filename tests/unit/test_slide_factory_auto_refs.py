from copy import deepcopy

from deck_builder.slide_factory import SlideFactory, inject_auto_refs


def slide_payload():
    return {
        "slide_id": "slide_001",
        "job": {
            "type": "explain_unit_economics",
            "required_evidence": ["source_existing"],
        },
        "content": {
            "headline": "Unit economics hold under pressure",
            "body": "Contribution margin improves to 38% by month 18.",
            "chart_id": None,
            "evidence_refs": ["source_existing"],
            "financial_refs": ["FM!EXISTING"],
        },
        "visual_quality": "code_generated",
        "materiality": "high",
    }


def test_inject_auto_refs_merges_evidence_required_evidence_and_financial_refs() -> None:
    base = slide_payload()
    injected = inject_auto_refs(
        base,
        source_refs=["source_new", "source_existing"],
        financial_refs=["FM!MANUAL"],
        financial_cells=[
            {
                "cell_ref": "FM!CM_M18_BASE",
                "scenario": "base",
                "validation_status": "validated",
            },
            {
                "cell_ref": "FM!CM_M18_DOWNSIDE",
                "scenario": "downside",
                "validation_status": "validated",
            },
            {
                "cell_ref": "FM!BROKEN",
                "scenario": "base",
                "validation_status": "failed",
            },
        ],
        scenario="base",
    )

    assert injected["content"]["evidence_refs"] == ["source_existing", "source_new"]
    assert injected["job"]["required_evidence"] == ["source_existing", "source_new"]
    assert injected["content"]["financial_refs"] == [
        "FM!EXISTING",
        "FM!MANUAL",
        "FM!CM_M18_BASE",
    ]
    assert injected["provenance"]["auto_refs"] == {
        "evidence_refs": ("source_existing", "source_new"),
        "financial_refs": ("FM!EXISTING", "FM!MANUAL", "FM!CM_M18_BASE"),
    }


def test_inject_auto_refs_is_copy_on_write() -> None:
    base = slide_payload()
    original = deepcopy(base)

    injected = SlideFactory().inject_auto_refs(
        base,
        source_refs=["source_new"],
        financial_cells={
            "FM!CM_M18_BASE": {
                "scenario": "base",
                "validation_status": "validated",
            }
        },
        scenario="base",
    )

    assert injected is not base
    assert injected["content"]["evidence_refs"] == ["source_existing", "source_new"]
    assert base == original
