# Documentation Index

This directory is the repository source of truth. Keep AGENTS concise and keep details here.

## Hierarchy

1. `architecture/`: technical boundaries, runtime contracts, and environment harness.
2. `domain/`: business semantics and solver-facing constraints.
3. `decisions/`: ADRs for durable architecture choices.
4. `requirements/`: customer-facing integration requirements and interface requests.
5. `exec-plans/`: active work plans and maintenance logs.
6. `reports/`: dated run analyses and experiment diagnostics.

## Read Order

1. `architecture/index.md`
2. `domain/sandwich-loop.md`
3. `decisions/`
4. `requirements/`
5. `exec-plans/`
   - Completed plans are archived under `exec-plans/completed/`.

## Engineering Harness

- Create/update the repository environment using `uv` (Python 3.13):
	- `uv venv --python /usr/local/bin/python3.13`
	- `uv lock`
	- `uv sync --extra dev`
- Run repository commands from `.venv`:
	- `./.venv/bin/python -m pytest`
	- `./.venv/bin/ruff check .`
	- `./.venv/bin/python -m mypy src`
- Script execution should also use `.venv` Python (for example `python scripts/run_baseline.py`).

## Current Highlights

- YAAM customer interface requirements are captured under `requirements/`.
- Phoenix attribution normalizes to `openinference.project.name` during startup.
- Phoenix OpenAPI feedback-loop guide is available at `architecture/phoenix-openapi-feedback-loop.md`.
- Batch pipeline supports gradient disruptions and optional dual-disruption scenarios.
- Script contracts are covered by tests under `tests/scripts/`.
- Run analysis reports are cataloged under `reports/README.md`.
