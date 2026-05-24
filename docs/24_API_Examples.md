# API Examples

These payloads are implementation accelerators for the workflow-service and approval API. They are examples, not relaxed contracts. Runtime validation must still use SQL constraints, JSON Schema, and `08_StateMachine_Spec.yaml` guards.

## API versioning strategy

All client requests should send an explicit media-type version. v3.2.4 uses:

```http
Accept: application/vnd.pfos.v3.2.4+json
Content-Type: application/vnd.pfos.v3.2.4+json
```

The workflow-service may accept `application/json` in local development, but CI contract tests must use the versioned media type.

## 1. Create project

### Endpoint

```http
POST /projects
Accept: application/vnd.pfos.v3.2.4+json
Content-Type: application/vnd.pfos.v3.2.4+json
```

### Request

```json
{
  "name": "Series A IC Deck - Mobile Pizza Platform",
  "audience": "Risk-aware investment committee evaluating a capital allocation decision",
  "audience_profile": {
    "decision_maker_type": "ic_partner",
    "risk_tolerance": "medium",
    "familiarity_with_topic": "informed",
    "known_objections": ["team_risk", "market_size", "timing"],
    "stakeholder_map": [
      {
        "role": "economic_buyer",
        "concern": "return on invested capital"
      },
      {
        "role": "technical_evaluator",
        "concern": "operational scalability"
      }
    ]
  },
  "objection_preemption_map": {
    "team_risk": {
      "planned_response": "Show advisor/operator coverage and phased execution gates",
      "target_phase": "narrative"
    },
    "market_size": {
      "planned_response": "Triangulate TAM/SAM/SOM with sourced demand proxies",
      "target_phase": "research"
    }
  }
}
```

### Successful response

```json
{
  "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
  "phase": "created",
  "audience_profile_valid": true
}
```

### Failure response: invalid audience profile

```json
{
  "error": "validation_failed",
  "message": "audience_profile is missing required field: known_objections",
  "blocking_gate": "audience_psychology_adequate"
}
```

## 2. Request phase transition

### Endpoint

```http
POST /projects/{project_id}/phase-transitions
Accept: application/vnd.pfos.v3.2.4+json
Content-Type: application/vnd.pfos.v3.2.4+json
```

### Request

```json
{
  "from_phase": "intake",
  "to_phase": "strategy",
  "transition_kind": "forward",
  "requested_by": "analyst@example.com",
  "reason": "Brief, audience profile, and decision definition are complete.",
  "guard_context": {
    "guards": {
      "rubric_above_3_5": true,
      "thesis_audience_aligned": true
    },
    "rubric_score_id": "3ebec5e5-ec8e-45c0-ae80-ff4b02bfaa87",
    "approval_snapshot_id": "b4ea8e85-b2cc-47e7-9860-f5b85e64ea71"
  }
}
```

### Successful response

```json
{
  "transition_id": "8a2f939f-859c-4e7a-9d9c-ff75ee6e29c9",
  "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
  "from_phase": "intake",
  "to_phase": "strategy",
  "status": "applied",
  "guards": [
    {"name": "rubric_above_3_5", "status": "pass"},
    {"name": "thesis_audience_aligned", "status": "pass"},
    {"name": "audience_psychology_adequate", "status": "pass"},
    {"name": "no_blocking_rules", "status": "pass"}
  ]
}
```

### Failure response: outbox not drained

```json
{
  "error": "transition_blocked",
  "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
  "from_phase": "review",
  "to_phase": "approved",
  "blocking_guards": [
    {
      "name": "no_blocking_rules",
      "reason": "project_has_unprocessed_outbox_rows",
      "unprocessed_outbox_count": 2
    }
  ]
}
```

## 3. Submit approval

### Endpoint

```http
POST /projects/{project_id}/approvals
Accept: application/vnd.pfos.v3.2.4+json
Content-Type: application/vnd.pfos.v3.2.4+json
```

### Request

```json
{
  "phase": "review",
  "actor_email": "ic.member@example.com",
  "role": "ic_member",
  "decision": "approved",
  "rubric_score_snapshot": {
    "overall_score": 4.25,
    "source_traceability": 4.5,
    "financial_validation": 4.2,
    "visual_qa": 4.1,
    "deck_completeness": 4.2
  },
  "notes": "Approved for IC circulation. Confirm final source appendix remains attached at export."
}
```

### Successful response

```json
{
  "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
  "phase": "review",
  "approval_recorded": true,
  "quorum_met": false,
  "approved_count": 1,
  "rejected_count": 0,
  "changes_requested_count": 0,
  "missing_roles": {},
  "blocking_rejection": false
}
```

## 4. Get approval status

### Endpoint

```http
GET /projects/{project_id}/approvals/status/{phase}
Accept: application/vnd.pfos.v3.2.4+json
```

### Successful response

```json
{
  "project_id": "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5",
  "phase": "review",
  "quorum_met": true,
  "decision_rule": "unanimous",
  "required_count": 2,
  "approved_count": 2,
  "rejected_count": 0,
  "abstained_count": 0,
  "changes_requested_count": 0,
  "missing_roles": {},
  "blocking_rejection": false,
  "escalation_status": "none",
  "escalation_reason": null
}
```

### Failure response: phase-scoped quorum violation

```json
{
  "error": "approval_not_counted_for_quorum",
  "message": "Approval was created before latest entry into review phase and cannot count toward current review quorum.",
  "phase": "review",
  "required_action": "submit_new_phase_scoped_approval"
}
```
