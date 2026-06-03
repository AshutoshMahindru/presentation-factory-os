from __future__ import annotations

from typing import Any


def validate_visual_qa_result(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("status") not in {"passed", "failed"}:
        errors.append("status must be passed or failed")
    score = result.get("score")
    if not isinstance(score, int | float) or not 0 <= float(score) <= 1:
        errors.append("score must be between 0 and 1")
    findings = result.get("findings", ())
    if not isinstance(findings, (list, tuple)):
        errors.append("findings must be a list or tuple")
    return errors
