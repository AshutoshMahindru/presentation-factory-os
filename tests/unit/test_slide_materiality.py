from deck_builder.slide_factory import build_slide_jobs_from_pillars, derive_materiality


def test_derive_materiality_honors_valid_explicit_value() -> None:
    assert derive_materiality({"pillar_type": "financial", "materiality": "low"}) == "low"


def test_derive_materiality_uses_type_defaults() -> None:
    assert derive_materiality({"pillar_type": "data"}) == "high"
    assert derive_materiality({"pillar_type": "financial"}) == "high"
    assert derive_materiality({"pillar_type": "claim"}) == "medium"
    assert derive_materiality({"pillar_type": "objection"}) == "medium"
    assert derive_materiality({"pillar_type": "narrative"}) == "low"


def test_slide_mapping_carries_materiality_into_each_slide_job() -> None:
    slides = build_slide_jobs_from_pillars(
        [
            {
                "id": "pillar-data",
                "pillar_index": 0,
                "pillar_type": "data",
                "statement": "The category is expanding quickly.",
            },
            {
                "id": "pillar-narrative",
                "pillar_index": 1,
                "pillar_type": "narrative",
                "statement": "The buyer story is founder-led.",
                "materiality": "medium",
            },
        ],
        source_refs_by_pillar={
            "pillar-data": ["source_data"],
            "pillar-narrative": ["source_story"],
        },
    )

    assert [slide["materiality"] for slide in slides] == ["high", "medium"]
