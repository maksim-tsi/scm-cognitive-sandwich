# Final Empirical Evidence & Data Audit: Cognitive Sandwich Architecture

This report aggregates historical run data, payload logs, and solver metrics across `data/results_idwl_v1.csv`, `data/results_variant_b_batch.csv`, and specific deep-dive execution traces (`winsim-demo-001`). The objective is to provide comprehensive, quantitative evidence of system behaviors, architectural pathologies, and efficiency constraints for academic peer review.

---

## 1. Executive Summary

Our empirical audit of the recent batch runs reveals a stark contrast between initial drafting capabilities and self-correction efficiency. While the Variant B orchestrated runs achieved a high success rate (83.3%), the pure IDWL V1 baseline runs highlighted severe limitations in LLM reasoning when confronted with strict mathematical Operations Research (OR) constraints. Most notably, **the system exhibited a 0% success rate in its repair loop**—if the LLM failed the initial zero-shot allocation, it inevitably descended into recursion or terminal infeasibility.

---

## 2. Experimental Data Aggregation

We evaluated the overarching status distributions across two distinct operational batches.

### Baseline IDWL V1 Run Metrics (78 Total Scenarios)
| Metric | Count | Percentage | Description |
| :--- | :--- | :--- | :--- |
| **Total Scenarios** | 78 | 100% | Procedurally generated routing events. |
| **FEASIBLE (0-shot)** | 16 | 20.5% | Scenarios correctly routed on the first attempt without repair. |
| **INFEASIBLE** | 28 | 35.9% | Failed to generate a mathematically sound allocation. |
| **ERROR_RECURSION** | 34 | 43.6% | Exceeded the LangGraph recursion limit without finding a solution. |

### Variant B Orchestrated Batch (66 Total Scenarios)
*Variant B introduces the LLM-as-a-Judge and Pareto Frontier topology.*

| Metric | Count | Percentage | Description |
| :--- | :--- | :--- | :--- |
| **SUCCESS** | 55 | 83.3% | Successfully navigated, validated, and optimized. |
| **FATAL_VALIDATION** | 11 | 16.7% | Fatal schema/logic errors preventing execution. |
| **ERROR/INFEASIBLE** | 0 | 0.0% | Zero infinite looping or unhandled infeasibilities. |

*(Note: The `winsim-demo-001` run demonstrated the ideal Variant B execution, achieving identical time/cost/risk metrics (120h / $50k / 0.2) across its Pareto frontier with exactly 1 retry step).*

---

## 3. Pathology Statistics

Analysis of the IDWL V1 payloads and `latest_solver_error_log` exposed two critical LLM behavioral pathologies under constraints.

### 3.1 Cognitive Escape (Hallucinations)
When the LLM cannot fit the cargo volume into the available capacities of the `ALLOWED_PORTS` (`NLRTM`, `BEANR`, `DEHAM`, `DEBRV`), it attempts a "Cognitive Escape" by hallucinating invalid ports to dump the excess volume.
- **Occurrences**: **7 instances** (e.g., hallucinating nodes `FRLEH`, `GBSOU`, and `DEWVN`).
- **Mechanism**: The solver rejects these immediately as "unrecognized in the current network topology" or assigns them a 0 TEU maximum capacity constraint.

### 3.2 Stubborn Agent Syndrome
Instead of correctly interpreting the Irreducible Infeasible Subsystem (IIS) logs provided by the OR-solver, the LLM frequently repeats its previous failed drafts or cycles between two invalid states.
- **Occurrences**: **34 instances** (43.6% of the V1 dataset).
- **Mechanism**: The LangGraph state machine violently halts the execution with `ERROR_RECURSION` after hitting the hard limit of 10 consecutive failures. 

---

## 4. Guardrails & Repair Efficiency

### The "Terminal Infeasibility Check" Guardrail
The O(1) mathematical pre-flight guardrail is designed to cleanly intercept scenarios where the `total_required_teu` strictly exceeds the `total_available_capacity` across all allowed ports combined.
- **Intercept Count**: **0 scenarios**.
- **Insight**: This indicates that the simulated events in `scenarios_idwl_v1.csv` never actually presented a mathematically impossible volume constraint. There was always enough aggregate theoretical capacity; the LLM simply failed to solve the distribution puzzle.

### The IIS-Driven Repair Loop
The core hypothesis of the "Cognitive Sandwich" is that deterministic solver feedback (IIS conflict logs) enables LLMs to repair their own artifacts.
- **One-Step Repair Success**: **0%**.
- **Multi-Step Repair Success**: **0%**.
- **Insight**: Every single one of the 16 `FEASIBLE` runs in the V1 batch had a `revisions_count` of exactly **0**. The LLM either successfully solved the routing parameters on the initial state-aware zero-shot prompt, or it failed entirely. **The LLM never successfully repaired an infeasible draft into a feasible one.** 

---

## 5. Conclusions for Academic Reviewers

The empirical data strongly suggests that while LLMs can act as effective translators of unstructured context into structured initial drafts (20.5% zero-shot success), they are **highly ineffective at iterative mathematical constraint satisfaction**. 

The inclusion of the deterministic OR-solver layer is thus absolutely vital, not as a feedback mechanism for the LLM to learn from during runtime, but as a hard, impenetrable wall to reject non-deterministic hallucinations and prevent physically impossible operations from executing downstream. The evolution to the Variant B architecture (83.3% success) demonstrates that routing via Sandbox simulations and LLM-as-a-Judge evaluations is vastly superior to expecting an LLM to self-correct based on pure mathematical constraint feedback.
