# 2026-04-05 — RFC-001–RFC-004 Orchestrator Readiness (Variant B / MVP) — Gap Analysis

**Repository**: `scm-cognitive-sandwich` (Orchestrator)  
**Date**: 2026-04-05  
**Scope reviewed (read-only)**: `src/` (agents, memory, clients, solver, core/observability), `src/tools/`, and runtime harness in `scripts/` + observability docs/ADRs.  
**Infrastructure constraint noted**: Production runs must not rely on `localhost`; remote services are on `192.168.107.172` / `192.168.107.187` per `.env.example`.

---

## Executive Readiness Scorecard (RAG)

| RFC | Status | Snapshot |
|---|---|---|
| **RFC-001 (LangGraph topology + deterministic Pareto)** | 🔴 **RED** | Current LangGraph is the baseline “draft/solve/repair/commit” sandwich loop, not the Variant B plan-and-execute topology; no scenario set (exactly 3), no sandbox execution node, no synth-report node, no deterministic Pareto frontier evaluator. Evidence: `src/agents/graph.py`, `docs/architecture/RFC-001-LangGraph-Pipeline.md`. |
| **RFC-002 (LLM-as-a-Judge + clarifying loop)** | 🔴 **RED** | No Judge node, no `retry_count` circuit breaker semantics, no hard-constraint REJECT gating; current loop is solver-driven repair with `revisions_count` and `recursion_limit`. Evidence: `src/agents/graph.py`, `src/agents/state.py`, `docs/architecture/RFC-002-LLM-as-a-Judge.md`. |
| **RFC-003 (Deterministic tool integration governance; no RAG for tools)** | 🟢 **GREEN** | Deterministic tool registry is already present: explicit manifest (`src/tools/active_tools_manifest.json`) → generated curated exports (`src/tools/__init__.py`) with stable callable names; no semantic search/RAG-based tool discovery in repo. Evidence: `src/tools/active_tools_manifest.json`, `src/tools/__init__.py`, `src/tools/README.md`. |
| **RFC-004 (YAAM 4-tier memory + open science artifact logging)** | 🔴 **RED** | Only partial scaffolding exists (Redis checkpointer factory + YAAM consolidation HTTP client). No L3/L4 connectors, YAAM artifact facade is placeholder, and required JSON/MD artifact dumping is not implemented. Evidence: `src/memory/checkpointer.py`, `src/memory/yaam_client.py`, `src/memory/yaam_facade.py`, `docs/architecture/RFC-004-YAAM-Artifact-Logging.md`. |

---

## As-Is State (Current Repository Reality)

> Infra note (2026-04-05): YAAM frontgate (`YAAM_API_URL`, port 8002) is deprecated per infrastructure audit. Variant B memory will target PostgreSQL/Qdrant/Typesense directly.

### A) LangGraph implementation (vs RFC-001)
**What exists now**
- A baseline LangGraph “sandwich loop” with nodes:
  - `node_ingest_alert` → `node_draft_artifact` → `node_run_solver` → (conditional) `node_repair_artifact` loop → `node_commit_final`.  
  Evidence: `src/agents/graph.py` (graph build at module bottom).
- Current state model is routing-only:
  - `GraphState` includes `alert_text`, `port_capacities`, `routing_parameters`, `solver_result`, `solver_error_logs`, `revisions_count`.  
  Evidence: `src/agents/state.py`.
- External ground-truth port capacity fetch is implemented:
  - `clients.port_sandbox.get_port_capacities()` calls `SANDBOX_API_URL` `/api/v1/pcs/terminals/{port}/status`.  
  Evidence: `src/clients/port_sandbox.py`.

**What this means for readiness**
- Current graph is **not** the RFC-001 Variant B topology:
  - No `IncidentTrigger` (Pydantic) entry contract.
  - No `node_gather_context`, `node_generate_scenarios` (exactly 3), `node_judge_validation`, `node_execute_sandbox`, `node_synthesize_report`.
  - No deterministic Pareto frontier computation from sandbox multi-criteria metrics.

