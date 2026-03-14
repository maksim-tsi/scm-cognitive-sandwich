# Documentation Index

This folder is the source of truth for system intent, constraints, and current execution plans.

## Sections

- `architecture/`: system boundaries, component responsibilities, and tracing architecture.
- `domain/`: business semantics and deterministic solver constraints.
- `decisions/`: architectural decision records (ADRs).
- `exec-plans/`: active implementation plans and maintenance logs.

## Start Here

1. Read `architecture/index.md` for component boundaries.
2. Read `domain/sandwich-loop.md` for artifact schema and feasibility loop semantics.
3. Review `decisions/` for pinned model and architecture choices.
4. Check `exec-plans/active/` for current implementation history.

## Recent Highlights (March 2026)

- OpenTelemetry/Phoenix project attribution is now normalized to `openinference.project.name` at startup.
- Baseline runner prints tracing env values before tracing initialization for easier diagnostics.
- Optional HTTPX instrumentation is available to capture external HTTP spans.
- Documentation now standardizes one `OTEL_RESOURCE_ATTRIBUTES` declaration in `.env`.
