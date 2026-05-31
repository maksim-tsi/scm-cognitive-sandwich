# SCM Cognitive Sandwich YAAM Readiness Report

**Date:** 2026-05-31  
**Consumer project:** `scm-cognitive-sandwich`  
**YAAM project namespace:** `YAAM_PROJECT_ID=scm-cognitive-sandwich`  
**Repository commit:** `5297445 chore: add read-only YAAM readiness checks`  
**Test mode:** read-only readiness plus approved write-enabled synthetic L2/L3/L4 artifact evidence test  
**Operator environment:** MacBook client against shared `skz-data-lv` YAAM runtime

## Executive Summary

SCM Cognitive Sandwich is ready for read-only YAAM consumer readiness usage through MCP v1 with REST v2 smoke coverage.

The shared YAAM runtime is reachable and healthy. Generic MCP memory/context calls, evidence table assembly, read-only resources, Cognitive Sandwich domain-pack resources, and domain-specific prompts all work. REST v2 health, context, query, and L3 semantic query also work with benchmark runtime scoping and leakage guard metadata.

After the initial read-only run, a write-enabled synthetic L2/L3/L4 artifact evidence test was authorized and executed. Generic L2, L3, and L4 writes succeeded and generic readback retrieved the synthetic evidence. Cognitive Sandwich domain-pack projections retrieved the L2/L3 artifact evidence but did not include the generic L4 finalized artifact in artifact lineage/resource counts, which remains a domain-pack projection gap.

## Environment And Configuration

| Item | Value |
| --- | --- |
| MCP endpoint | `http://192.168.107.187:8003/mcp` |
| REST endpoint | `http://192.168.107.187:8002` |
| Phoenix endpoint | `http://192.168.107.187:6006/v1/traces` |
| Phoenix project | `scm-cognitive-sandwich-winsim` |
| LLM provider | OpenRouter |
| Default LLM | `tencent/hy3-preview` |
| Embedding model | `qwen/qwen3-embedding-8b` |
| Embedding dimension | `4096` |
| PostgreSQL host | `192.168.107.187:5432` |
| YAAM domain packs | `auto` |

Local configuration was verified from `.env` and `.env.example`. Provider secrets and database credentials were not copied into this report.

## Checks Performed

### Local Validation Gate

| Check | Result |
| --- | --- |
| `./.venv/bin/ruff check .` | Pass |
| `./.venv/bin/python -m mypy src` | Pass; one informational note about unchecked untyped function bodies |
| `./.venv/bin/python -m pytest` | Pass: 65 passed, 1 skipped |

### MCP v1 Readiness

Command:

```bash
./.venv/bin/python scripts/verify_yaam_readiness.py \
  --session-id scm-cognitive-sandwich-readiness-20260531-report \
  --agent-id codex-macbook-readiness-report
```

Observed result:

| MCP check | Result |
| --- | --- |
| Initialize Streamable HTTP MCP | Pass: `yaam-mcp-v1`, version `1.12.4` |
| Tool discovery | Pass: 16 tools discovered |
| Static resource discovery | Pass: 5 resources discovered |
| `yaam://config/ciar` | Pass: readable |
| `yaam.health.check` | Pass: status `ok` |
| Nonexistent fact scoping guard | Pass: `yaam://facts/nonexistent-readiness-fact` returned `not_found` |
| `yaam.memory.get_context` | Pass: empty context, `leakage_guard_passed=true` |
| `yaam.evidence.table` | Pass: assembled, 0 rows, `partial=false` |
| Cognitive Sandwich prompts | Pass: both prompts render |

### Cognitive Sandwich Domain Pack

Discovery included all expected read-only resource templates:

- `yaam://artifacts/{artifact_id}/lineage`
- `yaam://sessions/{session_id}/artifacts`
- `yaam://runs/{run_id}/artifacts`
- `yaam://runs/{run_id}/evidence`
- `yaam://incidents/{incident_id}/reports`

Read-only projection checks were also executed with synthetic identifiers. All returned scoped empty projections with `project_id=scm-cognitive-sandwich`, `partial=false`, and `warnings=[]`.

| Resource | Result |
| --- | --- |
| `yaam://artifacts/artifact-readiness-001/lineage` | Pass: `artifact_lineage`, 0 items |
| `yaam://sessions/scm-cognitive-sandwich-readiness-20260531-report/artifacts` | Pass: `session_artifacts`, 0 artifacts |
| `yaam://runs/artifact-run-001/artifacts` | Pass: `run_artifacts`, 0 artifacts |
| `yaam://runs/artifact-run-001/evidence` | Pass: `run_evidence`, 0 evidence rows |
| `yaam://incidents/incident-readiness-001/reports` | Pass: `incident_reports`, 0 items |