### B) Memory handling & YAAM (vs RFC-004)
**What exists now**
- **L1 checkpointing**:
  - Adaptive checkpointer uses `REDIS_URL` when set; otherwise in-memory `MemorySaver`.  
  Evidence: `src/memory/checkpointer.py`, `.env.example` (Redis remote host + `REDIS_URL`).
- **Episode consolidation**:
  - Legacy: `YAAMClient.consolidate_episode()` posts final state via an HTTP endpoint and propagates `traceparent` (frontgate now deprecated).  
  Evidence: `src/memory/yaam_client.py`, `src/agents/graph.py` (`_consolidate_episode` call in `node_commit_final`).
- **Artifact tool facade exists but is non-functional**:
  - `artifact_save_draft()` returns `"draft_id_mock"`, and other functions are no-ops/mocks.  
  Evidence: `src/memory/yaam_facade.py`.
- The graph calls the facade, but uses hardcoded mock IDs:
  - `artifact_attach_feedback(artifact_id="draft_id_mock", ...)`, `artifact_commit_final(artifact_id="revision_id_mock")`.  
  Evidence: `src/agents/graph.py`.

**What this means for readiness**
- The repo has **scaffolding** for L1 and consolidation, but not the RFC-004 4-tier system:
  - No L3 (Qdrant) connector surfaces.
  - No L4 (Typesense) connector surfaces or indexing of final/negative results.
  - No open-science artifact dumping to `.json` per node or `.md` per run.

### C) Tool integrations (vs RFC-003)
**What exists now**
- Deterministic, explicitly curated tool registry:
  - `src/tools/active_tools_manifest.json` lists module/function pairs.
  - `src/tools/__init__.py` exports alias-named callables and `ACTIVE_TOOLS`.
  - No code path attempts semantic search to “find tools”; the surface is explicit.  
  Evidence: `src/tools/active_tools_manifest.json`, `src/tools/__init__.py`, `src/tools/README.md`.

**What this means for readiness**
- Tool governance is already in the right shape for RFC-003: deterministic, non-RAG, manifest-driven.
- Note: current baseline LangGraph does not yet use these tools inside an LLM scenario-generation node (because RFC-001 nodes are not implemented yet).

### D) Observability + Phoenix attribution (design verification)
**What exists now**
- Centralized tracing bootstrap:
  - `setup_observability()` loads `.env`, normalizes project attribution into `openinference.project.name`, and configures OTLP HTTP exporter to `PHOENIX_COLLECTOR_ENDPOINT`.  
  Evidence: `src/core/observability.py`.
- ADR confirms design intent:
  - Explicit precedence & legacy mapping (`project.name` → `openinference.project.name`).  
  Evidence: `docs/decisions/002-otel-phoenix-project-attribution.md`.
- Runners call tracing setup before graph execution:
  - `scripts/run_baseline.py`, `scripts/batch_runner.py`.  
- Operational verification guide exists:
  - Phoenix OpenAPI feedback loop + span queries.  
  Evidence: `docs/architecture/phoenix-openapi-feedback-loop.md`.

**What this means for readiness**
- Static review indicates Phoenix routing is implemented consistent with ADR 002 (project attribution normalization + explicit Resource).
- True end-to-end verification still requires a runtime run + Phoenix API query (the repo already includes the playbook).

---

## To-Be State (Gaps to reach Variant B / MVP)

### RFC-001 gaps: required nodes + deterministic Pareto
Missing / not yet implemented:
- **Graph entry contract**: `IncidentTrigger` Pydantic object with standardized incident fields (RFC-001).
- **Node set & flow** (Variant B):
  - `node_gather_context` (MCP/data gathering, merges into `incident_context`)
  - `node_generate_scenarios` (exactly **3** orthogonal candidate plans)
  - `node_judge_validation` (gatekeeper per RFC-002)
  - `node_execute_sandbox` (send validated scenarios to `maritime-port-sandbox` simulation endpoints; collect multi-metric results)
  - `node_synthesize_report` (final Markdown report)
