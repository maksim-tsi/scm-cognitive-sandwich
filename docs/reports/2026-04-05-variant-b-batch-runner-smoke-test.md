# Variant B Batch Runner Smoke Test Report

## Report Metadata

- Report date: 2026-04-05
- Repository: scm-cognitive-sandwich
- Experiment type: Variant B batch incident execution
- Scope: Smoke test on 3 dummy incidents (`data/batch_incidents_dummy`)
- Analyst: GitHub Copilot

## Objective

Validate the new unattended batch runner (`scripts/run_batch.py`) for:

1. Directory-based incident ingestion for `.json` IncidentTrigger files.
2. End-to-end Variant B graph execution per incident.
3. Fault tolerance (single incident failure does not stop batch).
4. Observability enforcement (Phoenix tracing enabled).
5. Summary reporting with required buckets.

## Command Executed

```bash
source .venv/bin/activate && python scripts/run_batch.py --incidents-dir data/batch_incidents_dummy --sleep-between-sec 0
```

## Test Inputs

- `data/batch_incidents_dummy/incident_nominal_001.json` (valid)
- `data/batch_incidents_dummy/incident_stress_002.json` (valid)
- `data/batch_incidents_dummy/incident_invalid_003.json` (invalid schema: missing `cargo_demand`)

## Observed Terminal Output (Summary Section)

```text
Batch Summary
Total Run: 3, Success: 2, Fatal Validation: 1, Infeasible: 0
Error: 0
Results CSV: data/results_variant_b_batch.csv
```

## Full Relevant Runtime Excerpt

```text
Observability configured. Exporting to http://192.168.107.172:6006/v1/traces for project scm-cognitive-sandwich-winsim (openinference.project.name=scm-cognitive-sandwich-winsim).
[RUN 001/003] incident_file=incident_invalid_003.json
  ERROR: ValidationError: 1 validation error for IncidentTrigger
cargo_demand
  Field required [type=missing, input_value={'incident_id': 'batch-de...lidation failure path.'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
  STATUS=FATAL_VALIDATION fatal_status=- retry_count=0 elapsed_sec=0.00
[RUN 002/003] incident_file=incident_nominal_001.json
  STATUS=SUCCESS fatal_status=- retry_count=0 elapsed_sec=28.65
[RUN 003/003] incident_file=incident_stress_002.json
  STATUS=SUCCESS fatal_status=- retry_count=0 elapsed_sec=28.59

Batch Summary
Total Run: 3, Success: 2, Fatal Validation: 1, Infeasible: 0
Error: 0
Results CSV: data/results_variant_b_batch.csv
```

## Outcome Assessment

- Batch continued after a schema validation failure on incident 1.
- Valid incidents 2 and 3 completed successfully.
- Summary buckets are present and correctly populated.
- Observability remained enabled and exported to Phoenix endpoint.

## Artifacts Produced

- Script: `scripts/run_batch.py`
- Dummy incidents: `data/batch_incidents_dummy/*.json`
- Batch results CSV: `data/results_variant_b_batch.csv`

## Validation Gate Results

- `ruff check .`: passed
- `python -m mypy src`: passed
- `python -m pytest`: passed (`65 passed, 1 skipped`)