Prompt discovery and rendering included:

- `yaam.prompt.artifact_repair_context`
- `yaam.prompt.artifact_lineage_summary`

### REST v2 Smoke

| REST check | Result |
| --- | --- |
| `GET /health` | Pass: status `ok` |
| `POST /v2/memory/context` | Pass: empty scoped context, `leakage_guard_passed=true` |
| `POST /v2/memory/query` | Pass: empty results, leakage guard passed |
| `POST /v2/memory/l3/query` with `nl_query` | Pass: status `success`, empty results |

No REST write or write-adjacent negative test was executed. In read-only mode, the nonexistent fact MCP resource lookup was used as the safety/scoping negative check.

### Write-Enabled Synthetic Artifact Evidence

Write-enabled synthetic test scope:

| Field | Value |
| --- | --- |
| Session | `scm-cognitive-sandwich-readiness-20260531T135506Z-write` |
| Run | `artifact-run-20260531T135506Z` |
| Artifact | `artifact-readiness-20260531T135506Z` |
| Agent | `codex-macbook-write-readiness` |
| Metadata domain | `cognitive_sandwich` |

Synthetic metadata followed the YAAM readiness guidance: `artifact_id`, `revision_id`, `parent_revision_id`, `feedback_id`, `commit_id`, `run_id`, `thread_id`, `incident_id`, `scenario_id`, `artifact_kind`, `artifact_status`, `revision_number`, `verification_state`, `feedback_type`, `source_system`, `payload_hash`, `fatal_status`, and `retry_count`.

| Operation | Result |
| --- | --- |
| `yaam.l2.store_fact` | Pass: created `0160efee-bd02-405a-b4b4-098e3e7fdc5b`, provenance source tier `L2` |
| `yaam.l3.assimilate_episode` | Pass: created `ep-9d9d6824`, provenance source tier `L3` |
| `yaam.l4.finalize_artifact` | Pass: created `kd-1324f80a`, provenance source tier `L4` |
| `yaam.l2.search_facts` | Pass: retrieved synthetic solver feedback with canonical metadata |
| `yaam.l3.search_episodes` | Pass: retrieved synthetic artifact episode `ep-9d9d6824` |
| `yaam.l4.search_knowledge` | Pass: retrieved finalized synthetic artifact `kd-1324f80a` |
| `yaam.evidence.table` | Pass: returned L3 and L4 evidence rows with provenance |

Domain-pack readback after writes:

| Resource | Result |
| --- | --- |
| `yaam://artifacts/artifact-readiness-20260531T135506Z/lineage` | Partial: 2 items, `l2=1`, `l3=1`, `l4=0`, `partial=false` |
| `yaam://sessions/scm-cognitive-sandwich-readiness-20260531T135506Z-write/artifacts` | Partial: 1 artifact, `l2=1`, `l3=1`, `l4=0`, `partial=false` |
| `yaam://runs/artifact-run-20260531T135506Z/artifacts` | Partial: 1 artifact, `l2=1`, `l3=1`, `l4=0`, `partial=false` |
| `yaam://runs/artifact-run-20260531T135506Z/evidence` | Partial: 2 evidence items, `l2=1`, `l3=1`, `l4=0`, `partial=false` |
| `yaam://incidents/incident-readiness-001/reports` | Partial: 0 reports, `partial=false` |

Finding: generic L4 storage and search work, and the evidence table includes the finalized L4 artifact. However, Cognitive Sandwich domain-pack resource projections did not surface the L4 finalized artifact or incident report projection from the generic L4 record. This does not block generic memory use, but it does limit domain-pack artifact lineage completeness.

## Requirement Classification