- **Deterministic Pareto frontier evaluator**:
  - Must be pure Python and run inside the synth/report path (LLM only narrates trade-offs).  
  Current codebase has `src/tools/pareto_analysis.py`, but it implements 80/20 Pareto principle, **not** multi-objective non-dominance frontier.

### RFC-002 gaps: Judge hard constraints + clarifying loop
Missing / not yet implemented:
- A **dedicated Judge node** that emits explicit `STATUS: REJECT` on hard constraint violations (mass balance, SLA/contract, physics/terminal throughput/closed ports, malformed tool/syntax, lack of diversification).
- **Clarifying loop state**:
  - `retry_count` tracked in state (separate from solver revision count unless intentionally unified).
  - Route back to scenario generation on REJECT with appended judge feedback.
  - Circuit breaker: `retry_count >= 3` → terminate with `FATAL_VALIDATION_ERROR` (no simulation).

### RFC-004 gaps: YAAM L3/L4 + artifact dumping (Open Science)
Missing / not yet implemented:
- **YAAM artifact tools real integration**:
  - `src/memory/yaam_facade.py` must bind to real YAAM artifact APIs (no mock IDs).
  - Artifact lineage: revisions must link correctly; solver/Judge feedback must attach to the correct revision IDs.
- **YAAM tiers beyond L1**:
  - L3 (Qdrant) connector for semantic retrieval (explicitly *not* for tool discovery).
  - L4 (Typesense) connector for final deliverables + negative results.
- **Artifact dumping mechanisms** (required by RFC-004):
  - After every node: dump entire Graph State to `run_id_step_N.json`.
  - Final report: write `report_run_id.md`.
  - Negative results: persist `FATAL_VALIDATION_ERROR` runs as Markdown and store/index in L4.

### Cross-cutting operational gap (infra constraint: “no localhost”)
- Several codepaths default to `http://localhost:*` when env vars are missing:
  - `src/clients/port_sandbox.py` defaults `SANDBOX_API_URL` to `http://localhost:8001`.
  - `scripts/batch_runner.py` defaults `SANDBOX_API_URL` to `http://localhost:8001`.  
- `.env.example` is correctly configured for remote nodes, but the runtime should fail fast (or at least warn loudly) if a non-local environment is expected.

---

## Observability Check (Phoenix attribution)

### Static compliance with prior design decisions (ADR 002)
- **Project attribution normalization** appears correct:
  - Resolves project name from `OTEL_RESOURCE_ATTRIBUTES` (`openinference.project.name` first, then legacy `project.name`, then `PHOENIX_PROJECT_NAME`).
  - Ensures `openinference.project.name` is present in the effective Resource and synchronizes `OTEL_RESOURCE_ATTRIBUTES` in-process.  
  Evidence: `src/core/observability.py`, `docs/decisions/002-otel-phoenix-project-attribution.md`, `tests/core/test_observability.py`.

### What cannot be fully verified by static inspection
- Whether Phoenix at `http://192.168.107.172:6006` is currently ingesting and routing spans for fresh runs into the intended project (this requires a run + API query).
- The repo already documents an API-first verification method.  
  Evidence: `docs/architecture/phoenix-openapi-feedback-loop.md`.

---

## Implementation Plan (Variant B / MVP) — Prioritized Checklist

### P0 — Variant B graph topology + state contracts (RFC-001 foundation)
- [ ] Define `IncidentTrigger` (Pydantic) and new Variant B `GraphState` fields (`incident_context`, `scenarios[3]`, `judge_feedback`, `retry_count`, `run_id`, `results`, `fatal_status`).
- [ ] Implement LangGraph Variant B node skeletons and edges exactly as RFC-001 specifies (gather → generate(3) → judge → execute → synthesize).
- [ ] Ensure the baseline graph remains runnable for regression (either behind a switch or as a separate entrypoint).

