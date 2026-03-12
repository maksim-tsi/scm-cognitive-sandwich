# Execution Plan: Project Initiation (SCM Cognitive Sandwich)

## Objective
Establish the baseline directory structure, initial code skeletons, and testing strategy for the SCM Cognitive Sandwich project. This plan strictly follows the architecture and domain guidelines defined in `docs/architecture/index.md` and `docs/domain/sandwich-loop.md`.

## Phase 1: Skeleton & Environment Setup
1. **Initialize Directory Structure:**
   - Create the `src/` directory with subdirectories: `agents/`, `solver/`, `clients/`, `memory/`.
   - Create `tests/` directory with corresponding subdirectories matching `src/`.
2. **Setup Dependencies:**
   - Since we use `langgraph`, `langchain`, `pyomo`, `pydantic` (v2), `pytest`, `ruff`, and `mypy`, ensure `pyproject.toml` or `requirements.txt` is updated reflecting these dependencies.

## Phase 2: Domain Modeling & Memory Facade
1. **Pydantic Schemas:**
   - Create `src/agents/state.py` containing `PortAllocation`, `RoutingParameters`, `SolverResult`, and `GraphState`.
2. **YAAM Integration (`src/memory/yaam_facade.py`):**
   - Implement wrapper functions for `artifact_save_draft`, `artifact_attach_feedback`, `artifact_create_revision`, and `artifact_commit_final`.

## Phase 3: Client & Solver Implementation
1. **External API Client (`src/clients/port_sandbox.py`):**
   - Implement HTTP client to fetch ground truth from `maritime-port-sandbox`. Provides actual `availableCapacityTEU`.
2. **Operations Research Model (`src/solver/routing_model.py`):**
   - Implement Pyomo model utilizing SCIP.
   - Encode constraints: Demand Satisfaction & Capacity.
   - Implement logic to catch infeasibility and extract the Irreducible Infeasible Subsystem (IIS) log.

## Phase 4: LangGraph Agent Orchestration
1. **Prompts (`src/agents/prompts.py`):**
   - Define system prompts for Upstream LLM (translates text to JSON) and Downstream LLM (reads IIS log and repairs JSON).
2. **Graph Construction (`src/agents/graph.py`):**
   - Implement `node_ingest_alert`, `node_draft_artifact`, `node_run_solver`, `node_repair_artifact`, `node_commit_final`.
   - Wire conditional edges: `FEASIBLE` -> commit; `INFEASIBLE` -> repair -> run_solver.

## Phase 5: Testing & Validation
1. **Solver Tests (`tests/solver/test_routing_model.py`):**
   - Verify 100% test coverage for the deterministic Pyomo/SCIP solver.
   - Intentionally pass mathematically impossible JSON payloads and assert IIS log extraction.
2. **Integration Tests (`tests/agents/test_graph.py`):**
   - Mock LLM responses via `langchain_core.messages`.
   - Verify LangGraph routing terminates on `FEASIBLE` and loops on `INFEASIBLE`.
   - Run `pytest` and `ruff check .` to pass strict validation.

## Next Steps
- Request user approval.
- Proceed to implement Phase 1 & 2.

## Maintenance Log
- 2026-03-12: Added `recursion_limit` to `scripts/run_baseline.py`, retained cumulative `solver_error_logs` state history, strengthened downstream repair prompt, and improved baseline runner printing for routing JSON + IIS logs.