| Requirement | Classification | Evidence |
| --- | --- | --- |
| `YAAM-REQ-0002` MCP memory query | Implemented | Scoped MCP context and REST query returned success with leakage guard metadata. |
| `YAAM-REQ-0003` MCP context assembly | Implemented | `yaam.memory.get_context` returned structured empty context with `leakage_guard_passed=true`. |
| `YAAM-REQ-0006` L3 episode assimilation | Implemented | `yaam.l3.assimilate_episode` created `ep-9d9d6824` with provenance. |
| `YAAM-REQ-0007` L3 semantic query | Implemented | REST `/v2/memory/l3/query` returned status `success`. |
| `YAAM-REQ-0008` L4 final artifact storage | Implemented generically | `yaam.l4.finalize_artifact` created `kd-1324f80a`; generic L4 search retrieved it. Domain-pack projections did not include it. |
| `YAAM-REQ-0009` Provenance | Implemented generically, partial in domain views | L2/L3/L4 write acknowledgements and generic readback returned source-tier/source-id provenance. Domain-pack resources omitted the L4 projection. |
| `YAAM-REQ-0010` Scoping | Implemented | Nonexistent fact returned `not_found`; context/query calls returned no cross-project leakage and leakage guard passed. |
| `YAAM-REQ-0011` Read-only MCP resources | Implemented | Static resources and Cognitive Sandwich domain resources discovered and read successfully. |
| `YAAM-REQ-0012` Allowlisted MCP writes | Implemented for generic L2/L3/L4 | Authorized synthetic writes succeeded through MCP tools. Dedicated artifact lifecycle writes remain missing. |
| `YAAM-REQ-0016` Evidence Table | Implemented for generic evidence, partial for artifact lineage completeness | Evidence table returned L3 and L4 rows with provenance after synthetic writes. |
| `YAAM-REQ-0019` Artifact draft/revision/feedback/commit lineage | Partial | Domain pack exposes metadata-derived lineage views, but there is no native lifecycle graph enforcement in current YAAM. |
| `YAAM-REQ-0020` Artifact lineage resources | Partial | Resource templates exist and read successfully. After writes, projections included L2/L3 evidence but not the generic L4 finalized artifact. |
| `YAAM-REQ-0021` Deterministic feedback/solver evidence | Implemented generically, partial in domain views | L2 solver feedback and L3 episode were written and retrieved; L4 final artifact was retrieved generically and through evidence table, but not through domain resource projections. |
| `YAAM-REQ-0028` Transitional facade until MCP parity | Partial | Generic MCP is adequate for temporary read/context/evidence flows; dedicated artifact mutation remains absent. |
| `YAAM-REQ-0030` Autonomous lifecycle consolidation | Deferred | Explicitly outside current YAAM capability. |
| `YAAM-REQ-0032` Domain-specific artifact prompts | Implemented | `yaam.prompt.artifact_repair_context` and `yaam.prompt.artifact_lineage_summary` discovered and rendered. |

## Product Gaps

- Dedicated mutating `yaam.artifact.*` lifecycle tools: missing.
- First-class draft/revision/feedback/commit graph model: partially implemented at most; current domain pack projects lineage from metadata and does not enforce lifecycle transitions.
- Cognitive Sandwich domain-pack L4 projection: generic L4 final artifacts are searchable and appear in evidence table, but were not included in artifact lineage/run/incident domain resource counts in this test.
- Evidence table usefulness for artifact repair: implemented for generic L3/L4 evidence rows; usefulness would improve if domain-pack projections also included L4 final artifacts.
- Autonomous consolidation/distillation: deferred.

## Readiness Questions

**Is generic MCP memory/context enough for temporary integration?**  
Yes for read-only temporary integration. Scoped context, evidence table, read-only resources, and prompts are usable. It is not enough to replace artifact lifecycle mutation.

**Which artifact lifecycle primitive is the first blocker for production use?**  
Native artifact revision lifecycle is the first blocker: draft, feedback, revision, commit, and feasibility transition semantics need first-class YAAM support or a dedicated artifact MCP surface.

**Does generic L3/L4 storage preserve enough provenance for artifact repair audit?**  
Yes for generic storage and search: L3 and L4 write acknowledgements, generic readback, and evidence table rows included source-tier/source-id provenance. The domain-pack artifact resources still need L4 projection coverage before they provide a complete artifact audit view.

**Do artifact resources and prompts reduce dependence on the transitional facade?**  
Yes for read-only inspection and repair-context assembly over L2/L3 metadata. They do not yet eliminate the facade for artifact mutation, lifecycle enforcement, or complete L4 final artifact lineage.

**Are write gates and read-only resources acceptable for agent safety?**  
Yes. Read-only resources behaved safely in this run, and the previous nonexistent-fact scoping anomaly is resolved.

**Can the project migrate away from transitional facade usage with current MCP surface?**  
Only partially. Generic read/write memory and evidence can move toward MCP, but dedicated artifact mutation and complete domain-pack L4 lineage remain required before full migration.

## Conclusion

YAAM is ready for SCM Cognitive Sandwich read-only readiness and generic write-enabled synthetic L2/L3/L4 artifact evidence storage. The Cognitive Sandwich domain pack is enabled and useful for L2/L3 artifact/evidence projections and prompt generation. Production artifact lifecycle integration still requires dedicated artifact MCP semantics and improved domain-pack projection of generic L4 finalized artifacts.
