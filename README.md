# SCM Cognitive Sandwich

This repository implements an Artifact-Centric "Sandwich" agent for maritime disruption rerouting.

The loop is deterministic where it must be and adaptive where it helps:
1. Upstream LLM translates disruption text into a strict routing JSON artifact.
2. OR solver validates feasibility against port capacities.
3. Downstream LLM repairs the artifact using solver feedback when infeasible.

## Core Components

- `src/agents/`: LangGraph nodes, routing logic, prompts, and typed state.
- `src/solver/`: Pyomo feasibility checker plus deterministic IIS-style conflict payload generation.
- `src/clients/`: External API clients (for example maritime port sandbox).
- `src/memory/`: YAAM artifact facade, YAAM consolidation client, and checkpointer factory.
- `src/core/`: Cross-cutting services such as observability bootstrap.
- `scripts/run_baseline.py`: Main runnable baseline scenario.

## Quick Start

### 1) Create environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 2) Configure environment variables

Create `.env` in repository root. Recommended observability block:

```bash
# --- OBSERVABILITY (Arize Phoenix) ---
PHOENIX_COLLECTOR_ENDPOINT=http://192.168.107.172:6006/v1/traces
PHOENIX_PROJECT_NAME=scm-cognitive-sandwich-idwl
OTEL_RESOURCE_ATTRIBUTES=openinference.project.name=scm-cognitive-sandwich-idwl,service.name=scm-cognitive-sandwich-idwl
```

Important:
- Do not define `OTEL_RESOURCE_ATTRIBUTES` twice in `.env`.
- If duplicated, the last assignment wins and may cause confusing attribution behavior.
- Legacy `project.name=...` is still accepted by this repo and normalized to `openinference.project.name` during startup.

### 3) Run baseline

```bash
python scripts/run_baseline.py --thread-id baseline-session
```

The runner prints tracing env diagnostics before tracing initialization, then streams node-level updates and final routing output.

## Observability Notes (Phoenix + OpenTelemetry)

Tracing setup lives in `src/core/observability.py` and currently:
- Loads env vars early from `.env`.
- Resolves project name from resource attributes first, then `PHOENIX_PROJECT_NAME`.
- Normalizes `project.name` into `openinference.project.name` for Phoenix routing.
- Builds an explicit `TracerProvider(resource=...)` before instrumenting LangChain.
- Optionally instruments HTTPX when `opentelemetry-instrumentation-httpx` is installed.

### Verify trace routing quickly

```bash
# Phoenix projects (CLI)
export PHOENIX_HOST="${PHOENIX_COLLECTOR_ENDPOINT%/v1/traces}"
npx @arizeai/phoenix-cli projects --format raw --no-progress

# Recent traces in target project (CLI)
export PHOENIX_PROJECT="scm-cognitive-sandwich-idwl"
npx @arizeai/phoenix-cli traces --limit 5 --last-n-minutes 15 --format raw --no-progress

# Projects via Phoenix API (curl)
curl -sS "${PHOENIX_HOST}/v1/projects" | jq '.data | map(.name)'
```

## Test and Quality Commands

```bash
ruff check .
python -m mypy src
python -m pytest -q
```

## Documentation Map

- `docs/architecture/index.md`: system boundaries, LangGraph flow, memory and tracing integration.
- `docs/domain/sandwich-loop.md`: domain model, constraints, IIS loop semantics.
- `docs/decisions/`: architecture and implementation ADRs.
- `docs/exec-plans/`: active execution plans and maintenance logs.

## License

MIT.

