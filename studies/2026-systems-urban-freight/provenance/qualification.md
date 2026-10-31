# Offline qualification — 1 November 2026

Package revision: 0.1.0-review. Source manuscript/research commit:
`7bd0b106cfa71a96f7c51f6b9860bc148963b113` (read-only during export).
SCM base: `9e13c45c795e106732029279eadee52cfa43a3e9`.
This qualifies the exported research package, not journal acceptance, real
freight access, a new model profile or a new scientific experiment.

## Results

- EVAL30: 120 retained assignments, 119 exact terminal/evaluator replays;
  Mistral EVAL-29 retains its original prompt-budget status.
- Separate Luna extension: 30/30 terminal/evaluator replays; 48 recorded requests.
- R1: 110 assignment records; 108 exact terminal/evaluator replays; two observed
  model-format failures preserved. All provider summaries, component counts,
  paired differences and missingness bounds equal the original analyzer output.
  Durable journal readback totals agree with the retained 150-request accounting;
  legacy controller attempt fields are not used to infer OpenAI requests.
- Total 257 terminal records across separate collections. No pooled performance
  statistic is computed. 87 scripted diagnostics are replayed and reported
  separately, including the known acquired-evidence counterexample admitted by I3.
- Original EVAL30 and 16-case precursor generators reconstruct their input worlds;
  the R1 constructor reconstructs all 22 assignments exactly. All reference records
  agree, all six pairs differ only in permitted visual context, and canonical R1
  assignment/schedule hashes match the original scientific freeze receipt.
- Both generated result-table bodies and matched-outcome PDF are byte-identical
  to the manuscript artifacts. Figure code changes only resource paths and hashes.
- 41 inventory/second-pass records match on file SHA, panorama date and POI UUID;
  12 POI classifications reproduce 6 conditional / 4 constrained / 2 insufficient.
  The original POI/scenario map regenerates exactly from public textual inputs.
- Original final-text examples (45 across the three collections) remain hash-bound;
  selection covers provider/action/correctness strata, including both R1 format
  failures. Examples are not the statistical denominator.

## Independent process / environment

The package is copied without caches, private source links or original archives
into a separate temporary directory. A second Python 3.13 environment is installed
from the pinned requirements using local package cache only. Reproduction runs
with `python -I`, an empty inherited environment, disabled network connections/
DNS and an audit hook rejecting reads under user directories. Private user-path
read attempts: zero. The scientific checks need only the public package and its
installed dependencies. This is automated verification, not independent human
expert review or independently established field ground truth.

The independent verifier consumes the exported manifest as supplied: it does
not regenerate or bypass the manifest to make validation pass.

## Tests and static checks

- Study: 11 tests and seven subtests, including proposal/evidence/witness tampering,
  prompt construction, final-text hashes, original Responses envelope tests and
  network denial. Three OR-Tools/SWIG deprecation warnings are non-failing.
- Historical root: 65 passed, one skipped; mypy succeeds on 83 source files.
- New replay wrapper: mypy succeeds. Original root Ruff 0.15.9 succeeds; pinned
  study Ruff 0.17.2 succeeds from the study directory under explicit E4/E7/E9/F
  rules and scoped original-source formatting exceptions. Historical excerpts are
  labeled `.py.txt` because they are inspection fragments, not runnable modules.
- Code-equivalence audit: frozen top-level functions/classes unchanged except
  the deliberately disabled HTTP worker and its sanitized endpoint allowlist.
  Configuration/global data-root relocations are recorded separately.
- Historical extension: 18 byte-identical exported source files; 60 terminals and
  15,400 retained DES rows verified without new statistical resampling or DES.
- Export hash inventory, citation syntax, prohibited-file checks, private host/path
  and common credential-pattern scans pass. No images, full technical traces,
  capture archives, private manuscripts or credentials are in the new study export.

## Limits and preservation

A replay checks the same recorded proposal against the same acquired information;
route-tool witnesses are checked rather than searched again. It does not audit
omitted original provider-wire bytes, establish external truth, or promise identical
future generations. Geographical prototype summaries are provenance, not evaluated
travel-time forecasts. Visual observations remain historical and non-authoritative.

Legacy root code/data/tests and historical refs remain intact. Private source and
frozen artifacts are not rewritten. Existing public history is not purged by this
PR. IDWL's pre-workshop source anchor is not asserted to identify the exact executed
runtime solely from its date. The maritime extension retains its original partial
reproduction limits. Final releases/tags and merge remain author-controlled.
