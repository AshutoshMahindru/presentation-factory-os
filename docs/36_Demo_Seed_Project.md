# Demo Seed Project

Baby Step 87 adds a canonical local/operator seed project for PFOS v3.2.4:

- Fixture: `tests/fixtures/demo_project.json`
- Loader: `scripts/seed_demo_project.py`
- Demo name: `Series A IC Deck - Mobile Pizza Platform`

The seed is derived from the `POST /projects` example in
`docs/24_API_Examples.md`. It keeps the same investment-committee deck premise
and normalizes the stakeholder role to the enforced audience profile schema
enum, `technical_evaluator`.

## Validate the Fixture Only

Use this mode when Docker or the workflow-service is not running:

```bash
python3 scripts/seed_demo_project.py
```

The script validates:

- the fixture is valid JSON;
- the versioned PFOS v3.2.4 media type is present;
- the project payload includes the required `POST /projects` fields;
- `audience_profile` passes `docs/22_AudienceProfile.schema.json`;
- the fixture explicitly states that it is not a successful export.

## Load Through the Live Workflow API

Start the local stack and apply the existing database schema using the normal
local validation path. Then post the seed through the real API:

```bash
make docker-up
make validate-sql-live
python3 scripts/seed_demo_project.py --api-base-url http://localhost:8000
```

The loader calls:

```http
POST /projects
Accept: application/vnd.pfos.v3.2.4+json
Content-Type: application/vnd.pfos.v3.2.4+json
```

It treats the seed as loaded only when the workflow-service returns a
`project_id`, `phase = created`, and `audience_profile_valid = true`.

## Operator Follow-Up Checks

After a project is created, use the returned `project_id` with the existing
control-plane surfaces:

```bash
curl -H 'Accept: application/vnd.pfos.v3.2.4+json' \
  http://localhost:8000/health/projects/${PROJECT_ID}/outbox

curl -H 'Accept: application/vnd.pfos.v3.2.4+json' \
  http://localhost:8000/health/projects/${PROJECT_ID}/source-retractions

curl -H 'Accept: application/vnd.pfos.v3.2.4+json' \
  http://localhost:8000/health/projects/${PROJECT_ID}/hard-gates

curl -H 'Accept: application/vnd.pfos.v3.2.4+json' \
  http://localhost:8000/projects/${PROJECT_ID}/approvals/status/review
```

This seed creates an initial project only. It does not create approvals, drain
queues, move phases, or mark export success. Any export demo must use the
existing deck/export validation gates.
