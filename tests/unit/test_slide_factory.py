import pytest

from deck_builder.slide_factory import (
    SlideFactory,
    SlideFactoryError,
    build_slide_jobs_from_pillars,
)
from deck_builder.slide_schema_validator import SlideSchemaValidator


def test_maps_pillars_to_schema_valid_slide_jobs_in_pillar_order() -> None:
    pillars = [
        {
            "id": "pillar-financial",
            "pillar_index": 2,
            "pillar_type": "financial",
            "statement": "Unit economics expand as retention improves.",
        },
        {
            "id": "pillar-market",
            "pillar_index": 0,
            "pillar_type": "data",
            "statement": "The market is large enough for venture-scale growth.",
        },
        {
            "id": "pillar-risk",
            "pillar_index": 1,
            "pillar_type": "objection",
            "statement": "Budget concentration is the primary buyer risk.",
        },
    ]

    slides = build_slide_jobs_from_pillars(
        pillars,
        source_refs_by_pillar={
            "pillar-market": ["source_market"],
            "pillar-risk": ["source_risk"],
            "pillar-financial": ["source_financial"],
        },
        financial_cells_by_pillar={
            "pillar-financial": {
                "FM!NRR_BASE": {
                    "scenario": "base",
                    "validation_status": "validated",
                }
            }
        },
        scenario="base",
    )

    assert [slide["slide_id"] for slide in slides] == ["slide_001", "slide_002", "slide_003"]
    assert [slide["job"]["type"] for slide in slides] == [
        "establish_market_size",
        "address_risk",
        "explain_unit_economics",
    ]
    assert slides[0]["content"]["evidence_refs"] == ["source_market"]
    assert slides[2]["content"]["financial_refs"] == ["FM!NRR_BASE"]
    assert slides[2]["provenance"]["pillar"]["pillar_id"] == "pillar-financial"

    validator = SlideSchemaValidator.from_file()
    for slide in slides:
        validator.assert_valid(slide)


def test_slide_factory_instance_exposes_pillar_mapper() -> None:
    slides = SlideFactory().build_slide_jobs_from_pillars(
        [
            {
                "id": "pillar-claim",
                "pillar_index": 0,
                "pillar_type": "claim",
                "statement": "The product wins in regulated teams.",
            }
        ],
        source_refs_by_pillar={"pillar-claim": ["source_001"]},
    )

    assert slides[0]["job"]["type"] == "compare_competitive_position"
    assert slides[0]["materiality"] == "medium"


def test_rejects_unsupported_pillar_type() -> None:
    with pytest.raises(SlideFactoryError, match="Unsupported pillar_type"):
        build_slide_jobs_from_pillars(
            [
                {
                    "id": "pillar-bad",
                    "pillar_index": 0,
                    "pillar_type": "theme",
                    "statement": "Unsupported pillar type.",
                }
            ]
        )
