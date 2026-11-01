# Historical package qualification — 1 November 2026

Source: existing SCM supplement plus read-only local WSC source and accepted-run
checkpoint; full hashes/transformations in historical-additions.json. Existing
18 supplementary source exports and all original outcome/analysis files unchanged.

- The preserved analysis.py, with its original seeds and definitions, reproduces
  the original analysis JSON exactly from 60 terminal rows (59 analyzable clusters).
  No model outputs are rescored, and no inference, DES or new cases are generated.
- Condition counts agree with the accepted summary: 8 llm_only, 17 gate_only,
  18 structured_repair accepted; one unavailable scientific outcome per condition.
- All 15,400 saved DES rows are unique, form 11 paired incidents and seven variants,
  and have 100 replications per condition/variant. Existing invariants are checked,
  not re-simulated.
- All 35 checkpoint DES projections correspond to original terminal rows. Reversing
  only the documented metadata projection recovers 27 distinct canonical response
  objects with matching terminal artifact hashes. Original response whitespace/API
  envelopes and failed response content are not invented. This retained material
  is success-conditioned and does not represent all 344 operations.
- Original initial/repair templates and source design match their launch versions.
  All 180 original design-unit payload hashes verify. Their membership in the
  executed scientific population is not certified: its unit_set_sha256 binding
  remains unreconciled. The exported data are labeled Phase-A design inputs.
- Forwarder navigation retains STOP/missingness/development limitations and uses
  allowlisted extracts. No operational report, infrastructure identifier, trace ID,
  live launcher or private review/paper is exported wholesale.
- Tests: 70 passed, one skipped (legacy plus new packaging/historical tests).
  Ruff passes. Mypy passes on the new wrappers and existing 83 source files.
- Independent reconstruction from committed public files/release archives is
  performed offline with network disabled. This is an automated check, not
  independent human/domain validation or a new scientific observation.

IDWL preservation is sufficient as accepted by the author. No additional
paper-section crosswalk, experiment mapping or rerun is required.
The entire Systems study directory is byte-identical to merged PR #4.
Final release publication, tags and merge remain separately author-controlled.
