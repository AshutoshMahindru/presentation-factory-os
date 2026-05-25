from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import seed_demo_project
from scripts.seed_demo_project import DemoSeed, DemoSeedError
from system.audience_profile_validator import AudienceProfileValidator


class FakeHttpResponse:
    status = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_demo_fixture_loads_and_validates_against_audience_schema() -> None:
    seed = seed_demo_project.load_seed()

    seed_demo_project.validate_seed(seed)

    assert seed.seed_id == "pfos_v3_2_4_mobile_pizza_series_a_ic_deck"
    assert seed.project["name"] == "Series A IC Deck - Mobile Pizza Platform"
    assert seed.project["audience_profile"]["stakeholder_map"][1]["role"] == "technical_evaluator"


def test_build_project_request_posts_versioned_create_project_payload() -> None:
    seed = seed_demo_project.load_seed()
    request = seed_demo_project.build_project_request("http://localhost:8000/", seed)

    assert request.full_url == "http://localhost:8000/projects"
    assert request.get_method() == "POST"
    assert request.get_header("Accept") == seed_demo_project.VERSIONED_MEDIA_TYPE
    assert request.get_header("Content-type") == seed_demo_project.VERSIONED_MEDIA_TYPE

    body = json.loads(request.data.decode("utf-8"))
    assert body == seed.project
    assert "project_id" not in body
    assert "exported" not in json.dumps(body).lower()


def test_create_project_requires_real_api_created_response() -> None:
    seed = seed_demo_project.load_seed()
    captured_requests = []

    def opener(request: object, timeout: float) -> FakeHttpResponse:
        captured_requests.append((request, timeout))
        return FakeHttpResponse(
            {
                "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
                "phase": "created",
                "audience_profile_valid": True,
            }
        )

    payload = seed_demo_project.create_project(
        "http://workflow-service:8000",
        seed,
        opener=opener,
        timeout_seconds=3.0,
    )

    assert payload["project_id"] == "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5"
    assert captured_requests[0][1] == 3.0


@pytest.mark.parametrize(
    "response_payload, expected_error",
    [
        ({"phase": "created", "audience_profile_valid": True}, "project_id"),
        (
            {
                "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
                "phase": "exported",
                "audience_profile_valid": True,
            },
            "expected_initial_phase",
        ),
        (
            {
                "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
                "phase": "created",
                "audience_profile_valid": False,
            },
            "audience_profile_valid=true",
        ),
    ],
)
def test_create_project_rejects_unvalidated_or_export_like_responses(
    response_payload: dict[str, Any],
    expected_error: str,
) -> None:
    seed = seed_demo_project.load_seed()

    def opener(request: object, timeout: float) -> FakeHttpResponse:
        return FakeHttpResponse(response_payload)

    with pytest.raises(DemoSeedError, match=expected_error):
        seed_demo_project.create_project("http://localhost:8000", seed, opener=opener)


def test_validate_seed_rejects_invalid_audience_profile() -> None:
    seed = seed_demo_project.load_seed()
    invalid_seed = DemoSeed(
        seed_id=seed.seed_id,
        media_type=seed.media_type,
        project={
            **seed.project,
            "audience_profile": {
                **seed.project["audience_profile"],
                "stakeholder_map": [{"role": "technical_reviewer", "concern": "scalability"}],
            },
        },
        operator_validation=seed.operator_validation,
    )

    with pytest.raises(DemoSeedError, match="audience_profile failed validation"):
        seed_demo_project.validate_seed(invalid_seed, AudienceProfileValidator.from_file())


def test_validate_seed_rejects_missing_export_disclaimer() -> None:
    seed = seed_demo_project.load_seed()
    invalid_seed = DemoSeed(
        seed_id=seed.seed_id,
        media_type=seed.media_type,
        project=seed.project,
        operator_validation={**seed.operator_validation, "export_note": ""},
    )

    with pytest.raises(DemoSeedError, match="not a successful export"):
        seed_demo_project.validate_seed(invalid_seed)


def test_main_validates_fixture_without_api_call(capsys) -> None:
    exit_code = seed_demo_project.main([])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "DEMO_SEED_VALID=1" in output
    assert "load_path=POST /projects" in output
    assert "does not represent a successful export" in output


def test_load_seed_reports_malformed_json(tmp_path: Path) -> None:
    fixture = tmp_path / "demo_project.json"
    fixture.write_text("{not-json")

    with pytest.raises(DemoSeedError, match="not valid JSON"):
        seed_demo_project.load_seed(fixture)
