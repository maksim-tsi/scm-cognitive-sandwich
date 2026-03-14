# Architecture Docs

This directory documents the technical boundaries and implementation contracts of SCM Cognitive Sandwich.

## Files

- `index.md`: primary architecture guide.

## What changed recently

- Added explicit OpenTelemetry resource attribution guidance for Phoenix routing.
- Documented project-name precedence and normalization (`project.name` to `openinference.project.name`).
- Documented optional HTTPX instrumentation behavior and current trace-shape caveats.
