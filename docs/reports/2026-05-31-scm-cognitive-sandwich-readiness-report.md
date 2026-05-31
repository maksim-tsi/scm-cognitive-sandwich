# SCM Cognitive Sandwich YAAM Readiness Report

**Date:** 2026-05-31  
**Consumer project:** `scm-cognitive-sandwich`  
**YAAM project namespace:** `YAAM_PROJECT_ID=scm-cognitive-sandwich`  
**Repository commit:** `5297445 chore: add read-only YAAM readiness checks`  
**Test mode:** read-only readiness, no synthetic writes  
**Operator environment:** MacBook client against shared `skz-data-lv` YAAM runtime

## Executive Summary

SCM Cognitive Sandwich is ready for read-only YAAM consumer readiness usage through MCP v1 with REST v2 smoke coverage.

The shared YAAM runtime is reachable and healthy. Generic MCP memory/context calls, evidence table assembly, read-only resources, Cognitive Sandwich domain-pack resources, and domain-specific prompts all work. REST v2 health, context, query, and L3 semantic query also work with benchmark runtime scoping and leakage guard metadata.

Synthetic write/read validation was intentionally not executed because YAAM has not opened a write window for this run. Requirements that depend on L2/L3/L4 synthetic write evidence are therefore classified as partial or not exercised rather than failed.

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

## Requirement Classification

| Requirement | Classification | Evidence |
| --- | --- | --- |
| `YAAM-REQ-0002` MCP memory query | Implemented | Scoped MCP context and REST query returned success with leakage guard metadata. |
| `YAAM-REQ-0003` MCP context assembly | Implemented | `yaam.memory.get_context` returned structured empty context with `leakage_guard_passed=true`. |
| `YAAM-REQ-0006` L3 episode assimilation | Not exercised | Requires a write window; no L3 assimilation was run. |
| `YAAM-REQ-0007` L3 semantic query | Implemented | REST `/v2/memory/l3/query` returned status `success`. |
| `YAAM-REQ-0008` L4 final artifact storage | Not exercised | Requires a write window; no L4 finalization was run. |
| `YAAM-REQ-0009` Provenance | Partial | REST L3 query returned provenance with agent/session; evidence table had no rows in fresh namespace, so row-level evidence provenance is not yet validated. |
| `YAAM-REQ-0010` Scoping | Implemented | Nonexistent fact returned `not_found`; context/query calls returned no cross-project leakage and leakage guard passed. |
| `YAAM-REQ-0011` Read-only MCP resources | Implemented | Static resources and Cognitive Sandwich domain resources discovered and read successfully. |
| `YAAM-REQ-0012` Allowlisted MCP writes | Not exercised | Write tools are discoverable but were not called in read-only mode. |
| `YAAM-REQ-0016` Evidence Table | Partial | Tool executed successfully, but returned 0 rows because no synthetic evidence was written during this run. |
| `YAAM-REQ-0019` Artifact draft/revision/feedback/commit lineage | Partial | Domain pack exposes metadata-derived lineage views, but there is no native lifecycle graph enforcement in current YAAM. |
| `YAAM-REQ-0020` Artifact lineage resources | Implemented | All Cognitive Sandwich read-only resource templates were discovered and returned scoped projections. |
| `YAAM-REQ-0021` Deterministic feedback/solver evidence | Partial | Generic evidence/resource paths are available, but deterministic feedback write/read evidence was deferred to a write window. |
| `YAAM-REQ-0028` Transitional facade until MCP parity | Partial | Generic MCP is adequate for temporary read/context/evidence flows; dedicated artifact mutation remains absent. |
| `YAAM-REQ-0030` Autonomous lifecycle consolidation | Deferred | Explicitly outside current YAAM capability. |
| `YAAM-REQ-0032` Domain-specific artifact prompts | Implemented | `yaam.prompt.artifact_repair_context` and `yaam.prompt.artifact_lineage_summary` discovered and rendered. |

## Product Gaps

- Dedicated mutating `yaam.artifact.*` lifecycle tools: missing.
- First-class draft/revision/feedback/commit graph model: partially implemented at most; current domain pack projects lineage from metadata and does not enforce lifecycle transitions.
- Deterministic solver feedback audit through L2/L3/L4: not fully validated without a write window.
- Evidence table usefulness for artifact repair: partial until synthetic or real artifact evidence exists in namespace.
- Autonomous consolidation/distillation: deferred.

## Readiness Questions

**Is generic MCP memory/context enough for temporary integration?**  
Yes for read-only temporary integration. Scoped context, evidence table, read-only resources, and prompts are usable. It is not enough to replace artifact lifecycle mutation.

**Which artifact lifecycle primitive is the first blocker for production use?**  
Native artifact revision lifecycle is the first blocker: draft, feedback, revision, commit, and feasibility transition semantics need first-class YAAM support or a dedicated artifact MCP surface.

**Does generic L3/L4 storage preserve enough provenance for artifact repair audit?**  
Not proven in this read-only run. Generic paths and domain projections are available, but provenance quality for deterministic feedback and final artifacts must be verified during a synthetic write window.

**Do artifact resources and prompts reduce dependence on the transitional facade?**  
Yes for read-only inspection and repair-context assembly. They do not eliminate the facade for artifact mutation and lifecycle enforcement.

**Are write gates and read-only resources acceptable for agent safety?**  
Yes. Read-only resources behaved safely in this run, and the previous nonexistent-fact scoping anomaly is resolved.

**Can the project migrate away from transitional facade usage with current MCP surface?**  
Only partially. Read-only context/evidence can move toward MCP. Dedicated artifact mutation remains required before full migration.

## Conclusion

YAAM is ready for SCM Cognitive Sandwich read-only readiness and ordinary non-mutating consumer validation. The Cognitive Sandwich domain pack is enabled and useful for read-only artifact/evidence projections and prompt generation. Production artifact lifecycle integration still requires either a dedicated artifact MCP surface or an explicit write-enabled generic L2/L3/L4 workflow validated during a YAAM write window.
