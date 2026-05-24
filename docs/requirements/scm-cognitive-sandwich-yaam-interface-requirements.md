# SCM Cognitive Sandwich YAAM Interface Requirements

**System:** SCM Cognitive Sandwich<br>
**Owner:** SCM Cognitive Sandwich project team<br>
**Date:** 2026-05-24<br>
**Status:** Draft<br>
**Primary contact:** TBD

## 1. System Overview

SCM Cognitive Sandwich is a LangGraph-based maritime disruption orchestration
system. It implements a "sandwich" control loop: an upstream LLM translates
unstructured disruption alerts into strict routing JSON artifacts, deterministic
solver and sandbox checks validate physical feasibility, and a downstream LLM
repairs the JSON only from explicit validation feedback.

YAAM is used as the audit memory layer for this workflow. Current integration is
through `src/memory/yaam_facade.py` and direct backing adapters for Qdrant and
Typesense. The target interface is MCP-first so agent hosts can discover safe
memory tools/resources while the project preserves the existing rule that local
YAAM access goes through the facade boundary and does not modify YAAM internals.

Main runtime components:

- Baseline graph: `node_draft_artifact`, `node_run_solver`,
  `node_repair_artifact`, and `node_commit_final`.
- Variant B graph: scenario generation, deterministic judge validation,
  maritime-port-sandbox execution, Pareto synthesis, L3 episode upsert, and L4
  report indexing.
- Deployment environment: Python 3.13 repository virtualenv, LangGraph,
  Phoenix/OpenTelemetry tracing, Redis checkpointer when configured, and remote
  Qdrant/Typesense collections for YAAM L3/L4.

## 2. Integration Goals

SCM Cognitive Sandwich needs YAAM for concrete audit and memory workflows:

- preserve every routing artifact revision and every solver feedback edge;
- retrieve compact lineage/context for active runs and completed artifacts;
- write successful Variant B episodes to L3 episodic memory;
- index final reports, SLA constraints, and negative/fatal validation outcomes
  in L4 semantic memory;
- return evidence and provenance metadata suitable for Phoenix-based debugging;
- enforce run/session/project isolation across shared memory infrastructure.

## 3. Expected Interface

| Interface | Required? | Purpose | Notes |
|---|---:|---|---|
| API Wall `/v1/chat/completions` | No | Not used for YAAM memory operations. | LLM calls are owned by the orchestrator; YAAM must not become the chat runtime for this system. |
| REST v2 `/v2/memory/...` | No for MVP | Optional batch/admin integration if YAAM requires a non-agent interface. | Useful for health checks, export jobs, or CI probes, but not the target customer interface. |
| MCP tools/resources/prompts | Yes | Target interface for artifact lifecycle, read-only context/evidence retrieval, L3/L4 writes, audit inspection, and health. | Must expose controlled mutating tools and read-only resources with explicit scope fields. |
| LangChain tools | No | Not required as a YAAM interface. | Runtime deterministic tools are governed by `src/tools/active_tools_manifest.json`; memory operations should not be mixed into that surface. |
| Direct library calls | Temporary | Transitional implementation through `src/memory/yaam_facade.py`. | Required until MCP reaches parity; all current local integration must continue through the facade boundary. |

## 4. Required Capabilities

