# Architecture & System Design 🏗️

This document defines the architectural boundaries for the **SCM Cognitive Sandwich**. As an autonomous agent, you must strictly adhere to these patterns. Do not blur the lines between semantic reasoning (LLM) and mathematical optimization (OR Solver).

## 1. The "Sandwich" Paradigm
The core philosophy of this repository is explicit separation of concerns:
* **LLMs are bad at math but good at semantic context.**
* **Solvers are perfect at math but cannot read news or understand context.**

Therefore, the workflow is a "Sandwich":
1. **Upstream (LLM):** Translates an unstructured text alert into a structured JSON payload (Routing Parameters).
2. **Meat (OR Solver):** A deterministic Python function (Pyomo + SCIP) attempts to solve the routing problem using the JSON payload.
3. **Downstream (LLM):** If the solver fails, it returns an IIS (Irreducible Infeasible Subsystem) log. The LLM reads this log, adjusts the JSON, and sends it back to the solver.

## 2. Directory Structure & Layered Design
You must maintain strict separation between the graph logic, the math model, and the external API clients.

```text
src/
├── agents/               # LangGraph definitions and LangChain wrappers
│   ├── graph.py          # The main state machine (nodes and edges)
│   ├── state.py          # TypedDict defining the GraphState
│   └── prompts.py        # System prompts for the Upstream and Downstream LLMs
├── solver/               # Operations Research core (Deterministic Math)
│   └── routing_model.py  # Pyomo model formulation and SCIP IIS extraction
├── clients/              # External integrations
│   └── port_sandbox.py   # HTTP client to fetch ground truth from maritime-port-sandbox
└── memory/               # YAAM integration wrappers
    └── yaam_facade.py    # Helper functions invoking YAAM's artifact_tools

```

## 3. The LangGraph State Machine

The orchestration is driven by **LangGraph**. You must implement the following nodes and conditional edges:

### Nodes:

* `node_ingest_alert`: Receives the initial text alert, calls the `maritime-port-sandbox` client to get current port capacities, and stores them in the `GraphState`.
* `node_draft_artifact`: The Upstream LLM generates `Artifact v1` (JSON routing plan). Calls YAAM's `artifact_save_draft`.
* `node_run_solver`: Passes the JSON artifact to the Pyomo solver. Does NOT invoke the LLM. Returns either `FEASIBLE` or `INFEASIBLE` (with IIS log).
* `node_repair_artifact`: The Downstream LLM analyzes the IIS log and generates `Artifact v(N+1)`. Calls YAAM's `artifact_attach_feedback` and `artifact_create_revision`.
* `node_commit_final`: Calls YAAM's `artifact_commit_final` to save the successful decision to L4 memory.

### Conditional Edges:

* After `node_run_solver`, the graph must route to `node_commit_final` if the status is `FEASIBLE`.
* If the status is `INFEASIBLE`, it must route to `node_repair_artifact`, and then loop back to `node_run_solver`.

## 4. The Pyomo / SCIP Boundary

The solver in `src/solver/routing_model.py` must be strictly deterministic.

* **Rule 1:** The LLM does NOT write or execute Python code at runtime. The Pyomo model is pre-written by you (the AI coder) during development.
* **Rule 2:** The solver accepts a strict Pydantic model (`RoutingParameters`) and returns a strict Pydantic model (`SolverResult`).
* **Rule 3:** If the Pyomo model is mathematically infeasible, you must extract the IIS (Irreducible Infeasible Subsystem) using SCIP's built-in conflict analysis and return it as a string for the Downstream LLM to read.

## 5. YAAM Integration (Memory Subsystem)

We use YAAM (`Yet Another Agents Memory`) as an external library to maintain the cognitive audit trail.

* Do not create SQL tables or local JSON files for state persistence.
* Import the artifact tools directly from the YAAM package.
* **Lineage Requirement:** Every time `node_repair_artifact` creates a new revision, it MUST link it to the previous revision and attach the IIS log using `artifact_attach_feedback`.

## 6. Testing Requirements

* **Solver Tests:** `src/solver/routing_model.py` must have 100% test coverage using `pytest`. You must write tests that intentionally pass mathematically impossible JSON payloads to verify that the IIS extraction works correctly.
* **Graph Tests:** Use `langchain_core.messages` to mock LLM responses and test the LangGraph routing logic (ensuring the loop terminates on `FEASIBLE`).