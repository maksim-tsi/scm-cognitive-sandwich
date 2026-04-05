# RFC-003: Tool Integration (MCP) & Deterministic Execution

**Status**: Approved for WinterSim Phase
**Repository**: `scm-cognitive-sandwich`

## 1. Objective
Ensure all mathematical, physical, and logistical claims made by the LLM agent are grounded in verified, deterministic Python code execution, aligning with the neuro-symbolic methodology.

## 2. Tool Governance
* **Strictly No RAG for Tools**: The agent must not use semantic search (vector DB) to "guess" or find tools. 
* **Model Context Protocol (MCP)**: Tool availability is strictly dictated by the `active_tools_manifest.json` and the corresponding exports in `tools/__init__.py`. 
* **Deterministic Injection**: Tools are dynamically bound to the OpenRouter LLM interface at the start of the `node_generate_scenarios` step.

## 3. Epistemic Trespassing Prevention
The system must reject any scenario where the agent "hallucinates" a calculation. For example, if a scenario quotes a freight cost, the Graph State logs MUST show a prior, successful execution of `ocean_freight_costing__calculate_total_freight_cost`. If the execution trace is missing, the Judge (RFC-002) must reject the plan.