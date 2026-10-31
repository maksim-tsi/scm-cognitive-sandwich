# IDWL 2026 — historical maritime study

Published antecedent: Maksim Ilin and Dmitry Pavlyuk, **“Cognitive Sandwich”
Architecture for LLM Agents in Logistics**, IDWL 2026,
[DOI 10.25673/123541](https://doi.org/10.25673/123541).

The separate [`idwl-26` branch](https://github.com/maksim-tsi/scm-cognitive-sandwich/tree/1be281e1ed80f3fc194181292115ecfc13176209)
is anchored at 31 May 2026, before the approximately mid-June workshop.
The branch date alone does not prove the exact executed runtime or deposited
paper input set. See `provenance/inventory.json` for immutable links and hashes.

Existing root paths remain available: `src/agents/` and `src/solver/` implement
the four-port world; `scripts/` contains generation/collection utilities;
`data/` contains original result tables; `docs/reports/` retains historical reports.
Use the pinned snapshot for historical reproduction, not current dev assumptions.

| Artifact | Rows | Meaning |
| --- | ---: | --- |
| data/scenarios_idwl_v1.csv | 100 | Generated candidate inputs |
| data/results_idwl_v1.csv | 78 | Main retained result batch |
| data/results_variant_b_batch.csv | 66 | Separate Variant B batch |

These denominators are not interchangeable or pooled with the later 60-incident
study or urban-freight experiments. Historical report interpretations are retained
as historical statements, not adopted as current cross-study superiority claims.
No results are rescored. Raw historical traces are not copied into study exports.
The original launch interface is documented in
[the legacy quick start](../../docs/legacy-maritime-quickstart.md).
A final publication-specific release tag remains subject to author approval.
