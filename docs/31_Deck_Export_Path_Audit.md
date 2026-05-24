# Deck Export Path Audit

Baby Step 72 audit for PFOS v3.2.4.

## Scope

This audit inspects the current deck/export path before changing export behavior. It covers:

- `deck_builder/slide_schema_validator.py`
- `deck_builder/narrative_arc_validator.py`
- `deck_builder/export_gate.py`
- `deck_builder/render_python_pptx.py`
- `deck_builder/render_pptxgenjs.ts`
- `tests/unit/test_export_gate.py`
- `tests/unit/test_slide_schema.py`
- `tests/unit/test_narrative_arc_validator.py`
- `tests/integration/test_end_to_end_brief_to_export.py`

Adjacent specs and validators were checked only to identify export-readiness gaps:

- `docs/06_SlideJobDefinition.schema.json`
- `docs/08_StateMachine_Spec.yaml`
- `docs/09_Financial_Model_Schema.yaml`
- `docs/12_Tool_Server_Degradation_Policy.yaml`
- `financial_model/slide_numeric_assertion_checker.py`

No export behavior was changed in this step.

## Current Implementation Summary

| Area | Current status | Evidence |
| --- | --- | --- |
| Slide schema validation | Implemented for individual slide payloads through JSON Schema. | `SlideSchemaValidator.from_file()` loads `docs/06_SlideJobDefinition.schema.json`; `validate()` and `assert_valid()` return deterministic error messages. |
| `visual_quality` schema handling | Implemented at schema level. | Schema allows only `code_generated`, `degraded`, and `final_rendered`. |
| `materiality` schema handling | Implemented at schema level. | Schema requires `materiality` and allows only `high`, `medium`, and `low`. |
| Degraded visual blocking | Partially implemented. | `ExportGate` blocks `degraded` visuals for high/medium materiality slides and warns for low materiality slides. |
| Stale artifact blocking | Partially implemented. | `ExportGate` blocks artifacts whose in-memory status is `stale_due_to_retreat`. |
| Missing source attribution blocking | Partially implemented. | `ExportGate` blocks high/medium materiality slides with empty `content.evidence_refs`. |
| Unsupported financial claim blocking | Partially implemented outside the export gate. | `financial_model/slide_numeric_assertion_checker.py` requires `financial_refs` when numeric assertions are detected, but `ExportGate` only checks deck-level `financial_validation_status`. |
| Narrative arc validation | Implemented as a small deterministic rule set. | `NarrativeArcValidator` checks non-empty decks, no detailed financial first slide, ask-after-evidence, and objection-before-ask ordering. |
| Source appendix/evidence map readiness | Not implemented. | No renderer or export integrity code assembles or validates a source appendix or evidence map. |
| Financial reference export readiness | Not implemented. | `financial_refs` are schema-supported, but no export renderer or appendix/map generator emits them. |
| Deterministic deck artifact generation readiness | Not implemented. | `deck_builder/render_python_pptx.py` and `deck_builder/render_pptxgenjs.ts` are empty. |

## Detailed Findings

### 1. Slide Schema Validation

Implemented:

- `SlideSchemaValidator` wraps `jsonschema.Draft202012Validator`.
- The schema file is loaded from `docs/06_SlideJobDefinition.schema.json` by default.
- Validation returns a stable `SlideValidationResult(valid, errors)` value.
- `assert_valid()` raises `SlideSchemaValidationError` with joined deterministic messages.
- Unit tests cover a valid payload, missing `materiality`, invalid job type, empty `required_evidence`, headline length, invalid `visual_quality`, and invalid `narrative_arc`.

Remaining gaps:

- The schema validates one slide at a time, not a whole deck envelope.
- The schema allows `content.evidence_refs` to be empty because attribution blocking is deferred to `ExportGate`.
- `content.financial_refs` is optional at schema level, so numeric claim enforcement must be invoked separately.
- There is no export path wiring that guarantees schema validation runs before render/export.

### 2. Visual Quality And Materiality

Implemented:

- `visual_quality` is a required schema field.
- Allowed values are `code_generated`, `degraded`, and `final_rendered`.
- `materiality` is a required schema field.
- Allowed values are `high`, `medium`, and `low`.
- `ExportGate` consumes both fields for degraded visual blocking.

Remaining gaps:

- `ExportGate` trusts in-memory slide dictionaries and does not run schema validation itself.
- Low-materiality degraded visuals only produce a warning; the warning says provenance is required, but no code verifies `slide.provenance` exists or contains render/fallback hashes.
- The deck export fallback policy says outline output is degraded and never a final export, but no renderer/export adapter exists to express this in deck artifacts.

### 3. Degraded Visual Blocking

Implemented:

- High and medium materiality slides with `visual_quality == "degraded"` block export.
- Low materiality slides with `visual_quality == "degraded"` produce warnings but do not block.
- Unit tests cover high-materiality blocking and low-materiality warning behavior.

Remaining gaps:

- The policy file has broader tool-specific rules for charts, diagrams, tables, and deck export fallbacks; `ExportGate` only sees a slide-level `visual_quality` value.
- No code maps renderer failures or fallback ladder outcomes into `visual_quality`.
- No code verifies degraded low-materiality slides include the provenance required by the warning copy.

### 4. Stale Artifact Blocking

Implemented:

- `ExportGate` blocks any artifact in `deck["artifacts"]` with `status == "stale_due_to_retreat"`.
- Unit tests cover this in-memory artifact status.

Remaining gaps:

- `ExportGate` does not query the stale artifact repository or project-scoped hard gate bundle.
- The current check depends on the export caller supplying complete artifact status in the deck dictionary.
- There is no export endpoint or renderer orchestration that re-runs the stale artifact gate at export time.

