from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from system.audience_profile_validator import AudienceProfileValidator


DEFAULT_FIXTURE_PATH = Path("tests/fixtures/demo_project.json")
DEFAULT_TIMEOUT_SECONDS = 10.0
VERSIONED_MEDIA_TYPE = "application/vnd.pfos.v3.2.4+json"


class DemoSeedError(Exception):
    """Raised when the demo seed cannot be validated or loaded."""


@dataclass(frozen=True)
class DemoSeed:
    seed_id: str
    media_type: str
    project: dict[str, Any]
    operator_validation: dict[str, Any]


def load_seed(path: str | Path = DEFAULT_FIXTURE_PATH) -> DemoSeed:
    fixture_path = Path(path)
    try:
        raw_seed = json.loads(fixture_path.read_text())
    except FileNotFoundError as exc:
        raise DemoSeedError(f"demo seed fixture not found: {fixture_path}") from exc
    except json.JSONDecodeError as exc:
        raise DemoSeedError(f"demo seed fixture is not valid JSON: {fixture_path}: {exc}") from exc

    if not isinstance(raw_seed, dict):
        raise DemoSeedError("demo seed fixture root must be an object")

    try:
        seed_id = _required_string(raw_seed, "seed_id")
        media_type = _required_string(raw_seed, "media_type")
        project = _required_mapping(raw_seed, "project")
        operator_validation = _required_mapping(raw_seed, "operator_validation")
    except TypeError as exc:
        raise DemoSeedError(str(exc)) from exc

    return DemoSeed(
        seed_id=seed_id,
        media_type=media_type,
        project=dict(project),
        operator_validation=dict(operator_validation),
    )


def validate_seed(seed: DemoSeed, validator: AudienceProfileValidator | None = None) -> None:
    if seed.media_type != VERSIONED_MEDIA_TYPE:
        raise DemoSeedError(
            f"demo seed media_type must be {VERSIONED_MEDIA_TYPE}, got {seed.media_type}"
        )

    required_project_fields = ("name", "audience", "audience_profile", "objection_preemption_map")
    missing_fields = [field for field in required_project_fields if field not in seed.project]
    if missing_fields:
        raise DemoSeedError(f"demo seed project is missing fields: {', '.join(missing_fields)}")

    audience_profile = seed.project["audience_profile"]
    if not isinstance(audience_profile, dict):
        raise DemoSeedError("demo seed project audience_profile must be an object")

    audience_validator = validator or AudienceProfileValidator.from_file()
    audience_result = audience_validator.validate(audience_profile)
    if not audience_result.valid:
        raise DemoSeedError(
            "demo seed audience_profile failed validation: "
            + "; ".join(audience_result.errors)
        )

    export_note = str(seed.operator_validation.get("export_note", "")).lower()
    if "does not represent a successful export" not in export_note:
        raise DemoSeedError("demo seed must explicitly state that it is not a successful export")


def build_project_request(api_base_url: str, seed: DemoSeed) -> Request:
    base_url = api_base_url.rstrip("/")
    body = json.dumps(seed.project, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return Request(
        f"{base_url}/projects",
        data=body,
        method="POST",
        headers={
            "Accept": seed.media_type,
            "Content-Type": seed.media_type,
        },
    )


def create_project(
    api_base_url: str,
    seed: DemoSeed,
    opener: Callable[..., Any] = urlopen,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    request = build_project_request(api_base_url, seed)
    try:
        with opener(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            status = getattr(response, "status", getattr(response, "code", None))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise DemoSeedError(f"workflow API rejected demo seed with HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise DemoSeedError(f"workflow API unavailable: {exc.reason}") from exc

    if status is not None and not 200 <= int(status) < 300:
        raise DemoSeedError(f"workflow API returned HTTP {status}: {response_body}")

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise DemoSeedError(f"workflow API returned non-JSON response: {response_body}") from exc

    if not payload.get("project_id"):
        raise DemoSeedError(f"workflow API response did not include project_id: {payload}")
    if payload.get("phase") != seed.operator_validation.get("expected_initial_phase"):
        raise DemoSeedError(
            "workflow API response phase did not match expected_initial_phase: "
            f"{payload.get('phase')}"
        )
    if payload.get("audience_profile_valid") is not True:
        raise DemoSeedError("workflow API did not confirm audience_profile_valid=true")

    return payload


def render_validation_summary(seed: DemoSeed) -> str:
    endpoints = "\n".join(
        f"- {endpoint}" for endpoint in seed.operator_validation["recommended_follow_up_endpoints"]
    )
    return (
        f"DEMO_SEED_VALID=1\n"
        f"seed_id={seed.seed_id}\n"
        f"project_name={seed.project['name']}\n"
        f"load_path={seed.operator_validation['create_project_endpoint']}\n"
        f"expected_initial_phase={seed.operator_validation['expected_initial_phase']}\n"
        "recommended_follow_up_endpoints:\n"
        f"{endpoints}\n"
        f"export_note={seed.operator_validation['export_note']}"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optionally load the canonical PFOS demo project seed."
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE_PATH),
        help="Path to the demo seed JSON fixture.",
    )
    parser.add_argument(
        "--api-base-url",
        help="Workflow-service base URL. When omitted, the script validates the fixture only.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout used when --api-base-url is provided.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or []))
    try:
        seed = load_seed(args.fixture)
        validate_seed(seed)

        if not args.api_base_url:
            print(render_validation_summary(seed))
            return 0

        response_payload = create_project(
            api_base_url=args.api_base_url,
            seed=seed,
            timeout_seconds=args.timeout_seconds,
        )
    except DemoSeedError as exc:
        print(f"DEMO_SEED_VALID=0\nerror={exc}", file=sys.stderr)
        return 1

    print(
        "DEMO_PROJECT_CREATED=1\n"
        f"seed_id={seed.seed_id}\n"
        f"project_id={response_payload['project_id']}\n"
        f"phase={response_payload['phase']}\n"
        f"audience_profile_valid={response_payload['audience_profile_valid']}"
    )
    return 0


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"demo seed requires non-empty string field: {key}")
    return value


def _required_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"demo seed requires object field: {key}")
    return value


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
