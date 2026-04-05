# Phoenix OpenAPI Feedback Loop Guide

This guide describes how to use Phoenix through its OpenAPI interface for observability-driven feedback loops and continuous refinement of the SCM Cognitive Sandwich agent.

## Goal

Use Phoenix trace and span data to:

1. Verify traces are ingested and attributed to the correct project.
2. Diagnose solver and repair-loop behavior at node level.
3. Attach structured human or automated feedback to spans/traces/sessions.
4. Re-run scenarios and compare outcomes over time.

## Prerequisites

1. Phoenix is reachable and has OpenAPI enabled.
2. Runtime tracing is enabled in scripts via `setup_observability()`.
3. Environment values are set consistently:
   - `PHOENIX_COLLECTOR_ENDPOINT` (for example `http://host:6006/v1/traces`)
   - `PHOENIX_PROJECT_NAME` (for example `scm-cognitive-sandwich-idwl`)
   - `OTEL_RESOURCE_ATTRIBUTES` including `openinference.project.name=<project>`

## Base URL and Project Resolution

Phoenix API base URL is derived from collector endpoint by removing `/v1/traces`.

Example:

```bash
PHOENIX_COLLECTOR_ENDPOINT=http://192.168.107.172:6006/v1/traces
PHOENIX_BASE=${PHOENIX_COLLECTOR_ENDPOINT%/v1/traces}
PROJECT=scm-cognitive-sandwich-winsim
```

## Step 1: Confirm API Surface

```bash
curl -sS "$PHOENIX_BASE/openapi.json" | jq -r '.info'
curl -sS "$PHOENIX_BASE/v1/projects" | jq '.data[] | {name, id}'
```

Expected result:

1. OpenAPI document is returned.
2. The target project appears in `/v1/projects`.

## Step 2: Generate a Fresh Trace Window

Use a short run with known timestamps.

```bash
START_TS=$(date -u +%FT%TZ)
python scripts/batch_runner.py --limit 2
END_TS=$(date -u +%FT%TZ)
echo "$START_TS -> $END_TS"
```

Tip:

1. Keep run windows short to reduce noise.
2. Use deterministic `thread_id` patterns (already present in batch runner) for easier filtering.

## Step 3: Query Spans for the Time Window

Primary endpoint:

```bash
curl -sS \
  "$PHOENIX_BASE/v1/projects/$PROJECT/spans?start_time=$START_TS&end_time=$END_TS&limit=1000" \
  > /tmp/phoenix_spans_window.json

jq '.data | length' /tmp/phoenix_spans_window.json
jq -r '.data[].attributes["metadata.thread_id"] // empty' /tmp/phoenix_spans_window.json | sort | uniq -c
jq -r '.data[].name' /tmp/phoenix_spans_window.json | sort | uniq -c
```

OTLP-formatted equivalent:

```bash
curl -sS \
  "$PHOENIX_BASE/v1/projects/$PROJECT/spans/otlpv1?start_time=$START_TS&end_time=$END_TS&limit=1000" \
  > /tmp/phoenix_spans_otlp_window.json
```

Pass criteria:

1. `data` count is greater than zero.
2. Expected graph nodes appear (for example `LangGraph`, `node_run_solver`, `node_repair_artifact`).
3. Expected thread IDs appear for the run.

### If windowed queries return 0 spans

Phoenix supports omitting the time window and simply requesting the most recent spans within a project. This is a fast sanity check when ingestion delay or timestamp formatting issues are suspected.

```bash
curl -sS \
  "$PHOENIX_BASE/v1/projects/$PROJECT/spans?limit=200" \
  > /tmp/phoenix_spans_recent.json

jq '.data | length' /tmp/phoenix_spans_recent.json
jq -r '.data[].attributes["metadata.thread_id"] // empty' /tmp/phoenix_spans_recent.json | sort | uniq -c
jq -r '.data[].name' /tmp/phoenix_spans_recent.json | sort | uniq -c
```

### Recommended timestamp format (RFC3339 with milliseconds)

The REST API accepts `start_time` and `end_time` as `date-time` strings. In practice, using millisecond precision avoids ambiguity when runs start/end within the same second.

macOS / BSD `date` example:

```bash
START_TS=$(date -u -v-15M +%Y-%m-%dT%H:%M:%S.000Z)
END_TS=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
```

Then query:

