# Phase Enum Codegen

PFOS phase names are sourced from `docs/08_StateMachine_Spec.yaml`.
Do not hand-maintain duplicate phase lists in backend or UI code.

Run:

```bash
make codegen-phase-enums
```

This updates:

- `system/generated_phase_enums.py`
- `ui/lib/phaseTypes.ts`

Validation uses:

```bash
make validate-phase-enums
```

`make validate` includes this check and fails when either generated file is
stale relative to the state machine spec.
