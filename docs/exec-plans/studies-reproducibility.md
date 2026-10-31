# Study-oriented reproducibility export — implementation plan

Authorization: research author, 31 October 2026, approval in the SCM reorganization chat.
SCM baseline: 9e13c45c795e106732029279eadee52cfa43a3e9.
Private Systems source: 7bd0b106cfa71a96f7c51f6b9860bc148963b113 (read only).

1. Export allowlisted Systems inputs, code, source-qualified textual observations,
   original results and compact action/evidence replay packets, preserving provenance.
2. Qualify summary reproduction and deterministic I2/I3 replay in a clean offline
   environment. Retain scientific failures; do not regenerate model responses.
3. Add historical IDWL and maritime-extension navigation/materials with separate
   citation records and exact source pins. Preserve legacy root paths.
4. Scope governance by study; remove infrastructure details from README examples.
5. Audit hashes, transformation equivalence, licensing, privacy and prohibited files.
6. Commit and open a Draft PR against dev. No merge, tags, releases, inference,
   remote compute or changes in source repositories are authorized by this plan.

Reproduction levels: (1) published summaries; (2) recorded-proposal I2/I3 replay;
(3) new LLM collection, separately documented and not executed or guaranteed identical.

## Implemented scope

- Systems package and three reproduction levels implemented; summaries/replays
  qualified offline in an isolated second environment/process.
- Historical indexes, bounded supplementary export, citation records, scoped
  governance and prospective release map added; root maritime paths preserved.
- Privacy, provenance, static/legacy compatibility and scientific-equivalence
  checks recorded under the Systems provenance directory.
- Delivery is a Draft PR only. No merge, final release/tag, inference or other
  repository state changes are performed.