### P0 — Judge gatekeeper + clarifying loop (RFC-002)
- [ ] Implement `node_judge_validation` with explicit ACCEPT/REJECT schema and hard constraints.
- [ ] Implement clarifying loop routing:
  - REJECT → append judge feedback → increment `retry_count` → back to `node_generate_scenarios`.
  - `retry_count >= 3` → terminate with `FATAL_VALIDATION_ERROR` and produce negative-result artifact (RFC-004).
- [ ] Add deterministic checks where possible (mass balance, malformed JSON, diversification heuristics) so the Judge is not purely “LLM opinion”.

### P0 — Deterministic Pareto frontier evaluator (RFC-001)
- [ ] Add a pure-Python Pareto frontier function over sandbox-returned metrics (non-dominance).
- [ ] Call it inside `node_synthesize_report` (LLM narrates only; Python determines the frontier set).
- [ ] Add tests asserting determinism and correctness on known metric tuples.

### P1 — Sandbox execution node + result schema (RFC-001)
- [ ] Implement `node_execute_sandbox` to send scenarios to `maritime-port-sandbox` simulation endpoints (not just terminal status/capacity).
- [ ] Define strict result schema capturing multi-criteria metrics required for Pareto.

### P1 — Tools binding and execution trace enforcement (RFC-003 in Variant B)
- [ ] In `node_generate_scenarios`, deterministically bind tools from `src/tools/__init__.py` (`ACTIVE_TOOLS`) to the LLM/tool-calling interface (no tool RAG).
- [ ] Add a state-level “tool execution ledger” (tool name, args, outputs, timestamp) so the Judge can reject epistemic trespassing (“quoted value without prior tool execution”).

### P1 — YAAM L3/L4 + artifact tools (RFC-004)
- [ ] Replace `src/memory/yaam_facade.py` mock behavior with real YAAM artifact tool calls via the facade boundary.
- [ ] Add YAAM connectors/config for L3 (Qdrant) and L4 (Typesense) per RFC-004, keeping tool-discovery explicitly excluded from L3 usage.
- [ ] Ensure negative results are stored/indexed in L4.

### P1 — Open science artifact dumping (RFC-004)
- [ ] Implement per-node Graph State dumps: `run_id_step_N.json`.
- [ ] Implement final report output: `report_run_id.md`.
- [ ] Implement negative-result report output for fatal sessions.

### P2 — Observability hardening for Variant B
- [ ] Ensure each node emits spans with stable names/attributes (node name, `run_id`, `thread_id`, scenario id).
- [ ] Keep Phoenix project attribution rules unchanged (ADR 002); add regression tests if new attributes are introduced.

### P2 — Operational guardrails (“no localhost”)
- [ ] Add startup validation that rejects or loudly warns when `SANDBOX_API_URL` / `PHOENIX_COLLECTOR_ENDPOINT` resolve to `localhost` in non-dev runs.
- [ ] Document the required `.env` settings for remote nodes (keep `.env.example` as the source of truth).

---

## Appendix: Primary Evidence Pointers (files)
- Variant B RFCs: `docs/architecture/RFC-001-LangGraph-Pipeline.md`, `docs/architecture/RFC-002-LLM-as-a-Judge.md`, `docs/architecture/RFC-003-Tool-Integration-MCP.md`, `docs/architecture/RFC-004-YAAM-Artifact-Logging.md`
- Current LangGraph baseline: `src/agents/graph.py`, `src/agents/state.py`, `src/agents/prompts.py`
- Tool registry: `src/tools/active_tools_manifest.json`, `src/tools/__init__.py`, `src/tools/README.md`
- Memory scaffolding: `src/memory/checkpointer.py`, `src/memory/yaam_client.py`, `src/memory/yaam_facade.py`
- Sandbox client: `src/clients/port_sandbox.py`
- Observability: `src/core/observability.py`, `docs/decisions/002-otel-phoenix-project-attribution.md`, `docs/architecture/phoenix-openapi-feedback-loop.md`
- Remote infra baseline: `.env.example`
