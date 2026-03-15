# Batch Run Analysis Report

## Report Metadata

- Report date: 2026-03-15
- Repository: scm-cognitive-sandwich
- Experiment type: IDWL batch run
- Scope: First 10 scenarios (`--limit 10`)
- Analyst: GitHub Copilot

## Run Identification

- Run date (UTC): 2026-03-15
- Start time (UTC): 2026-03-15T19:20:33Z
- End time (UTC): 2026-03-15T19:22:04Z
- Wall-clock duration: 91 seconds (window), 71.6791 seconds aggregate scenario execution time
- Batch command: `python scripts/batch_runner.py --limit 10`
- Batch log artifact: `/tmp/batch_run_limit10_20260315T192033Z.log`
- Results artifact: `data/results_idwl_v1.csv`
- Results rows before run: 34
- Results rows after run: 44
- New rows added: 10

## Objective of This Run

Evaluate whether the graceful unknown-port validation fix improves feedback quality in the repair loop and whether the 10-call trial converges to FEASIBLE outcomes under current prompts and control logic.

## Environment and Monitoring Setup

- Python runtime: 3.12.3
- Sandbox endpoint verified: `http://localhost:8001/api/v1/pcs/terminals/NLRTM/status` (HTTP 200)
- Phoenix OpenAPI verified: `http://192.168.107.172:6006/openapi.json` (HTTP 200)
- Phoenix project in use: `scm-cognitive-sandwich-idwl`
- Observability initialization in runner confirmed from startup logs:
  - `PHOENIX_COLLECTOR_ENDPOINT=http://192.168.107.172:6006/v1/traces`
  - `PHOENIX_PROJECT_NAME=scm-cognitive-sandwich-idwl`
  - `OTEL_RESOURCE_ATTRIBUTES=openinference.project.name=scm-cognitive-sandwich-idwl,service.name=scm-cognitive-sandwich-idwl`

## Executive Summary

- All 10 scenarios ended with `ERROR_RECURSION`.
- No run reached `node_commit_final`.
- Repair loops were uniform and non-convergent: each thread executed 4 `node_run_solver` passes and 4 `node_repair_artifact` passes.
- The new unknown-port validation message was observed and persisted (example: run `007`, bad port `DEWVN`), confirming the graceful guard is active.
- Dominant failure mode remains capacity infeasibility on effectively unavailable ports (9/10 latest error logs).

## Quantitative Outcomes

### Status and Loop Metrics

| Metric | Value |
| --- | --- |
| Scenarios executed | 10 |
| FEASIBLE | 0 |
| INFEASIBLE (terminal) | 0 |
| ERROR_RECURSION | 10 |
| Revision count (min / max / avg) | 4 / 4 / 4.0 |
| LLM token count total | 0 |
| LLM token count avg | 0.0 |
| Total execution time across scenarios | 71.6791 s |
| Average execution time per scenario | 7.1679 s |

### Error Pattern Breakdown (latest solver feedback in `final_json`)

| Pattern | Count |
| --- | --- |
| capacity_constraint | 9 |
| unknown_port | 1 |

## Per-Run Detail (10 New Rows)

| Run ID | Primary Event | Secondary Event | Final Status | Revisions | Time (s) | Pattern |
| --- | --- | --- | --- | ---: | ---: | --- |
| 001 | TOTAL_CLOSURE |  | ERROR_RECURSION | 4 | 9.0680 | capacity_constraint |
| 002 | OPERATIONAL_RESTRICTION |  | ERROR_RECURSION | 4 | 6.1140 | capacity_constraint |
| 003 | TOTAL_CLOSURE | TOTAL_CLOSURE | ERROR_RECURSION | 4 | 9.3897 | capacity_constraint |
| 004 | OPERATIONAL_RESTRICTION |  | ERROR_RECURSION | 4 | 7.3346 | capacity_constraint |
| 005 | OPERATIONAL_RESTRICTION | TOTAL_CLOSURE | ERROR_RECURSION | 4 | 6.3416 | capacity_constraint |
| 006 | TOTAL_CLOSURE | TOTAL_CLOSURE | ERROR_RECURSION | 4 | 6.1919 | capacity_constraint |
| 007 | SEVERE_CONGESTION |  | ERROR_RECURSION | 4 | 6.5754 | unknown_port |
| 008 | SEVERE_CONGESTION | OPERATIONAL_RESTRICTION | ERROR_RECURSION | 4 | 6.6288 | capacity_constraint |
| 009 | OPERATIONAL_RESTRICTION | TOTAL_CLOSURE | ERROR_RECURSION | 4 | 6.2555 | capacity_constraint |
| 010 | TOTAL_CLOSURE |  | ERROR_RECURSION | 4 | 7.7796 | capacity_constraint |

