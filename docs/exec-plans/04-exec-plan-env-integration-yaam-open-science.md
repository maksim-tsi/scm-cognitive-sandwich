# Exec Plan 3: Environment Integration & YAAM Open Science (P1/P2)

- **Date**: 2026-04-05
- **Status**: Draft (depends on Exec Plan 1 + Exec Plan 2)

## Objective
Wire Variant B into the real WinterSim environment:

- `node_execute_sandbox` calls the remote Sandbox API (`POST /api/v1/simulation/execute`) and parses results.
- Implement YAAM L3/L4 connectors (Qdrant + Typesense surfaces) through `src/memory/yaam_facade.py` boundary.
- Implement RFC-004 open-science artifact dumping:
  - per-node JSON state dumps (`run_id_step_N.json`)
  - final Markdown reports (`report_run_id.md`)
  - negative-result Markdown reports for `FATAL_VALIDATION_ERROR`
  - artifacts stored under `data/runs/<run_id>/`

## Verifiable Deliverable
A full end-to-end run that:

- hits the remote sandbox service,
- parses simulation results into the graph state,
- generates a final report Markdown file,
- and leaves a complete trail of JSON artifacts under `data/runs/`.

## Implementation Tasks (high-level, ordered)
- Implement sandbox simulation client and strict response schema validation.
- Extend state/result schemas to match sandbox multi-criteria metrics.
- Implement YAAM facade calls for artifact lineage + final commit, backed by real YAAM APIs.
- Implement Typesense indexing for final + negative-result reports (L4).
- Implement per-node artifact dump hook in the Variant B graph (post-node state snapshot).
- Add integration tests that can be skipped without env access; add a local "mock sandbox" mode for CI if needed.
- Confirm observability spans include run_id/thread_id/scenario_id and route to the configured Phoenix project.

## Test Plan
- Unit tests for artifact dumper output naming and schema stability.
- Integration tests gated by env flags and remote endpoint reachability.
- Quality gates: `ruff check .`, `python -m mypy src`, `python -m pytest`.

## Maintenance Log
- (fill in as changes land)

