# Documentation Index

This directory is the repository source of truth. Keep AGENTS concise and keep details here.

## Hierarchy

1. `architecture/`: technical boundaries, runtime contracts, and environment harness.
2. `domain/`: business semantics and solver-facing constraints.
3. `decisions/`: ADRs for durable architecture choices.
4. `exec-plans/`: active work plans and maintenance logs.
5. `reports/`: dated run analyses and experiment diagnostics.

## Read Order

1. `architecture/index.md`
2. `domain/sandwich-loop.md`
3. `decisions/`
4. `exec-plans/`
   - Completed plans are archived under `exec-plans/completed/`.

## Engineering Harness

- Run repository commands from `.venv`:
	- `source .venv/bin/activate`
	- `python -m pytest`
	- `ruff check .`
	- `python -m mypy src`
- Script execution should also use `.venv` Python (for example `python scripts/run_baseline.py`).

## Current Highlights

- Phoenix attribution normalizes to `openinference.project.name` during startup.
- Phoenix OpenAPI feedback-loop guide is available at `architecture/phoenix-openapi-feedback-loop.md`.
- Batch pipeline supports gradient disruptions and optional dual-disruption scenarios.
- Script contracts are covered by tests under `tests/scripts/`.
- Run analysis reports are cataloged under `reports/README.md`.
