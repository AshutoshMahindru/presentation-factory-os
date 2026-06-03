import pytest

from system.audience_profile_validator import (
    AudienceProfileValidationError,
    AudienceProfileValidator,
)


def valid_profile(**overrides):
    profile = {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["pricing", "timing", "team_risk"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "roi",
            }
        ],
    }
    profile.update(overrides)
    return profile


def test_valid_audience_profile_passes():
    result = AudienceProfileValidator.from_file().validate(valid_profile())
    assert result.valid is True
    assert result.errors == ()


def test_missing_decision_maker_type_fails():
    profile = valid_profile()
    del profile["decision_maker_type"]

    result = AudienceProfileValidator.from_file().validate(profile)

    assert result.valid is False
    assert any("decision_maker_type" in error for error in result.errors)


def test_invalid_risk_tolerance_fails():
    profile = valid_profile(risk_tolerance="reckless")

    with pytest.raises(AudienceProfileValidationError):
        AudienceProfileValidator.from_file().assert_valid(profile)


def test_known_objections_must_be_array():
    profile = valid_profile(known_objections="pricing")

    result = AudienceProfileValidator.from_file().validate(profile)

    assert result.valid is False
    assert any("known_objections" in error for error in result.errors)


def test_known_objections_may_be_empty():
    result = AudienceProfileValidator.from_file().validate(
        valid_profile(known_objections=[])
    )

    assert result.valid is True
    assert result.errors == ()


def test_stakeholder_map_must_have_at_least_one_member():
    profile = valid_profile(stakeholder_map=[])

    result = AudienceProfileValidator.from_file().validate(profile)

    assert result.valid is False
    assert any("stakeholder_map" in error for error in result.errors)


def test_stakeholder_map_requires_role_and_concern():
    profile = valid_profile(stakeholder_map=[{"role": "economic_buyer"}])

    result = AudienceProfileValidator.from_file().validate(profile)

    assert result.valid is False
    assert any("stakeholder_map" in error or "concern" in error for error in result.errors)


def test_additional_property_fails():
    profile = valid_profile()
    profile["random"] = "not allowed"

    result = AudienceProfileValidator.from_file().validate(profile)

    assert result.valid is False
    assert any("Additional properties" in error or "<root>" in error for error in result.errors)


def test_invalid_stakeholder_influence_level_fails():
    profile = valid_profile(
        stakeholder_map=[
            {
                "role": "economic_buyer",
                "concern": "roi",
                "influence_level": "dominant",
            }
        ]
    )

    result = AudienceProfileValidator.from_file().validate(profile)

    assert result.valid is False
    assert any("influence_level" in error for error in result.errors)
