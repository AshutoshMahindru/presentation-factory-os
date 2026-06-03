from deck_builder.slide_master_engine import SlideMasterEngine


def test_slide_master_assigns_chart_led_executive_layout():
    slide = {
        "materiality": "high",
        "content": {
            "headline": "Margin bridge",
            "body": "The bridge isolates expansion by cohort.",
            "chart_id": "chart_001",
        },
    }

    decision = SlideMasterEngine().assign(slide)

    assert decision.master == "executive-evidence"
    assert decision.layout == "chart-led"
    assert decision.cognitive_load_band in {"low", "moderate"}


def test_slide_master_marks_high_load_for_simplification():
    slide = {
        "materiality": "medium",
        "content": {
            "headline": "A" * 120,
            "body": " ".join(["dense"] * 100),
            "bullets": ["one", "two", "three", "four", "five", "six", "seven"],
            "charts": ["a", "b", "c"],
        },
    }

    decision = SlideMasterEngine().assign(slide)

    assert decision.layout == "chart-led"
    assert decision.cognitive_load_band == "high"
    assert "requires_simplification" in decision.findings
