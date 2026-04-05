# Refined Batch Run Analysis Report

## Report Metadata

- Report date: 2026-03-15
- Repository: scm-cognitive-sandwich
- Experiment: IDWL batch rerun after repair-loop refinement
- Scope: 10 scenarios (`--limit 10`)
- Analyst: GitHub Copilot

## Run Identification

- Start time (UTC): 2026-03-15T19:45:13Z
- End time (UTC): 2026-03-15T19:45:47Z
- Batch command: `python scripts/batch_runner.py --limit 10`
- Batch log: `/tmp/batch_run_limit10_refined_20260315T194513Z.log`
- Results file: `data/results_idwl_v1.csv`
- Rows before run: 44
- Rows after run: 54
- New rows added: 10

## LLM Used in Calls

### Runtime selection

The run used:

- Provider: `google`
- Model: `gemini-3.1-flash-lite-preview`

### Why this model was selected

Selection follows `_get_llm()` precedence in [src/agents/graph.py](src/agents/graph.py#L127):

1. `GOOGLE_API_KEY` -> `ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview")`
2. else `MISTRAL_API_KEY`
3. else `GROQ_API_KEY`

During this run, Google key path was active, so data calls used `gemini-3.1-flash-lite-preview`.

## Executive Summary

- The recursion failure mode was eliminated for this 10-call slice.
- All 10 runs terminated cleanly as `INFEASIBLE` (no `ERROR_RECURSION`).
- All 10 solver outcomes were terminal mathematical infeasibility at solver boundary, so no repair loop was entered.
- Graph behavior matched design intent for terminal infeasible states:
  - `node_repair_artifact` count = 0
  - `node_commit_final` count = 10

## Quantitative Outcomes

### Batch result metrics (from CSV append segment)

| Metric | Value |
| --- | --- |
| Scenarios executed | 10 |
| FEASIBLE | 0 |
| INFEASIBLE | 10 |
| ERROR_RECURSION | 0 |
| Revisions min / max / avg | 0 / 0 / 0.0 |
| Total execution time | 14.9659 s |
| Average time per scenario | 1.4966 s |
| LLM token count total | 0 |

### Run-level statuses

| Run ID | Final Status | Revisions |
| --- | --- | ---: |
| 001 | INFEASIBLE | 0 |
| 002 | INFEASIBLE | 0 |
| 003 | INFEASIBLE | 0 |
| 004 | INFEASIBLE | 0 |
| 005 | INFEASIBLE | 0 |
| 006 | INFEASIBLE | 0 |
| 007 | INFEASIBLE | 0 |
| 008 | INFEASIBLE | 0 |
| 009 | INFEASIBLE | 0 |
| 010 | INFEASIBLE | 0 |

## Solver Feedback Pattern

From stream log diagnostics:

- `SOLVER TERMINAL: MATHEMATICALLY INFEASIBLE.` occurrences: 10
- Unknown-port errors: 0
- Capacity-conflict IIS lines: 0
- Demand-conflict IIS lines: 0

Interpretation: terminal infeasibility pre-check is now the dominant path for this scenario slice, and it prevents blind iterative repair attempts.

## Phoenix Trace Analysis

### Attribution and coverage

Window queried with a +2 minute buffer to absorb exporter delay:

- Start: 2026-03-15T19:45:13Z
- End: 2026-03-15T19:47:47Z

| Metric | Value |
| --- | --- |
| Target project spans | 150 |
| Default project spans | 0 |
| Unique thread IDs | 10 |

### Node counts

| Node | Count |
| --- | ---: |
| node_ingest_alert | 10 |
| node_draft_artifact | 10 |
| node_run_solver | 10 |
| node_repair_artifact | 0 |
| node_commit_final | 10 |

Interpretation: traces confirm expected deterministic path `ingest -> draft -> run_solver -> commit_final` for all 10 runs, with no repair loop invocation.

## YAAM Observability Notes

- Earlier in the session, transient YAAM connectivity warnings were observed.
- During this refined run:
  - `YAAM consolidate call failed` lines in log: 0
  - YAAM health endpoint was reachable (`/health` returned 200).
- Conclusion: no YAAM connectivity impact on this specific rerun outcome.

## Before vs After (Previous 10-call run vs Refined 10-call run)

| Metric | Previous run | Refined run |
| --- | ---: | ---: |
| ERROR_RECURSION | 10 | 0 |
| INFEASIBLE | 0 | 10 |
| node_repair_artifact spans | 40 | 0 |
| node_commit_final spans | 0 | 10 |
| Avg revisions | 4.0 | 0.0 |

Net effect: the blind repair loop was removed for this cohort, and outcomes are now legitimate terminal statuses instead of recursion errors.

## Key Conclusion

The requested refinement objective was achieved for this batch slice:

- graceful unknown-port handling remains intact,
- blind repair recursion is prevented,
- runs terminate in deterministic `INFEASIBLE` when mathematically impossible.

## Recommended Next Step

To increase FEASIBLE outcomes (not only avoid recursion), run a complementary 10-scenario subset where combined available capacity is expected to exceed demand, so the improved repair prompt and guardrail can be evaluated on genuinely repairable cases.

## Evidence Artifacts

- Window metadata: `/tmp/batch_limit10_refined_window.env`
- Structured summary: `/tmp/batch_limit10_refined_analysis_summary.json`
- Batch log: `/tmp/batch_run_limit10_refined_20260315T194513Z.log`
- Phoenix target spans (+2m): `/tmp/phoenix_spans_limit10_refined_target_plus2m.json`
- Results CSV: `data/results_idwl_v1.csv`
