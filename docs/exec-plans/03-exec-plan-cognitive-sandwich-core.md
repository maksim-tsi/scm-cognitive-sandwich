# Exec Plan 2: The Cognitive Sandwich Core (P0/P1)

- **Date**: 2026-04-05
- **Status**: Draft (depends on Exec Plan 1)

## Objective
Implement the Variant B cognitive core:

- OpenRouter-backed LLM abstraction with per-node model selection (fast vs reasoning).
- Deterministic tool injection from `src/tools/__init__.py:ACTIVE_TOOLS` into `node_generate_scenarios` (no RAG for tools).
- A strict `node_judge_validation` implementation (RFC-002 hard constraints + clarifying loop semantics).
- A pure-Python deterministic Pareto frontier evaluator (multi-objective non-dominance) for Variant B reporting.

## Verifiable Deliverable
With mocked sandbox execution data:

- the LLM can generate 3 scenarios using injected tools,
- the Judge rejects malformed/unsupported plans and appends actionable feedback (triggering retries),
- and the Pareto evaluator correctly identifies the frontier from a deterministic test fixture.

## Implementation Tasks (high-level, ordered)
- Implement OpenRouter LLM adapter and env-driven model selection per node.
- Implement tool binding/injection into scenario generation (manifest-driven; `ACTIVE_TOOLS` only).
- Add a tool-execution ledger to state so the Judge can detect epistemic trespassing (quoted facts without tool traces).
- Implement RFC-002 Judge hard-constraint checks (mass balance, SLA/forbidden routes, physics/capacity, malformed tool syntax, diversification).
- Add deterministic Pareto frontier Python function + unit tests.
- Extend Variant B synth step to call Pareto evaluator (LLM narrates only; Python decides dominance set).

## Test Plan
- Unit tests for: tool ledger enforcement, judge accept/reject rules, Pareto frontier determinism.
- Quality gates: `ruff check .`, `python -m mypy src`, `python -m pytest`.

## Maintenance Log
- (fill in as changes land)