### 5. Missing Source Attribution Blocking

Implemented:

- `ExportGate` blocks high/medium materiality slides when `content.evidence_refs` is empty.
- Unit tests cover an empty `evidence_refs` list on a high-materiality slide.

Remaining gaps:

- The check verifies reference presence only, not that refs point to active sources.
- It does not verify `job.required_evidence` and `content.evidence_refs` overlap.
- It does not verify Neo4j `SUPPORTED_BY` edges, active source lifecycle status, or minimum support count.
- It does not build or validate the source appendix/evidence map expected by export integrity.

### 6. Unsupported Financial Claim Blocking

Implemented:

- `ExportGate` blocks when deck-level `financial_validation_status` is neither `None` nor `validated`.
- `SlideNumericAssertionChecker` separately detects numeric assertions in slide body copy and requires `content.financial_refs`.
- Unit tests cover numeric claims requiring financial refs.

Remaining gaps:

- `ExportGate` does not invoke `SlideNumericAssertionChecker`.
- A deck with numeric slide assertions and empty `financial_refs` can pass `ExportGate` if `financial_validation_status` is `validated` or omitted.
- `financial_validation_status == None` currently allows export. That may be intentional for non-financial decks, but there is no explicit distinction between "no financial claims present" and "financial validation not run".
- There is no check that `financial_refs` point to validated financial cells.
- There is no exported financial reference map.

### 7. Narrative Arc Validation

Implemented:

- Empty decks fail.
- A deck cannot start with `explain_unit_economics` or `show_capital_gate`.
- `request_decision` cannot appear before an evidence job type.
- `address_risk` must appear before the first request-decision slide when both are present.
- Unit tests cover the implemented rules.

Remaining gaps:

- Narrative validation is not wired into export gating or render orchestration.
- The rule set uses `job.type`, not the optional `narrative_arc` schema tag.
- `define_strategic_path` is a valid schema job type but is not classified as evidence, ask, financial, or objection.
- There is no deck-level narrative contract describing required sections, maximum slide count, appendix behavior, or export order.

### 8. Source Appendix And Evidence Map Readiness

Not ready.

Observed gaps:

- `render_python_pptx.py` is empty.
- `render_pptxgenjs.ts` is empty.
- `tests/integration/test_end_to_end_brief_to_export.py` is empty.
- No inspected code builds a source appendix.
- No inspected code builds an evidence map from slide claims to active source refs.
- No inspected code validates appendix completeness before export.

Required before export behavior changes:

- Define a deterministic source appendix artifact structure.
- Define an evidence map structure keyed by slide id and claim/ref id.
- Verify every material claim maps to active source evidence.
- Make export integrity fail if source appendix or evidence map is missing or incomplete.

### 9. Financial Reference Export Readiness

Not ready.

Observed gaps:

- `financial_refs` exist in the slide schema and numeric assertion checker, but renderers are empty.
- No inspected code emits financial refs into a deck appendix, notes section, metadata file, or sidecar map.
- No inspected code checks that every `financial_ref` resolves to a validated `financial_cells.cell_ref`.
- No inspected code binds financial validation output to export artifact generation.

Required before export behavior changes:

- Define a deterministic financial reference map format.
- Require numeric claim validation in the export path.
- Resolve `financial_refs` against validated financial cells.
- Include the map in exported artifact metadata or appendix output.

### 10. Deterministic Deck Artifact Generation Readiness

Not ready.

Observed gaps:

- `deck_builder/render_python_pptx.py` is empty.
- `deck_builder/render_pptxgenjs.ts` is empty.
- `deck_builder/app.py` is empty.
- `tool_server/export.py` is empty.
- `api/exports.py` is empty.
- `tests/integration/test_end_to_end_brief_to_export.py` is empty.

Required before export behavior changes:

- Choose and implement the primary deterministic renderer interface.
- Define an artifact manifest with input hash, output hash, renderer name/version, source appendix status, financial reference map status, and visual degradation status.
- Ensure export gating runs after all validation inputs are materialized and before artifact finalization.
- Add an end-to-end test that exercises brief-to-export through schema validation, narrative validation, export gate, renderer output, and artifact manifest checks.

## Exact Remaining Implementation Gaps

The following gaps should be closed before changing export behavior:

1. Add deck-level export orchestration that runs slide schema validation, narrative arc validation, numeric assertion validation, export gate evaluation, and renderer execution in a fixed order.
2. Make the export path distinguish "no financial claims present" from "financial validation not run".
3. Wire numeric claim validation into export gating or pre-export orchestration.
4. Verify `financial_refs` resolve to validated financial cells before export.
5. Produce a deterministic financial reference map for exported decks.
6. Verify `evidence_refs` are active source references, not only non-empty strings.
7. Verify `job.required_evidence` is satisfied by slide evidence refs.
8. Produce a deterministic source appendix and evidence map.
9. Make export integrity fail when the source appendix, evidence map, media references, slide count, or financial reference map is missing or incomplete.
10. Wire stale artifact blocking to the project-scoped stale artifact repository or hard gate bundle instead of relying only on caller-supplied deck dictionaries.
11. Map renderer fallback/degradation outcomes into slide/deck `visual_quality`.
12. Verify provenance for low-materiality degraded visuals when export is allowed with warning.
13. Implement `render_pptxgenjs.ts` or `render_python_pptx.py` with deterministic output and artifact hashing.
14. Add a real `tests/integration/test_end_to_end_brief_to_export.py` flow.

## Recommended Next Baby Step

The next implementation step should still avoid broad export behavior changes. A safe follow-up would define the export artifact contract and tests first:

- artifact manifest schema
- source appendix/evidence map schema
- financial reference map schema
- expected pre-export validation order

Only after that contract exists should PFOS implement renderer behavior changes.