| Capability | Tier | Read/Write/Lifecycle | Required for MVP? | Example input | Expected output |
|---|---|---|---:|---|---|
| Create artifact draft | Raw | Write | Yes | `artifact_kind="routing_parameters"`, `session_id`, `run_id`, JSON payload, `agent_id` | `artifact_id`, `revision_id`, `revision_number=1`, payload hash, status `draft` |
| Attach deterministic feedback | Raw | Write | Yes | `artifact_id`, `revision_id`, `feedback_type="solver_iis"`, IIS log, solver metadata | `feedback_id`, linked revision, verification state `infeasible` |
| Create repaired artifact revision | Raw | Write | Yes | `artifact_id`, `parent_revision_id`, repaired JSON payload, `trigger_feedback_id` | New `revision_id`, parent/feedback linkage, verification state `unverified` |
| Commit feasible final artifact | Raw | Lifecycle | Yes | `artifact_id`, feasible `revision_id`, commit reason, run metadata | `commit_id`, artifact status `committed`, committed revision linkage, optional L4 knowledge id |
| Retrieve artifact lineage/context | Unified | Read | Yes | `artifact_id` or `session_id` | Ordered draft/revision/feedback/commit nodes with payload hashes and provenance |
| Query or assemble scoped memory context | Unified | Read | Yes | `session_id`, `run_id`, topic/filter fields, max result count | Compact context block with source ids, tiers, scores, and trace metadata |
| Upsert successful episode | Raw | Write | Yes | `Episode`, 4096-d embedding, `QDRANT_COLLECTION`, run metadata | `episode_id`/vector id persisted in L3 with collection and status |
| Search episodic memory | Unified | Read | Yes | Query vector or incident topics, collection, limit, scope filters | Similar episodes with ids, summaries, scores, topics, and provenance |
| Upsert knowledge/report document | Raw | Write | Yes | `KnowledgeDocument`, `TYPESENSE_COLLECTION`, final Markdown or fatal report | `knowledge_id`, collection status, searchable L4 document |
| Retrieve evidence table | Unified | Read | Yes | `run_id`, `artifact_id`, scenario ids, include suppressed flag | Evidence rows for solver logs, sandbox results, tool ledger entries, Phoenix trace ids, and YAAM ids |
| Explain CIAR/retrieval metadata | Agentic | Read | No | `fact_id` or retrieval result ids | CIAR components if available; no autonomous promotion or consolidation |
| Trigger autonomous promotion/consolidation | Agentic | Lifecycle | No | N/A | Not exposed to SCM Cognitive Sandwich without explicit future approval |

### Requirement Justifications

- Versioned artifact lineage is required because the repair loop depends on
  preserving every JSON routing payload and every IIS-style feedback edge.
- Read-only context retrieval is required because operators and future agents
  need compact run context without querying Qdrant, Typesense, Redis, or graph
  storage internals.
- L3 episodic upsert/retrieval is required because Variant B already creates
  successful `Episode` records with 4096-dimensional embeddings and run
  metadata for later analysis.
- L4 indexing is required because WinterSim/open-science workflows need
  searchable final reports, SLA constraints, baseline port characteristics, and
  negative-result distributions.
- Evidence/provenance metadata is required because deterministic tool ledger
  entries, sandbox results, Phoenix trace ids, solver logs, and YAAM ids must
  remain inspectable.
- Strict scope identifiers are required because shared Redis, Qdrant, Typesense,
  and future YAAM services must not mix experiments, runs, tenants, or agents.
- Controlled mutations are required because the orchestrator, not YAAM, owns
  when memory is written; no background promotion/consolidation should run unless
  the graph explicitly requests it.

## 5. Use Case Scenarios

### Scenario 1: Artifact Repair Lineage

**Trigger:**
`node_draft_artifact` produces initial routing JSON and `node_run_solver`
returns an infeasible IIS-style conflict log.

**Caller:**
SCM Cognitive Sandwich baseline LangGraph.

**YAAM interface:**
MCP tools: `yaam.artifact.create_draft`,
`yaam.artifact.attach_feedback`, `yaam.artifact.create_revision`, and
`yaam.artifact.commit_final`.

**Input example:**

```json
{
  "session_id": "baseline-session-42",
  "run_id": "idwl-042",
  "agent_id": "scm-sandwich-experiment-v1",
  "artifact_kind": "routing_parameters",
  "payload": {
    "original_destination": "DEHAM",
    "total_teu_to_reroute": 10000,
    "allocations": [{"port_code": "NLRTM", "teu_amount": 10000}]
  }
}
```