```bash
curl -sS \
  "$PHOENIX_BASE/v1/projects/$PROJECT/spans?start_time=$START_TS&end_time=$END_TS&limit=1000" \
  > /tmp/phoenix_spans_window.json
```

## Step 4: Validate Project Attribution

Compare target and default project in the same time window.

```bash
curl -sS \
  "$PHOENIX_BASE/v1/projects/$PROJECT/spans?start_time=$START_TS&end_time=$END_TS&limit=1000" \
  | jq '.data | length'

curl -sS \
  "$PHOENIX_BASE/v1/projects/default/spans?start_time=$START_TS&end_time=$END_TS&limit=1000" \
  | jq '.data | length'
```

Expected pattern:

1. Target project has non-zero spans.
2. Default project has zero spans for that same run window.

## Step 5: Close the Feedback Loop with Annotations

Phoenix supports feedback annotations at trace/span/session levels.

### Trace-level feedback

```bash
TRACE_ID=<hex_trace_id>

curl -sS -X POST "$PHOENIX_BASE/v1/trace_annotations" \
  -H 'Content-Type: application/json' \
  -d '{
    "data": [
      {
        "name": "solver_loop_quality",
        "annotator_kind": "HUMAN",
        "trace_id": "'"$TRACE_ID"'",
        "result": {
          "label": "non_convergent",
          "score": 0.1,
          "explanation": "Exceeded recursion limit due to repeated infeasible repairs."
        },
        "metadata": {
          "workflow": "batch_runner",
          "action": "tighten downstream repair prompt"
        }
      }
    ]
  }'
```

### Span-level feedback

```bash
SPAN_ID=<hex_span_id>

curl -sS -X POST "$PHOENIX_BASE/v1/span_annotations" \
  -H 'Content-Type: application/json' \
  -d '{
    "data": [
      {
        "name": "node_repair_artifact_diagnostic",
        "annotator_kind": "HUMAN",
        "span_id": "'"$SPAN_ID"'",
        "result": {
          "label": "insufficient_repair",
          "score": 0.2,
          "explanation": "Repair proposal still violates zero-capacity ports."
        }
      }
    ]
  }'
```

## Step 6: Continuous Refinement Workflow

Use the same loop for each refinement cycle:

1. Run a deterministic trial (`--limit` or fixed scenarios).
2. Pull windowed spans from target project.
3. Quantify failures:
   - recursion-limit traces
   - repeated `node_repair_artifact` loops
   - repeated solver infeasibility logs
4. Add annotations that encode root cause and proposed remediation.
5. Apply prompt/logic update in repository.
6. Re-run the same scenarios and compare windowed span signatures and outcomes.

## Useful Queries for This Repository

1. Check if solver/repair loops are dominating:

```bash
jq -r '.data[].name' /tmp/phoenix_spans_window.json | sort | uniq -c | sort -nr
```

2. Isolate run thread IDs:

```bash
jq -r '.data[].attributes["metadata.thread_id"] // empty' /tmp/phoenix_spans_window.json | sort | uniq -c
```

3. Inspect LangGraph node path metadata:

```bash
jq -r '.data[] | select(.name=="node_run_solver" or .name=="node_repair_artifact") | [.start_time, .attributes["metadata.langgraph_node"], .attributes["metadata.thread_id"]] | @tsv' /tmp/phoenix_spans_window.json
```

## Troubleshooting

1. No spans in target project:
   - Confirm `setup_observability()` is called before graph execution.
   - Confirm `PHOENIX_COLLECTOR_ENDPOINT` is reachable.
   - Confirm `openinference.project.name` is present after startup normalization.
2. Spans only in default project:
   - Check duplicate `OTEL_RESOURCE_ATTRIBUTES` declarations in `.env`.
   - Verify runtime startup prints normalized resource attributes.
3. Old data only, no fresh traces:
   - Tighten `start_time` and `end_time` window.
   - Retry query after a short ingestion delay.
4. Trace endpoint returns HTML shell:
   - Use project span APIs (`/v1/projects/{project}/spans`) for machine-readable evidence.

## Operational Notes

1. Prefer API-driven verification in automation and CI diagnostics.
2. Use Phoenix CLI as optional convenience, not as the only source of truth.
3. Keep annotation names stable (`solver_loop_quality`, `node_repair_artifact_diagnostic`) so longitudinal analysis remains consistent.
