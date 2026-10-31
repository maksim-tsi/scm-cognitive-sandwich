# Agent Directives: Cognitive Sandwich research repository

This repository contains successive studies with different experimental worlds.
Never transfer a study's operational assumptions to another study implicitly.

## Repository-wide preservation rules

- Preserve historical paths, commits, frozen scenarios, references and outcomes.
- Do not pool distinct cohorts, silently rescore outputs, or regenerate subject responses.
- No provider calls, remote compute, new collection, publication release/tag or
  merge without explicit authorization. Offline verification is the default.
- Keep credentials, private endpoints, third-party restricted media and raw traces
  out of new public exports. Record source hashes and transformations.
- Use a separate branch and a plan under `docs/exec-plans/` for complex work.

## Historical maritime scope: root src/, scripts/, data/, tests/, docs/

The following original rules apply to the historical implementation only:
- LLMs translate/repair JSON; the solver performs feasibility checks.
- YAAM integration uses `src/memory/yaam_facade.py`; do not alter YAAM internals.
- External maritime port ground truth comes from the maritime-port-sandbox API.
  This is an architectural rule, not authorization to contact that API.
- Validate historical changes with repository `.venv`: `ruff check .`,
  `python -m mypy src`, `python -m pytest`. Do not replace its environment.

## studies/ scope

Follow the study's own AGENTS.md, reproduction instructions and pinned contracts.
Maritime API/YAAM/port-authority rules do not apply to the synthetic Padua world.
Run the relevant offline study checks and confirm historical files remain intact.
Study exports may preserve historical source formatting; do not reformat frozen
scientific algorithms just to satisfy a different study's tooling.

## Documentation map

- README.md: current research and historical navigation.
- studies/*/README.md: publication-specific contracts and reproduction levels.
- docs/legacy-maritime-quickstart.md: preserved legacy launch interface.
- docs/architecture/, docs/domain/, docs/decisions/: historical maritime design.
