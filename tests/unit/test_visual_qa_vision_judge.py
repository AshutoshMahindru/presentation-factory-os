from deck_builder.visual_qa import LocalVisionJudge, VisionJudgeResult, judge_visual


def slide():
    return {
        "slide_id": "slide_001",
        "materiality": "medium",
        "visual_quality": "code_generated",
        "content": {
            "headline": "Pricing power remains intact",
            "body": "Survey evidence supports the pricing thesis.",
            "evidence_refs": ["src_001"],
        },
    }


class FakeJudge:
    def judge(self, deck_or_slide):
        return VisionJudgeResult(
            status="passed",
            score=0.88,
            rationale="mocked",
            findings=("mocked_contract",),
            judge="fake",
        )


def test_local_vision_judge_uses_deterministic_fallback():
    result = LocalVisionJudge().judge(slide())

    assert result.status == "passed"
    assert result.judge == "local-deterministic"
    assert "deterministic" in result.rationale


def test_judge_visual_accepts_pluggable_judge_without_remote_keys():
    result = judge_visual(slide(), judge=FakeJudge())

    assert result.status == "passed"
    assert result.findings == ("mocked_contract",)
    assert result.judge == "fake"
