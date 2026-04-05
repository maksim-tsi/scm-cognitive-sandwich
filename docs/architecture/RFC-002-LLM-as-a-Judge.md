# RFC-002: LLM-as-a-Judge Mechanism & Clarifying Loop

**Status**: Approved for WinterSim Phase
**Repository**: `scm-cognitive-sandwich`

## 1. Objective
Prevent "Cognitive Escape", enforce deterministic execution, and reduce computational waste in the DES environment by implementing a strict validation layer (Gatekeeper).

## 2. Hard Constraints (Reject Triggers)
The `node_judge_validation` MUST explicitly output `STATUS: REJECT` if a candidate scenario violates ANY of the following:
1.  **Mass Balance Violation**: The sum of redistributed cargo (TEU) does not exactly match the disrupted cargo.
2.  **SLA / Contract Breach**: The scenario utilizes ports or routes explicitly forbidden by the extracted context.
3.  **Physical Impossibility (Physics Violation)**: Targeting closed ports or proposing throughput that exceeds explicitly checked `terminal_throughput` limits.
4.  **Malformed Tool/Syntax**: Scenario lacks specific tool calls or valid JSON structure required by the DES engine.
5.  **Lack of Diversification**: The 3 candidates are conceptually identical, making Pareto multi-criteria analysis impossible.

## 3. The Clarifying Loop (Anti-Stubborn Agent Syndrome)
* The Graph State must track `retry_count` (int).
* Upon a `REJECT` verdict, the Judge's feedback is explicitly appended to the context, and execution routes back to `node_generate_scenarios`.
* **Circuit Breaker**: If `retry_count >= 3`, the session MUST immediately terminate with a `FATAL_VALIDATION_ERROR` status, bypassing simulation.