**Expected YAAM behavior:**
Create draft revision 1. When solver feedback is attached, mark revision 1
infeasible and link the feedback to that revision. When the repaired JSON is
submitted, create revision 2 with `parent_revision_id` and
`trigger_feedback_id`. Commit only a revision that has deterministic feasible
feedback.

**Expected response shape:**
IDs for artifact, revision, feedback, commit, payload hash, revision number,
verification state, tier state, timestamps, and scope metadata.

**Failure handling:**
If YAAM cannot create lineage, return a typed error and do not silently claim the
artifact was persisted. If commit is requested for a non-feasible revision,
return a non-retryable validation error.

**Trace/audit expectations:**
Every tool response includes `trace_id` or accepts propagated `traceparent`,
plus `session_id`, `run_id`, `agent_id`, `artifact_id`, and `revision_id`.

### Scenario 2: Read-Only Artifact Audit Context

**Trigger:**
An operator or agent needs to inspect why a run converged, failed, or exhausted
repair attempts.

**Caller:**
SCM operator UI, debugging script, or future MCP-capable agent host.

**YAAM interface:**
MCP resource `yaam://artifacts/{artifact_id}/lineage` and tool
`yaam.artifact.get_lineage`.

**Input example:**

```json
{
  "artifact_id": "artifact-idwl-042",
  "include_payloads": true,
  "include_feedback": true
}
```

**Expected YAAM behavior:**
Return ordered lineage without mutating memory. Include draft/revision payload
hashes, solver feedback content, feasible/infeasible verification states, final
commit metadata, and knowledge projection ids when present.

**Expected response shape:**
`artifact`, `current_revision`, and ordered `nodes` with `node_type`, `node_id`,
`relation`, `revision_id`, `parent_id`, `timestamp`, `content`, and metadata.

**Failure handling:**
Unknown artifact ids return a typed not-found error. Authorization/scope
mismatches return a typed permission error without leaking artifact content.

**Trace/audit expectations:**
Read access is audited with caller id, resource URI, scope filters, and response
node count.

### Scenario 3: Variant B Successful Episode And Report Persistence

**Trigger:**
Variant B accepts generated scenarios, maritime-port-sandbox execution succeeds,
the Pareto frontier is computed, and `node_synthesize_report` builds a final
Markdown report.

**Caller:**
SCM Cognitive Sandwich Variant B graph.

**YAAM interface:**
MCP tools `yaam.l3.upsert_episode`, `yaam.l4.upsert_document`, and
`yaam.memory.query`.

**Input example:**

```json
{
  "session_id": "variant-b-thread-1",
  "run_id": "incident-2026-05-24-001",
  "incident_id": "incident-2026-05-24-001",
  "episode": {
    "summary": "Variant B successful run incident-2026-05-24-001",
    "topics": ["winsim", "variant_b"],
    "metadata": {
      "pareto_frontier_ids": ["incident-2026-05-24-001-S2"],
      "embedding_model": "qwen/qwen3-embedding-8b"
    }
  },
  "embedding_dimension": 4096,
  "knowledge_document": {
    "knowledge_id": "report-incident-2026-05-24-001",
    "knowledge_type": "final_report",
    "domain": "scm"
  }
}
```

**Expected YAAM behavior:**
Validate embedding dimension and scope fields, upsert the episode to the
configured Qdrant collection, upsert the final report to the configured
Typesense collection, and return storage status for both writes.

**Expected response shape:**
`episode_id`, vector id or point id, `knowledge_id`, collection names, write
status, timestamps, and trace metadata.

**Failure handling:**
Missing collection names, embedding failures, or storage write failures return
typed errors. The graph may mark `FATAL_YAAM_ERROR`; YAAM should not hide partial
write failures.

**Trace/audit expectations:**
Spans/events must expose `yaam.l3_upsert_episode`,
`yaam.l4_upsert_document`, `run_id`, `thread_id`, collection names, and latency.

### Scenario 4: Negative Result Knowledge Capture

