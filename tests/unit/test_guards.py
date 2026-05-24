from system.guards import GuardEvaluator


def valid_audience_profile():
    return {
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


def test_audience_psychology_guard_passes_with_valid_profile():
    result = GuardEvaluator().evaluate(
        "audience_psychology_adequate",
        {"project": {"audience_profile": valid_audience_profile()}},
    )

    assert result.passed is True
    assert result.reason is None


def test_audience_psychology_guard_fails_with_missing_profile():
    result = GuardEvaluator().evaluate(
        "audience_psychology_adequate",
        {"project": {}},
    )

    assert result.passed is False
    assert "audience_profile" in result.reason


def test_audience_psychology_guard_fails_with_invalid_profile():
    profile = valid_audience_profile()
    profile["risk_tolerance"] = "reckless"

    result = GuardEvaluator().evaluate(
        "audience_psychology_adequate",
        {"project": {"audience_profile": profile}},
    )

    assert result.passed is False
    assert "risk_tolerance" in result.reason


def test_unknown_guard_fails_closed_when_not_supplied():
    result = GuardEvaluator().evaluate("rubric_above_3_5", {"guards": {}})

    assert result.passed is False
    assert "not satisfied" in result.reason


def test_unknown_guard_passes_when_supplied_by_context():
    result = GuardEvaluator().evaluate("rubric_above_3_5", {"guards": {"rubric_above_3_5": True}})

    assert result.passed is True
