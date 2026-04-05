# Exec Plan 1: Core Variant B State & Graph Skeleton (P0)

- **Date**: 2026-04-05
- **Status**: Completed
- **Target**: Variant B (MVP) readiness scaffolding per RFC-001/RFC-002/RFC-004 (structure-only; mocked execution)

## Objective
Implement the Variant B state contracts and a runnable LangGraph topology skeleton with the 5 new nodes:

1. `node_gather_context`
2. `node_generate_scenarios` (exactly 3 outputs)
3. `node_judge_validation` (stubbed verdict + clarifying loop + circuit breaker)
4. `node_execute_sandbox` (stubbed execution)
5. `node_synthesize_report` (stubbed report synthesis)

Also add strict "no localhost" environment guards so non-dev runs cannot silently fall back to `http://localhost:*`.

## Scope

### In scope
- New Variant B Pydantic input: `IncidentTrigger`.
- New Variant B graph state contract including `run_id` and `retry_count`.
- New Variant B LangGraph skeleton with deterministic routing and the `FATAL_VALIDATION_ERROR` circuit breaker.
- "No localhost" guard for external services (sandbox, YAAM, Phoenix, Redis), with an explicit local-dev escape hatch.
- A runnable script that streams node execution so operators can visually verify routing.
- Unit tests for (a) routing/circuit breaker and (b) env guard behavior.

### Out of scope (explicitly deferred)
- OpenRouter LLM abstraction and real tool injection (Exec Plan 2).
- Real Judge hard-constraint logic and epistemic-ledger enforcement (Exec Plan 2).
- Real sandbox simulation calls (`POST /api/v1/simulation/execute`) and parsing results (Exec Plan 3).
- YAAM L3/L4 connectors and open-science artifact dumping (Exec Plan 3).

## Verifiable Deliverable
A runnable (mocked/stubbed) LangGraph pipeline where you can inject an `IncidentTrigger` and:

- observe node execution in order via `graph.stream(..., stream_mode="updates")`, and
- force REJECT loops until `retry_count >= 3` yields a terminal `FATAL_VALIDATION_ERROR`.

## Implementation Tasks (ordered)

### 1) Add Variant B state contracts
- Create `src/agents/variant_b/state.py`:
  - `IncidentTrigger` (Pydantic).
  - `VariantBState` (TypedDict) including:
    - control plane: `run_id: str`, `retry_count: int`
    - data plane placeholders: `incident_context`, `scenarios`, `judge_feedback`, `sandbox_results`, `final_report_md`, `fatal_status`
  - `VariantBStateUpdate` (TypedDict, `total=False`).
- Create `src/agents/variant_b/__init__.py` exposing the Variant B graph entrypoint(s).

### 2) Add strict "no localhost" environment guard
- Create `src/core/env_guard.py`:
  - `assert_no_localhost_services(...)` validates:
    - `SANDBOX_API_URL`
    - `PHOENIX_COLLECTOR_ENDPOINT`
    - `REDIS_URL`
    - `POSTGRES_HOST` (if set)
    - `QDRANT_URL` (if set)
    - `TYPESENSE_URL` (if set)
  - Reject hostnames/IPs in `{localhost, 127.0.0.1, ::1, 0.0.0.0}`.
  - Allow explicit bypass for local dev/test only via `ALLOW_LOCALHOST=true`.
  - Error messages must be actionable (print the offending env var and value).

### 3) Implement Variant B LangGraph skeleton
- Create `src/agents/variant_b/graph.py`:
  - Implement stubbed nodes:
    - `node_gather_context`: populate minimal `incident_context`.
    - `node_generate_scenarios`: always create exactly 3 scenario dicts (include stable scenario ids).
    - `node_judge_validation`: stub verdict logic with deterministic switch:
      - If env `VARIANT_B_FORCE_REJECT=true`, reject and append feedback.
      - Otherwise accept.
      - On REJECT: increment `retry_count` and route to `node_generate_scenarios`.
      - If `retry_count >= 3`: set `fatal_status="FATAL_VALIDATION_ERROR"` and terminate.
    - `node_execute_sandbox`: stub results for 3 scenarios.
    - `node_synthesize_report`: populate `final_report_md` (string only; no filesystem writes in this exec plan).
  - Wire graph edges:
    - `START → gather_context → generate_scenarios → judge_validation`
    - judge conditional:
      - ACCEPT → execute_sandbox → synthesize_report → `END`
      - REJECT (retry_count < 3) → generate_scenarios
      - FATAL (retry_count >= 3) → `END`
  - Provide a `compile_variant_b_graph(...)` function so scripts/tests can import without side effects.

### 4) Add runnable harness
- Create `scripts/run_variant_b.py`:
  - Loads `.env` early (match `scripts/run_baseline.py` pattern).
  - Calls `assert_no_localhost_services()` before executing any network-facing logic.
  - Calls `setup_observability()` before graph execution.
  - Accepts:
    - `--incident-json <path>` to load `IncidentTrigger`
    - `--thread-id <id>` for LangGraph `configurable.thread_id`
    - `--run-id <id>` override (default derived from incident_id + timestamp or just incident_id)
  - Streams node updates and prints:
    - `[NODE COMPLETED] <node_name>`
    - `retry_count`
    - final status: success vs `FATAL_VALIDATION_ERROR`

### 5) Add tests
- Add `tests/core/test_env_guard.py`:
  - localhost URLs rejected for each key.
  - remote IP URLs accepted (use `.env.example`-style values).
  - bypass works when `ALLOW_LOCALHOST=true`.
- Add `tests/agents/test_variant_b_graph.py`:
  - ACCEPT path hits all nodes and produces `final_report_md`.
  - forced REJECT loops and terminates at `retry_count == 3` with `fatal_status="FATAL_VALIDATION_ERROR"`.

## Test Plan (must-pass quality gates)
Run using the repo virtual environment (`.venv/`):

- `./.venv/bin/ruff check .`
- `./.venv/bin/python -m mypy src`
- `./.venv/bin/python -m pytest`

## Acceptance Criteria
- `python scripts/run_variant_b.py` runs end-to-end without contacting external services (stubbed execute) while still enforcing env guards.
- Forced reject path deterministically terminates with `FATAL_VALIDATION_ERROR` after 3 retries.
- All tests and quality gates pass.
- Baseline graph (`src/agents/graph.py`) remains intact and runnable.

## Maintenance Log
- 2026-04-05:
  - Green baseline gates: fixed `ruff` unused imports and `mypy` type errors in `src/tools/*`.
  - Implemented Variant B Exec Plan 1 skeleton: `IncidentTrigger` + `VariantBState`, `assert_no_localhost_services()` guard, stubbed 5-node LangGraph, CLI runner `scripts/run_variant_b.py`, and unit tests.
  - Validated: `ruff check .`, `python -m mypy src`, `python -m pytest`.