**Trigger:**
Variant B reaches `FATAL_VALIDATION_ERROR` after deterministic or semantic judge
rejections.

**Caller:**
SCM Cognitive Sandwich Variant B graph or batch runner.

**YAAM interface:**
MCP tool `yaam.l4.upsert_document`.

**Input example:**

```json
{
  "session_id": "variant-b-thread-2",
  "run_id": "incident-2026-05-24-002",
  "knowledge_type": "failed_run_log",
  "content": "# Variant B Negative Result\n\nValidation failed after 3 retries.",
  "metadata": {
    "fatal_status": "FATAL_VALIDATION_ERROR",
    "retry_count": 3,
    "judge_findings": ["MASS_BALANCE(...): allocations sum 3 != cargo_demand 10000."]
  }
}
```

**Expected YAAM behavior:**
Index the fatal validation report in L4 as negative evidence, not as a successful
episode. Preserve judge feedback/findings and run identifiers for later failure
distribution analysis.

**Expected response shape:**
`knowledge_id`, collection name, `knowledge_type="failed_run_log"`, write
status, timestamps, and provenance metadata.

**Failure handling:**
If the L4 write fails, return a typed write error and include enough detail for
the orchestrator to surface the failure in run output.

**Trace/audit expectations:**
Audit records distinguish successful reports from negative results and include
fatal status plus retry count.

### Scenario 5: Scoped Evidence Table Retrieval

**Trigger:**
A reviewer needs to prove why a scenario recommendation was accepted and which
deterministic evidence supported it.

**Caller:**
SCM operator, paper artifact generator, or future MCP-capable agent.

**YAAM interface:**
MCP tool `yaam.evidence.table` or `yaam.memory.get_context`.

**Input example:**

```json
{
  "run_id": "incident-2026-05-24-001",
  "session_id": "variant-b-thread-1",
  "include_sandbox_results": true,
  "include_tool_ledger": true,
  "include_solver_feedback": true
}
```

**Expected YAAM behavior:**
Assemble a read-only evidence table from YAAM records and customer-provided
metadata. Return deterministic tool entries, sandbox execution results, solver
feedback, artifact ids, episode ids, knowledge ids, and Phoenix trace links when
available.

**Expected response shape:**
Rows with `evidence_id`, `source_tier`, `source_id`, `source_system`,
`timestamp`, `claim`, `evidence_payload`, `trace_id`, and `scope`.

**Failure handling:**
Partial evidence retrieval may return partial rows with warnings. Scope mismatch
or missing permission must fail closed.

**Trace/audit expectations:**
Returned evidence includes source ids and timestamps; the read call is logged
with requested scopes and partial-result warnings.

## 6. MCP Expectations

### 6.1 Tool Requirements

| Proposed tool | Required? | Read/Write/Lifecycle | Required input fields | Required output fields |
|---|---:|---|---|---|
| `yaam.artifact.create_draft` | Yes | Write | `session_id`, `artifact_kind`, `payload`, `run_id`, `agent_id` | `artifact_id`, `revision_id`, `revision_number`, `payload_hash`, `status` |
| `yaam.artifact.attach_feedback` | Yes | Write | `artifact_id`, `revision_id`, `feedback_type`, `source_system`, `content`, `run_id` | `feedback_id`, `verification_state`, `artifact_status`, `timestamp` |
| `yaam.artifact.create_revision` | Yes | Write | `artifact_id`, `parent_revision_id`, `payload`, `trigger_feedback_id`, `agent_id` | `revision_id`, `revision_number`, `payload_hash`, `parent_revision_id` |
| `yaam.artifact.commit_final` | Yes | Lifecycle | `artifact_id`, `revision_id`, `commit_reason`, `run_id` | `commit_id`, `artifact_status`, `revision_id`, optional `knowledge_id` |
| `yaam.artifact.get_lineage` | Yes | Read | `artifact_id` or `session_id`, include flags | `artifact`, `current_revision`, ordered `nodes`, metadata |
| `yaam.memory.query` | Yes | Read | `session_id`/scope, query text/vector, tiers, limit | Results with tier, id, score, content snippet, provenance |
| `yaam.memory.get_context` | Yes | Read | `session_id`, `run_id`, tiers, token/row limit | Context block, sources, estimated tokens, warnings |
| `yaam.l3.upsert_episode` | Yes | Write | `session_id`, `episode`, `embedding`, `collection`, `run_id` | `episode_id`, vector id/point id, collection, status |
| `yaam.l4.upsert_document` | Yes | Write | `knowledge_document`, `collection`, `run_id`, `session_id` | `knowledge_id`, collection, status |
| `yaam.evidence.table` | Yes | Read | `run_id` or `artifact_id`, include flags, scope | Evidence rows, source ids, trace ids, warnings |
| `yaam.health` | Yes | Read | Optional backend checks | Service/backend health and version metadata |

