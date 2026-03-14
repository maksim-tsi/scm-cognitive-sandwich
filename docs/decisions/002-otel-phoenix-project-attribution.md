# ADR 002: OpenTelemetry Project Attribution for Phoenix

## Status
Accepted

## Context

LangGraph traces were reaching Phoenix but were routed to the `default` project instead of the intended project.

The runtime had `OTEL_RESOURCE_ATTRIBUTES=project.name=<project>`, but Phoenix project assignment for this stack depends on OpenInference-compatible resource attribution.

## Decision

1. Normalize project attribution at startup in `src/core/observability.py`.
2. Resolve project name with precedence:
   - `openinference.project.name` from `OTEL_RESOURCE_ATTRIBUTES`
   - legacy `project.name` from `OTEL_RESOURCE_ATTRIBUTES`
   - `PHOENIX_PROJECT_NAME`
3. Map legacy `project.name` into `openinference.project.name` when needed.
4. Build `TracerProvider` with explicit `Resource` containing normalized attributes.
5. Keep `OTEL_RESOURCE_ATTRIBUTES` synchronized in-process for downstream instrumentors.
6. Add baseline env diagnostics in `scripts/run_baseline.py` before observability initialization.

## Consequences

- Fresh baseline traces route to the intended Phoenix project.
- Legacy env settings remain backward-compatible.
- Duplicate `OTEL_RESOURCE_ATTRIBUTES` entries in `.env` remain risky because the last assignment wins; docs now recommend a single declaration.
- Optional HTTPX instrumentation can surface HTTP spans, but those spans may appear as separate root traces depending on instrumentation/runtime context boundaries.
