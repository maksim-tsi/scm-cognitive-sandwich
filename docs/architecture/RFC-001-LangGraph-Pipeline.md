# RFC-001: LangGraph Pipeline Architecture (Variant B) & State Management

**Status**: Approved for WinterSim Phase
**Repository**: `scm-cognitive-sandwich`
**Context**: Transition from static validation to dynamic simulation using a neuro-symbolic "Cognitive Sandwich" approach.

## 1. Objective
Define the strictly controlled "Plan-and-Execute" graph topology to orchestrate LLM reasoning, solver validation, and simulation execution. Ensure Vendor-Agnostic design for LLM providers.

## 2. Model Agnosticism (OpenRouter)
To ensure flexibility during the research phase, the system MUST decouple the LLM logic from specific providers (like OpenAI or Anthropic). 
* All LLM calls within nodes must be routed through an abstraction layer (via OpenRouter).
* Model selection must be configurable via environment variables, allowing seamless swapping of models for different nodes (e.g., a fast model for `gather_context` and a high-reasoning model for `judge_validation`).

## 3. Proposed Graph Design
* **Initial Trigger**: The graph is instantiated via a Pydantic `IncidentTrigger` object (standardized JSON containing `incident_id`, `affected_nodes`, `cargo_demand`, `raw_alert_text`).
* **Graph Nodes & Flow**:
    1.  `node_gather_context`: Purely investigative. Uses MCP tools to fetch physical data from Digital Twin and logical data from ERP DB. Merges this with `IncidentTrigger` into `incident_context`.
    2.  `node_generate_scenarios`: Produces exactly 3 orthogonal candidate plans using available tools.
    3.  `node_judge_validation`: Acts as a gatekeeper using strict hard constraints (see RFC-002).
    4.  `node_execute_sandbox`: Transmits validated scenarios to the `maritime-port-sandbox` API.
    5.  `node_synthesize_report`: Aggregates simulation results and writes a final Markdown report.

## 4. Pareto Logic Constraints
Identification of the Pareto frontier (non-dominated scenarios) MUST be performed by a deterministic Python function within the `node_synthesize_report` node, based on the multi-criteria metrics from the Sandbox. The LLM is strictly relegated to textual interpretation of these mathematical trade-offs.