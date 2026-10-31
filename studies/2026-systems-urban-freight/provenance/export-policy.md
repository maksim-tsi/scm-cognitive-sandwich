# Artifact provenance and transformation policy

`source-export.json` identifies each copied/extracted/derived source artifact by
original repository commit, path/member and SHA-256, exported path and SHA-256,
and transformation. Compact packets additionally bind every original world trace
by member path/hash (or the diagnostic record) and its originating result member.
Reference/scenario files retain their original bytes. Sample final texts also
record original wire-envelope hashes without publishing those envelopes.

`package-manifest.json` covers all non-transient package files except itself.
New export support (README, instructions, wrappers, tests, citation/rights and
verification records) is authored for this SCM PR; its provenance is this PR's
Git history and package hashes, not a fabricated frozen experiment origin.
`code-equivalence.json` compares original/exported function/class ASTs. Nonidentical
network configuration is deliberately disabled, not asserted live-equivalent.

Scientific equivalence is checked at three levels: identical frozen worlds and
references; identical original acquired-event hashes and gate/evaluator outputs;
and identical publication tables/figure and original R1 summary/component output.
No model answer is repaired or replaced. All nonterminal statuses are retained.
Source-only input material remains preserved privately; export is additive.

Public privacy scanning is pattern-based plus a positive file/export allowlist;
it does not claim to erase pre-existing information from historical Git commits.
The published rights notice distinguishes authored synthetic material and derived
OSM inputs from original Padua data and restricted Street View imagery.