### 6.2 Resource Requirements

| Proposed resource | Required? | Access scope | Notes |
|---|---:|---|---|
| `yaam://sessions/{session_id}/context` | Yes | Session | Read-only assembled context for an active or completed run. |
| `yaam://sessions/{session_id}/artifacts` | Yes | Session | Lists artifacts and current status within one LangGraph thread/session. |
| `yaam://artifacts/{artifact_id}/lineage` | Yes | Artifact | Ordered artifact/revision/feedback/commit lineage. |
| `yaam://episodes/{episode_id}` | Yes | Episode | L3 episode payload and provenance. |
| `yaam://knowledge/{knowledge_id}` | Yes | Knowledge document | L4 report, SLA rule, or negative-result document. |
| `yaam://health` | Yes | Service | YAAM service and backend readiness. |
| `yaam://config/scopes` | Yes | Service | Read-only visible namespace/collection policy for debugging. |

### 6.3 Prompt Requirements

| Proposed prompt | Required? | Purpose | Expected variables |
|---|---:|---|---|
| `yaam.prompt.artifact_repair_context` | Yes | Format artifact lineage and solver feedback for downstream repair LLMs. | `artifact_id`, `current_revision_id`, `solver_feedback`, `capacity_context` |
| `yaam.prompt.evidence_table` | Yes | Present deterministic evidence for reports or reviews. | `run_id`, `artifact_id`, `include_tool_ledger`, `include_sandbox_results` |
| `yaam.prompt.memory_inspection` | Yes | Summarize scoped YAAM context for operators/agents. | `session_id`, `run_id`, `tiers`, `max_items` |
| `yaam.prompt.ciar_explanation` | No for MVP | Explain CIAR components when facts are later used. | `fact_id`, `include_components` |
| `yaam.prompt.contradiction_review` | No for MVP | Future review workflow for conflicting memories. | `session_id`, `candidate_facts` |

## 7. Data And Scope Requirements

- Required identifiers for mutating calls: `session_id` or `thread_id`,
  `run_id`, `agent_id`, and project/tenant namespace.
- Required domain identifiers when available: `incident_id`, `scenario_id`,
  `artifact_id`, `revision_id`, `feedback_id`, `episode_id`, and `knowledge_id`.
- Required backend scope metadata: Redis prefix, PostgreSQL database/schema,
  Qdrant collection, Typesense collection, and Phoenix project name when known.
- Baseline graph artifacts are scoped to the LangGraph thread/session plus
  `agent_id`.
- Variant B episodes and reports are scoped by `run_id`, `thread_id`,
  `incident_id`, and collection names.
- Cross-agent sharing is allowed only for committed L4 documents and explicitly
  queried L3 episodes within the same project/tenant namespace.
- Draft artifacts, infeasible revisions, solver logs, tool ledgers, and active
  checkpoints must remain private to the run/session unless an audit caller is
  authorized.
- L1/checkpoint state retention may be short-lived. L3 successful episodes and
  L4 final/negative reports are retained for experiment reproducibility unless
  project retention policy says otherwise.

