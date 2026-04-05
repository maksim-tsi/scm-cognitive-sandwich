# RFC-004: YAAM Memory Integration & Open Science Artifacts

**Status**: Approved for WinterSim Phase
**Repository**: `scm-cognitive-sandwich`

## 1. Objective
Implement the 4-tier Yet Another Agents Memory (YAAM) system and automated artifact logging to guarantee auditability, traceability, and reproducibility for the Winter Simulation Conference publication.

## 2. Memory Tiers (YAAM) Architecture
* **L1/L2 (Redis/PostgreSQL)**: Manages ephemeral runtime state, `retry_count`, active hypotheses, and LangGraph checkpoints.
* **L3 (Qdrant)**: Vector database for semantic search of historical atomic experiences (to be utilized in future RAG flows, explicitly excluding tool discovery).
* **L4 (Typesense)**: Fast, typo-tolerant Full-Text Search. Stores Final Deliverables, SLA contracts, and baseline port characteristics.

## 3. Open Science Artifact Logging
To support our WinterSim dataset:
1.  **Intermediate States**: After every LangGraph node execution, the entire `Graph State` must be dumped to a structured `.json` file (`run_id_step_N.json`).
2.  **Final Deliverables**: The terminal output of the pipeline MUST be saved as a human-readable `.md` (Markdown) file (`report_run_id.md`).
3.  **Negative Results**: Sessions that terminate in `FATAL_VALIDATION_ERROR` (see RFC-002) must also be documented in `.md` format and saved to Typesense (L4) to build a dataset of "Failure Distributions".
4.  **Observability**: All execution traces, prompt inputs, and LLM outputs must be streamed to Arize Phoenix using OpenTelemetry.