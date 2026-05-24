import pytest

from system.state_machine import (
    InvalidPhaseError,
    InvalidTransitionError,
    MissingRetreatReasonError,
    StateMachine,
    TerminalPhaseError,
)


def test_loads_state_machine_spec():
    sm = StateMachine.from_yaml()
    assert sm.version == "3.2.4"
    assert "intake" in sm.phases
    assert "exported" in sm.phases


def test_valid_forward_transition_passes():
    sm = StateMachine.from_yaml()
    transition = sm.validate_transition("created", "intake", "forward")
    assert transition.from_phase == "created"
    assert transition.to_phase == "intake"
    assert transition.kind == "forward"


def test_invalid_forward_transition_fails():
    sm = StateMachine.from_yaml()
    with pytest.raises(InvalidTransitionError):
        sm.validate_transition("intake", "financial_model", "forward")


def test_unknown_phase_fails():
    sm = StateMachine.from_yaml()
    with pytest.raises(InvalidPhaseError):
        sm.validate_transition("made_up_phase", "intake", "forward")


def test_retreat_requires_reason():
    sm = StateMachine.from_yaml()
    with pytest.raises(MissingRetreatReasonError):
        sm.validate_transition("strategy", "intake", "retreat")


def test_retreat_with_reason_passes():
    sm = StateMachine.from_yaml()
    transition = sm.validate_transition(
        "strategy",
        "intake",
        "retreat",
        reason="Brief is incomplete.",
    )
    assert transition.kind == "retreat"


def test_rejected_is_terminal():
    sm = StateMachine.from_yaml()
    with pytest.raises(TerminalPhaseError):
        sm.validate_transition("rejected", "intake", "forward")


def test_exported_is_terminal():
    sm = StateMachine.from_yaml()
    with pytest.raises(TerminalPhaseError):
        sm.validate_transition("exported", "review", "retreat")


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


def test_transition_with_guards_passes_when_all_guards_satisfied():
    from system.state_machine import GuardFailedError

    sm = StateMachine.from_yaml()
    transition, guard_results = sm.validate_transition_with_guards(
        "intake",
        "strategy",
        "forward",
        context={
            "project": {"audience_profile": valid_audience_profile()},
            "guards": {
                "rubric_above_3_5": True,
                "thesis_audience_aligned": True,
                "no_blocking_rules": True,
            },
        },
    )

    assert transition.from_phase == "intake"
    assert transition.to_phase == "strategy"
    assert all(result.passed for result in guard_results)


def test_transition_with_guards_fails_when_audience_profile_invalid():
    from system.state_machine import GuardFailedError

    sm = StateMachine.from_yaml()
    profile = valid_audience_profile()
    profile["risk_tolerance"] = "reckless"

    with pytest.raises(GuardFailedError) as exc:
        sm.validate_transition_with_guards(
            "intake",
            "strategy",
            "forward",
            context={
                "project": {"audience_profile": profile},
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                    "no_blocking_rules": True,
                },
            },
        )

    assert "audience_psychology_adequate" in str(exc.value)


def test_transition_with_guards_fails_closed_when_context_guard_missing():
    from system.state_machine import GuardFailedError

    sm = StateMachine.from_yaml()

    with pytest.raises(GuardFailedError) as exc:
        sm.validate_transition_with_guards(
            "intake",
            "strategy",
            "forward",
            context={
                "project": {"audience_profile": valid_audience_profile()},
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                },
            },
        )

    assert "no_blocking_rules" in str(exc.value)