## Validation of Hallucinated-Port Handling

### Expected behavior

Unknown ports should not crash solver execution and should produce explicit feedback:

`SOLVER ERROR: Port {bad_port} is not recognized in the current network topology. Allowed ports are: NLRTM, BEANR, DEHAM, DEBRV.`

### Observed behavior in this run

- Unknown-port message appeared in stream logs and persisted into output payloads.
- Latest unknown-port final payload observed in run `007`:
  - `SOLVER ERROR: Port DEWVN is not recognized in the current network topology. Allowed ports are: NLRTM, BEANR, DEHAM, DEBRV.`
- Log sampling found repeated unknown-port events, indicating guard activation is reliable under recursion pressure.

Interpretation: the graceful validation fix is working as designed, but it is not sufficient by itself to guarantee convergence.

## Phoenix Trace Analysis

### Project attribution and span availability

| Metric | Value |
| --- | --- |
| Target project span count | 390 |
| Default project span count | 0 |
| Unique run thread IDs | 10 |
| Thread ID pattern | `idwl_exp_v1_run_001` ... `idwl_exp_v1_run_010` |

### Node-level counts (windowed query)

| Node | Span Count |
| --- | ---: |
| node_ingest_alert | 10 |
| node_draft_artifact | 10 |
| node_run_solver | 40 |
| node_repair_artifact | 40 |
| node_commit_final | 0 |

### Per-thread loop shape

Every thread from `idwl_exp_v1_run_001` to `idwl_exp_v1_run_010` had:

- `node_run_solver`: 4
- `node_repair_artifact`: 4
- `node_commit_final`: 0

Interpretation: consistent non-convergent repair cycle; no successful terminal commit transitions.

## Phoenix Feedback Loop Actions Performed

To preserve diagnostics directly in observability tooling:

- Posted 10 trace annotations to Phoenix endpoint `/v1/trace_annotations`.
- Annotation name: `solver_loop_quality`
- Annotator kind: `HUMAN`
- Label: `non_convergent`
- Score: `0.1`
- Metadata action: `refine_downstream_repair_prompt_and_loop_guard`

## Notable Operational Finding

A Phoenix query failed earlier with HTTP 422 because `limit=5000` exceeds API max `1000`. Subsequent queries succeeded with `limit=1000`.

## Root-Cause Assessment

1. Unknown-port hallucination is now detected and surfaced semantically, preventing generic exception behavior.
2. Primary non-convergence driver in this 10-run cohort is still repeated capacity-constraint infeasibility.
3. Current repair policy appears to repeatedly produce allocations that remain mathematically infeasible under scenario capacities.
4. No evidence of commit path success in this sample (0 `node_commit_final` spans).

## Recommendations for Next Iteration

1. Strengthen downstream repair prompt constraints to explicitly avoid zero-capacity and closed ports in each revision.
2. Add deterministic pre-solver guard for zero-capacity targeting with explicit solver feedback analogous to unknown-port feedback.
3. Add a repair-attempt heuristic: if infeasibility pattern repeats without improvement across attempts, force alternative allocation strategy or emit deterministic INFEASIBLE decision.
4. Re-run the same `--limit 10` slice after prompt/logic updates and compare:
   - `ERROR_RECURSION` count
   - `node_commit_final` span count
   - mean revisions
   - share of unknown-port and capacity-constraint terminal logs

## Evidence Artifacts

- Run window metadata: `/tmp/batch_limit10_window.env`
- Batch execution log: `/tmp/batch_run_limit10_20260315T192033Z.log`
- Parsed summary snapshot: `/tmp/batch_limit10_analysis_summary.json`
- Phoenix spans (target project): `/tmp/phoenix_spans_limit10_target.json`
- Phoenix spans (default project): `/tmp/phoenix_spans_limit10_default.json`
- Persisted run outputs: `data/results_idwl_v1.csv`

## Reproducibility Notes

To reproduce this exact report flow:

1. Run `python scripts/batch_runner.py --limit 10`
2. Capture UTC start/end timestamps around run.
3. Query Phoenix with `limit <= 1000` for the window.
4. Analyze the last 10 appended rows from `data/results_idwl_v1.csv`.
5. Correlate row-level outcomes with thread-level traces (`idwl_exp_v1_run_###`).
