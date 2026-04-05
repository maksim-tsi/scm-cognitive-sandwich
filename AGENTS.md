# Agent Directives: SCM Cognitive Sandwich

This file is a routing map. Keep it concise and defer deep details to `/docs`.

## Non-Negotiable Rules
- Sandwich boundary: LLMs translate/repair JSON artifacts; solver performs deterministic feasibility checks.
- YAAM integration: use only YAAM artifact tools through `src/memory/yaam_facade.py`; do not modify YAAM package internals.
- External ground truth: port status/capacity must come from maritime-port-sandbox API calls.
- Validation gate: run `ruff check .`, `python -m mypy src`, and `python -m pytest` for meaningful changes.
- Environment harness: run commands using repository `.venv` (for example `source .venv/bin/activate`).

## Workflow Loop
1. Discover: read task + relevant docs.
2. Plan: create/update plan in `/docs/exec-plans/` for complex work.
3. Execute: implement code and tests.
4. Validate: pass lint, typing, and tests.
5. Document: update `/docs` when behavior/contracts change.

## Docs Map
- `/docs/README.md`: top-level hierarchy and reading order.
- `/docs/architecture/index.md`: system boundaries, LangGraph, solver, memory, observability, and runtime harness.
- `/docs/domain/sandwich-loop.md`: artifact schema and feasibility-repair loop semantics.
- `/docs/decisions/`: ADRs for durable architecture choices.
- `/docs/exec-plans/`: active implementation plans and maintenance log.
- `/docs/exec-plans/completed/`: completed plan archive.
