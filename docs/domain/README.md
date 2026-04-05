# Domain Docs

This directory captures problem semantics for the sandwich loop.

## Files

- `sandwich-loop.md`: baseline maritime rerouting scenario, routing artifact schema, solver constraints, and IIS-style repair loop behavior.

## Scope Boundary

- Keep this layer domain-focused (artifact semantics, solver constraints, repair-loop behavior).
- Runtime/setup mechanics belong in `docs/architecture/index.md`.

## Recent updates

- Clarified current solver backend behavior (`appsi_highs` with `scip` fallback).
- Added observability notes relevant to loop diagnostics and Phoenix project attribution.
- Included gradient-disruption context used by IDWL batch scenario generation.