## 8. Provenance, Evidence, And CIAR Requirements

Responses should include provenance fields whenever available:

- source tier and source id;
- timestamp and producing agent;
- `session_id`/`thread_id`, `run_id`, `incident_id`, and project namespace;
- artifact lineage ids (`artifact_id`, `revision_id`, `feedback_id`,
  `commit_id`);
- deterministic solver status, IIS log ids/content hashes, and sandbox result
  ids;
- tool ledger entry ids and deterministic tool names;
- Phoenix trace/span ids or propagated `traceparent`;
- backend collection/schema metadata for L3/L4 records.

CIAR component exposure is useful for future fact retrieval, but not required
for current MVP writes. If YAAM returns CIAR metadata, include certainty, impact,
age decay, recency boost, final score, and explanation. Suppressed or superseded
evidence should be available only when `include_superseded=true` and the caller
has audit permission.

Example evidence table shape:

| evidence_id | source_tier | source_id | claim | evidence_payload | trace_id |
|---|---|---|---|---|---|
| `feedback-1` | Artifact feedback | `rev-1` | Revision exceeded NLRTM capacity. | IIS log content/hash | `trace-abc` |
| `tool-2` | Tool ledger | `tool-2` | Freight cost was computed by deterministic tool. | Tool args/output/status | `trace-def` |
| `sandbox-1` | External sandbox | `scenario-S2` | Scenario executed successfully. | Metrics/status/events | `trace-ghi` |
| `knowledge-1` | L4 | `report-run-1` | Final report was indexed. | Knowledge metadata | `trace-jkl` |

## 9. Security And Permission Requirements

- Read-only operations: lineage retrieval, context assembly, memory query,
  evidence table retrieval, health/config resources, and prompt rendering.
- Mutating operations: artifact draft creation, feedback attachment, revision
  creation, feasible final commit, L3 episode upsert, and L4 document upsert.
- Lifecycle operations: final artifact commit only. Autonomous promotion,
  consolidation, contradiction review, and distillation must not be triggered by
  this system in MVP.
- Mutating and lifecycle MCP tools must require explicit allowlisting for the
  SCM Cognitive Sandwich agent/project.
- MCP resources must not expose API keys, raw environment values, LLM secrets,
  unauthorized tenant data, or unrelated project memories.
- YAAM must fail closed on scope mismatch. A caller scoped to one run/session
  must not read drafts, solver feedback, or checkpoints from another run unless
  it has explicit audit permission.

## 10. Observability Requirements

- MCP and transitional direct calls should propagate W3C `traceparent` when an
  active OpenTelemetry span exists.
- YAAM responses should return trace ids or correlation ids so Phoenix traces,
  YAAM audit records, and run artifacts can be stitched together.
- Expected Phoenix-visible spans/events include artifact draft, attach feedback,
  create revision, commit final, memory query/context retrieval,
  L3 episode upsert, L4 document upsert, and evidence table retrieval.
- Required audit fields: tool/resource name, caller/agent id, `session_id`,
  `run_id`, project namespace, input artifact/resource ids, output ids, status,
  latency, error type, and warning count.
- Required metrics: call count, p50/p95 latency, error rate by tool/resource,
  retry count, partial-result count, L3/L4 backend write failures, and
  permission-denied count.

## 11. Reliability And Error Handling

- Retryable failures: transient network errors, backend 429s, backend 5xx, and
  timeouts from Qdrant/Typesense/YAAM service.
- Non-retryable failures: schema validation errors, missing required scope
  identifiers, unauthorized access, unknown artifact/revision ids, invalid
  embedding dimension, and commit attempts for non-feasible revisions.
- Retrieval may return partial results only when the response includes
  `partial=true`, warnings, and source-level error details.
- Mutating operations should be idempotent where possible through caller-supplied
  keys or deterministic payload hashes; duplicate retry should not create
  misleading lineage.
