# Prospective publication-specific releases

No final tag/release is created by this preparation PR. After author approval,
create immutable source-linked releases separately, never force-move existing refs:

- `idwl-2026-v1`: published antecedent, confirmed source snapshot/limitations.
- `maritime-extension-2026-v1`: curated 60-incident extension; unpublished status.
- `systems-urban-freight-2026-v1`: Systems research package; retain manuscript
  status until the journal actually publishes it; add DOI only when assigned.

Each release should include its own CITATION.cff, file/hash manifest, provenance,
rights notice and qualified reproduction levels. Version the release package,
not scientific results. Any later correction must preserve earlier packages and
state whether code/configuration or scientific interpretation changed.


## Prepared candidates

See `release-candidates/` for publication-specific notes, a deterministic archive
builder and checksums. These are preparation artifacts for author review. No final
GitHub release or publication tag is created automatically. IDWL is a navigation/
source-anchor package; its preserved historical code remains at the pinned public
commit. The maritime extension supports retained-summary reproduction with explicit
execution-input gaps. Systems supports both results and original-proposal I2/I3
replay. Its entire study directory remains unchanged by historical completion.
