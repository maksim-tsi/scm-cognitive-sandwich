# Architecture & System Design

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
    ├── checkpointer.py   # Adaptive L1 checkpointer factory (Redis or in-memory)
    ├── yaam_client.py    # Async HTTP client for episode consolidation to YAAM
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
* **Rule 3:** If the Pyomo model is mathematically infeasible, return a deterministic, human-readable IIS-style conflict payload for the Downstream LLM.

### Current solver backend behavior

* The implementation attempts `appsi_highs` first (pip-installable via `highspy`) and falls back to `scip` when available.
* The conflict payload is generated deterministically from violated demand/capacity constraints.
* This keeps the repair loop stable even when native SCIP conflict extraction is unavailable in the runtime.

## 5. YAAM Integration (Memory Subsystem)

We use YAAM (`Yet Another Agents Memory`) as an external library to maintain the cognitive audit trail.

* Do not create SQL tables or local JSON files for state persistence.
* Import the artifact tools directly from the YAAM package.
* **Lineage Requirement:** Every time `node_repair_artifact` creates a new revision, it MUST link it to the previous revision and attach the IIS log using `artifact_attach_feedback`.

### L1/LTM Separation

* The graph owns short-lived Working Memory (L1) via a LangGraph checkpointer factory in `src/memory/checkpointer.py`.
* If `REDIS_URL` is set (for example `redis://host:6379/0`), the graph uses a Redis-backed saver with prefix `sandwich:checkpoint:` to avoid key collisions on shared Redis infrastructure.
* Redis can be shared with YAAM on the same DB when namespaces are kept distinct (for example via key prefixes and non-overlapping RediSearch index names).
* If `REDIS_URL` is absent or Redis initialization fails, the graph falls back to LangGraph `MemorySaver` for local development.
* Long-term consolidation is decoupled and performed by `src/memory/yaam_client.py`, which posts the final episode state to `YAAM_API_URL`.
* `consolidate_episode` propagates tracing context through the W3C `traceparent` header so local and remote traces can be stitched in Phoenix.

## 6. Testing Requirements

* **Solver Tests:** `src/solver/routing_model.py` must have 100% test coverage using `pytest`. You must write tests that intentionally pass mathematically impossible JSON payloads to verify that the IIS extraction works correctly.
* **Graph Tests:** Use `langchain_core.messages` to mock LLM responses and test the LangGraph routing logic (ensuring the loop terminates on `FEASIBLE`).

## 7. Observability Architecture (OpenTelemetry + Phoenix)

Tracing initialization is centralized in `src/core/observability.py` and executed by `scripts/run_baseline.py` before graph execution.

### Startup and resource attribution contract

* `.env` is loaded before tracing setup.
* Project routing is resolved in this order:
1. `OTEL_RESOURCE_ATTRIBUTES` `openinference.project.name`
2. `OTEL_RESOURCE_ATTRIBUTES` legacy `project.name` (normalized)
3. `PHOENIX_PROJECT_NAME`
* `TracerProvider` is created with an explicit `Resource`.
* `OTEL_RESOURCE_ATTRIBUTES` is rewritten in-process to include normalized attributes for downstream instrumentors.

### Required attributes for stable Phoenix routing

Preferred environment value:

`OTEL_RESOURCE_ATTRIBUTES=openinference.project.name=<project>,service.name=<service>`

Notes:
* Defining `OTEL_RESOURCE_ATTRIBUTES` multiple times in `.env` is discouraged.
* If duplicates exist, the last declaration wins.
* The code keeps backward compatibility for `project.name` by mapping it to `openinference.project.name`.

### Environment variables quick reference

| Variable | Required | Example / Notes |
| --- | --- | --- |
| `PHOENIX_COLLECTOR_ENDPOINT` | Yes (for tracing) | `http://192.168.107.172:6006/v1/traces` |
| `PHOENIX_PROJECT_NAME` | Yes (for tracing) | `scm-cognitive-sandwich-idwl` |
| `OTEL_RESOURCE_ATTRIBUTES` | Yes (for stable Phoenix routing) | `openinference.project.name=scm-cognitive-sandwich-idwl,service.name=scm-cognitive-sandwich-idwl` |
| `OTEL_SERVICE_NAME` | Optional | If unset, defaults to project name in startup code |
| `SANDBOX_API_URL` | Optional | Defaults to local sandbox URL when unset |
| `YAAM_API_URL` | Optional | Defaults to local YAAM URL when unset |
| `REDIS_URL` | Optional | Enables Redis-backed LangGraph checkpointer |
| `GOOGLE_API_KEY` | One LLM key required | Use local secret value; do not commit |
| `MISTRAL_API_KEY` | One LLM key required | Use local secret value; do not commit |
| `GROQ_API_KEY` | One LLM key required | Use local secret value; do not commit |

Safe copy/paste starter block (placeholder-only for secrets):

```bash
PHOENIX_COLLECTOR_ENDPOINT=http://192.168.107.172:6006/v1/traces
PHOENIX_PROJECT_NAME=scm-cognitive-sandwich-idwl
OTEL_RESOURCE_ATTRIBUTES=openinference.project.name=scm-cognitive-sandwich-idwl,service.name=scm-cognitive-sandwich-idwl

# Optional integration endpoints
# SANDBOX_API_URL=http://localhost:8001
# YAAM_API_URL=http://localhost:8002
# REDIS_URL=redis://localhost:6379/0

# LLM credentials (set locally; never commit real values)
# GOOGLE_API_KEY=<set-locally>
# MISTRAL_API_KEY=<set-locally>
# GROQ_API_KEY=<set-locally>
```

### Instrumentation scope

* `openinference.instrumentation.langchain` is always instrumented.
* `opentelemetry-instrumentation-httpx` is optional and enabled when installed.
* HTTP spans can appear as separate root traces depending on library/runtime context boundaries; project attribution still remains correct.