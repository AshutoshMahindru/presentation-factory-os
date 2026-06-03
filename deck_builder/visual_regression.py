from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from deck_builder.render_web_deck import render_web_deck


@dataclass(frozen=True)
class VisualRegressionResult:
    passed: bool
    diff_ratio: float
    baseline_hash: str
    candidate_hash: str


def reference_hash(deck: dict[str, Any]) -> str:
    return render_web_deck(deck).content_hash


def compare_hashes(baseline_hash: str, candidate_hash: str) -> VisualRegressionResult:
    if len(baseline_hash) != len(candidate_hash):
        diff_ratio = 1.0
    else:
        changed = sum(1 for left, right in zip(baseline_hash, candidate_hash, strict=True) if left != right)
        diff_ratio = round(changed / max(1, len(baseline_hash)), 3)
    return VisualRegressionResult(
        passed=diff_ratio == 0.0,
        diff_ratio=diff_ratio,
        baseline_hash=baseline_hash,
        candidate_hash=candidate_hash,
    )


def compare_decks(baseline: dict[str, Any], candidate: dict[str, Any]) -> VisualRegressionResult:
    return compare_hashes(reference_hash(baseline), reference_hash(candidate))
