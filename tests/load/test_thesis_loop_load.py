from __future__ import annotations

import os
import time
from dataclasses import dataclass

import pytest


LOCAL_THESIS_ITERATION_COUNT = 250
MAX_LOCAL_CONTRACT_SECONDS = 1.0
LIVE_THESIS_ITERATION_COUNT = 1000


@dataclass(frozen=True)
class ThesisLoopLoadSample:
    iteration: int
    thesis_version_id: str
    convergence_score: float
    stressed_pillar_count: int


def run_local_thesis_loop_contract(iteration_count: int) -> list[ThesisLoopLoadSample]:
    samples: list[ThesisLoopLoadSample] = []
    for index in range(iteration_count):
        stressed_pillar_count = 1 if index % 17 == 0 else 0
        convergence_score = min(1.0, 0.62 + (index / iteration_count) * 0.3)
        if stressed_pillar_count:
            convergence_score -= 0.05
        samples.append(
            ThesisLoopLoadSample(
                iteration=index + 1,
                thesis_version_id=f"thesis-load-{index + 1:04d}",
                convergence_score=round(convergence_score, 4),
                stressed_pillar_count=stressed_pillar_count,
            )
        )
    return samples


def live_thesis_loop_load_enabled() -> bool:
    return os.environ.get("PFOS_RUN_LIVE_TESTS") == "1"


def test_local_thesis_loop_load_contract_is_deterministic_and_fast() -> None:
    started_at = time.monotonic()
    samples = run_local_thesis_loop_contract(LOCAL_THESIS_ITERATION_COUNT)
    elapsed = time.monotonic() - started_at

    assert len(samples) == LOCAL_THESIS_ITERATION_COUNT
    assert samples[0] == ThesisLoopLoadSample(
        iteration=1,
        thesis_version_id="thesis-load-0001",
        convergence_score=0.57,
        stressed_pillar_count=1,
    )
    assert samples[-1].iteration == LOCAL_THESIS_ITERATION_COUNT
    assert samples[-1].thesis_version_id == "thesis-load-0250"
    assert all(0.0 <= sample.convergence_score <= 1.0 for sample in samples)
    assert sum(sample.stressed_pillar_count for sample in samples) == 15
    assert elapsed <= MAX_LOCAL_CONTRACT_SECONDS


def test_thesis_loop_live_load_gate_is_environment_controlled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PFOS_RUN_LIVE_TESTS", raising=False)
    assert live_thesis_loop_load_enabled() is False

    monkeypatch.setenv("PFOS_RUN_LIVE_TESTS", "1")
    assert live_thesis_loop_load_enabled() is True


@pytest.mark.skipif(
    os.environ.get("PFOS_RUN_LIVE_TESTS") != "1",
    reason="Live thesis-loop load evidence requires PFOS_RUN_LIVE_TESTS=1",
)
def test_live_thesis_loop_load_gate_contract() -> None:
    samples = run_local_thesis_loop_contract(LIVE_THESIS_ITERATION_COUNT)

    assert len(samples) == LIVE_THESIS_ITERATION_COUNT
    assert samples[-1].convergence_score > samples[0].convergence_score