- LLM-backed extraction or embedding failures should fail fast for write
  workflows that require embeddings, and should not fabricate placeholder
  vectors or summaries.
- Expected error shape:

```json
{
  "error": {
    "code": "YAAM_SCOPE_MISSING",
    "message": "run_id is required for mutating SCM Cognitive Sandwich calls.",
    "retryable": false,
    "details": {
      "tool": "yaam.l3.upsert_episode",
      "missing_fields": ["run_id"]
    }
  },
  "trace_id": "trace-abc"
}
```

## 12. Performance Expectations

| Workflow | Expected QPS | p50 latency | p95 latency | Timeout budget | Notes |
|---|---:|---:|---:|---:|---|
| Artifact draft/feedback/revision/commit | 1-5 | <250 ms | <1 s | 5 s | Interactive repair loop; should be fast and deterministic. |
| Artifact lineage/context read | 1-5 | <500 ms | <2 s | 5 s | Used by audits and repair context assembly. |
| L3 episode upsert | <1 | <1 s excluding embedding | <3 s excluding embedding | 10 s | Embedding is produced by SCM before YAAM upsert in current flow. |
| L3/L4 scoped query | 1-3 | <750 ms | <3 s | 10 s | Must include source/provenance metadata. |
| L4 report upsert | <1 | <500 ms | <2 s | 10 s | Final and negative reports are not high-QPS. |
| Evidence table retrieval | <1 | <1 s | <5 s | 10 s | May aggregate several sources. |
| Health/config read | 1-5 | <100 ms | <500 ms | 2 s | Used by scripts and readiness checks. |

## 13. Acceptance Tests

| Test | Interface | Setup | Expected result |
|---|---|---|---|
| Artifact loop lineage | MCP artifact tools | Create infeasible routing draft, attach solver IIS, create repaired revision, attach feasible feedback, commit final. | Lineage shows draft, feedback, repaired revision, feasible commit, payload hashes, parent links, and commit rejects any infeasible revision. |
| Variant B persistence | MCP L3/L4 tools | Successful run provides one `Episode`, 4096-d embedding, one final `KnowledgeDocument`, `run_id`, `thread_id`, `incident_id`, and collection names. | L3 returns episode/vector id, L4 returns knowledge id, both include scope and trace metadata. |
| Negative-result indexing | MCP L4 tool | Fatal validation run submits `failed_run_log` document with judge findings and retry count. | L4 stores searchable negative evidence without creating a successful L3 episode. |
| Scope isolation | MCP tools/resources | Run two sessions with distinct `thread_id`/`run_id` values and query each scope. | Drafts, feedback, checkpoints, episodes, and search results remain isolated unless an explicit cross-session audit query is authorized. |
| Observability propagation | MCP tools/resources | Execute artifact write, L3 upsert, L4 upsert, and lineage read under an active trace. | Responses include trace/correlation ids; Phoenix shows YAAM call spans or events with status, latency, run id, and artifact/document ids. |
| Partial retrieval behavior | MCP evidence/context tools | Make one evidence source unavailable while other sources are reachable. | Read response returns available rows with `partial=true` and warnings; mutating operations still fail explicitly. |

## 14. Open Questions

- Should YAAM artifact lifecycle tools use the proposed `yaam.artifact.*` names,
  or align to existing YAAM internal artifact tool names?
- Should artifact lineage live in YAAM graph storage, L4 projections, or both
  when exposed through MCP?
- What tenant/project identifier should YAAM require in addition to
  `session_id`, `run_id`, and `agent_id`?
- Should REST v2 remain available for batch runners and CI verification, or is
  MCP plus direct facade parity sufficient?
- What exact authorization mechanism will allow SCM mutating tools while
  keeping MCP resources read-only by default?
- Should YAAM own evidence table assembly, or should YAAM return raw scoped
  records while SCM assembles the paper/report-specific table?
- How should negative-result L4 retention be configured for long-running
  experiment datasets?
