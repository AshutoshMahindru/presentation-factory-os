from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from deck_builder.visual_qa_deterministic import DeterministicVisualQA


@dataclass(frozen=True)
class VisionJudgeResult:
    status: str
    score: float
    rationale: str
    findings: tuple[str, ...]
    judge: str


class VisionJudge(Protocol):
    def judge(self, deck_or_slide: dict[str, Any]) -> VisionJudgeResult:
        ...


class LocalVisionJudge:
    """Vision judge fallback used when no remote vision model is configured."""

    def __init__(self, qa: DeterministicVisualQA | None = None) -> None:
        self.qa = qa or DeterministicVisualQA()

    def judge(self, deck_or_slide: dict[str, Any]) -> VisionJudgeResult:
        if "slides" in deck_or_slide:
            result = self.qa.score_deck(deck_or_slide)
        else:
            result = self.qa.score_slide(deck_or_slide)
        rationale = "local deterministic visual quality checks"
        return VisionJudgeResult(
            status=result.status,
            score=result.score,
            rationale=rationale,
            findings=result.findings,
            judge="local-deterministic",
        )


def judge_visual(deck_or_slide: dict[str, Any], judge: VisionJudge | None = None) -> VisionJudgeResult:
    active_judge = judge or LocalVisionJudge()
    return active_judge.judge(deck_or_slide)
