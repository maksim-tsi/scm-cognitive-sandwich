# RFC-006: YAAM Data Contracts & Namespaces

**Status**: Approved for WinterSim Phase
**Repository**: `scm-cognitive-sandwich`
**Context**: Defining data structures, database isolation boundaries, and serialization contracts for direct memory management by the Orchestrator.

## 1. Objective
To prevent data contamination across different experiments on shared DBMS instances by strictly defining isolation namespaces. Additionally, to document the core Pydantic data contracts (schemas) used by the `YAAMFacade` for L1-L4 memory tiers.

## 2. Infrastructure Namespaces & Isolation
All memory interactions MUST be strictly scoped to the WinterSim experiment using explicit environment variables defined in `.env`.

* **L1 Working Memory (Redis)**
    * **Constraint**: Must use explicit key prefixes to avoid collision with other LangGraph agents or IDWL legacy runs.
    * **Config Key**: `REDIS_PREFIX` (e.g., `sandwich:winsim:`)
* **L2 Runtime Storage (PostgreSQL)**
    * **Constraint**: Data must be written to an isolated database schema.
    * **Config Key**: `POSTGRES_DB` (e.g., `yaam_winsim`).
    * *Known Limitation (Research Environment)*: Due to the constraints of the rapid prototyping environment, PostgreSQL access is currently managed via a global `pgadmin` superuser account rather than role-based access control (RBAC).
* **L3 Episodic Memory (Qdrant)**
    * **Constraint**: Vector embeddings for this experiment must be stored in a dedicated collection.
    * **Config Key**: `QDRANT_COLLECTION` (e.g., `winsim_episodes`)
* **L4 Semantic Artifacts (Typesense)**
    * **Constraint**: Final Markdown deliverables and SLA contracts must be indexed in a specific Typesense collection.
    * **Config Key**: `TYPESENSE_COLLECTION` (e.g., `winsim_artifacts`)

## 3. Core Data Contracts (Pydantic Models)
The `YAAMFacade` will enforce the following Pydantic schemas when serializing data to the target databases.

### 3.1. L1 & L2 (Runtime Context & Checkpoints)
* **Model**: `TurnData` / LangGraph Checkpoint State
* **Purpose**: Stores the ephemeral state of the LangGraph execution (current variables, `retry_count`, active scenarios).
* **Format**: JSON blobs indexed by `run_id` and `thread_id`.

### 3.2. L3 (Episodic Memory)
* **Model**: `Episode`
* **Purpose**: Stores a historical "snapshot" of a successful reasoning path and its context for future Retrieval-Augmented Generation (RAG).
* **Fields**:
    * `episode_id` (UUID)
    * `incident_context` (JSON metadata about the disruption)
    * `applied_tools` (List of tools utilized)
    * `embedding` (Dense vector array representing the semantic meaning of the incident)

### 3.3. L4 (Semantic Memory / Artifacts)
* **Model**: `KnowledgeDocument`
* **Purpose**: Stores the human-readable outputs and strict business rules.
* **Fields**:
    * `document_id` (String ID)
    * `content` (The raw Markdown text of the final report or SLA constraints)
    * `document_type` (e.g., `FINAL_REPORT`, `SLA_CONSTRAINT`, `FAILED_RUN_LOG`)
    * `run_id` (Reference back to the specific execution thread)

## 4. Data Flow (Variant B)
1.  **Ingestion**: `IncidentTrigger` begins the graph execution. State is continuously saved to **L1 (Redis)**.
2.  **Execution**: The Orchestrator interacts with the `maritime-port-sandbox` and receives a `SandboxExecutionOutput`.
3.  **Synthesis**: The `node_synthesize_report` calculates the Pareto frontier.
4.  **Consolidation**: 
    * The node formats the textual analysis into a Markdown document and calls `YAAMFacade.l4_upsert_document()`.
    * The node formats the successful tool sequence and incident semantics into an `Episode` and calls `YAAMFacade.l3_upsert_episode()`.