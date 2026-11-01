# Maritime research extension — August–September 2026

This package preserves the curated scientific evidence/code from local source
commit `cf1308557d071614533bac9197e8aff968737fa8`, supplementary revision 2.
Associated manuscript: **Typed Interfaces and Fail-Closed Verification for Language
Model Decision Support**, Maksim Ilin and Dmitry Pavlyuk. No acceptance or
publication is claimed. It extends, and cites, the published IDWL antecedent.

The scientific evidence predates some September editorial/follow-up work.
Later forwarder smoke/qualification is development evidence and not an extension
of the accepted scientific denominator. No calendar cutoff is used to combine runs.

- `evidence/terminals.jsonl`: 60 incidents, 59 analyzable.
- `evidence/des-replications.jsonl`: 15,400 retained DES rows, 11 admitted pairs.
- `evidence/accepted-metrics.json`, accepted-outcome.json and analysis.json:
  existing accepted outcomes; primary H1 unsupported, H2 exploratory.
- `code/analysis.py`: frozen numerical analysis implementation.
- `code/sandbox/`: historical evaluator/reference/admission/DES/generator modules.
- `code/*-excerpts.py.txt`: inspection excerpts, not standalone runnable modules.
- `provenance/`: original source provenance plus current public-export mapping.

The original Phase-A design inputs and generation source are not a certified
reconstruction of the exact executed input population. This export is not an end-to-end independent rerun of
model experiments. A package validator verifies file identity and row counts;
it does not rerun DES, model calls or statistical resampling.
Paper drafts and technical operation logs are excluded from the public export;
they remain preserved at source. Original files exported here are byte-identical.
The scope/limitations of the historical export have not been strengthened.
A final study release/tag requires author approval. Results are not pooled with
IDWL or Systems. Authored code/data use the root MIT license, subject to source
third-party notices; see the original sandbox dependency metadata.

## Added historical source material

- `prompts/`: byte-identical initial and repair templates used by the preserved
  builder, plus the builder/schema inspection excerpts under `code/`.
- `data/phase-a-design-inputs.json`: existing 180 design units, not an executed
  scientific population dump. No new scenario generation was performed.
- `examples/retained-des-allocations.json`: all 35 retained controller projections.
- `examples/recovered-canonical-responses.json`: 27 distinct original parsed
  response objects recovered with matching original terminal hashes. Raw serialized
  text is unavailable in the searched accepted-run outputs. The retained examples
  are success-conditioned and are not representative of all model operations.
- `provenance/historical-profile.json`: actual direct-provider scientific profile,
  kept separate from earlier OpenRouter qualification and later forwarder profiles.
- `development/forwarder/`: dated qualification/smoke/interface navigation only.

See [search decisions and unrecovered gaps](provenance/search-and-selection.md).
The scientific input-set binding remains unreconciled; do not promise independent
end-to-end regeneration or present design inputs as the executed cohort.

## Reproduce the retained summary without models

From the repository root, Python 3.13 (standard library only):

```sh
python3.13 studies/2026-maritime-extension/reproduction/reproduce.py --output /tmp/maritime-reproduction.json
```

This re-computes the original, seeded analysis from retained terminal rows and
requires exact equality with the saved analysis. It checks recorded DES rows,
canonical response hashes and original input-record hashes. It performs no new
inference, DES simulation, evaluator rescoring or reference adjudication. H1 remains
unsupported and H2 exploratory. Results stay separate from IDWL and Systems.
