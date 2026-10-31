# EVAL-OP-V2-R1: four-provider scientific collection

**Frozen definition:** `3da236d6dffa4707fce35f282b75dd77703831e6`, with explicit researcher approval before inference and the exact freeze receipt (`../evidence/eval-op-v2-r1/scientific-freeze.json`; original source artifact, not included here). Collection ran 30 October 2026. The published design has 16 enriched cases and six matched controls per provider; the six enriched members are not repeated. This is a new cohort, separate from the historical EVAL30, and raw accuracies across cohorts should not be treated as equivalent outcomes.

All 110 scheduled assignments were processed: 88 model and 22 D-INT assignments. There was no global STOP and no technically missing assignment or pair. Qwen and Mistral completed 22/22; DeepSeek and Luna completed 21/22 with one observed model-format failure each. DeepSeek `OPV2-08-C` produced an invalid canonical model event; Luna `OPV2-14-E` produced duplicate JSON keys in the unique final answer. Both had HTTP 200, are scored as observed model failures under the prespecified analysis and were neither repaired nor repeated. D-INT completed 22/22.

## Standalone 16 enriched assignments

| Route | Fully correct / 16 assigned | Appropriate insufficiency | Unnecessary insufficiency* | Unsupported numeric commitments / numeric terminals | Useful I2 / I3 |
|---|---:|---:|---:|---:|---:|
| Qwen | 7 | 4 | 3 | 0 / 9 | 7 / 7 |
| DeepSeek | 6 | 2 | 0 | 3 / 13 | 6 / 6 |
| Mistral | 4 | 4 | 9 | 2 / 2 | 4 / 4 |
| GPT-6 Luna | 5 | 3 | 3 | 2 / 9 | 5 / 5 |
| D-INT | 16 | 4 | 0 | 0 / 12 | 16 / 16 |

*The broader prospective refusal diagnostic counts `INSUFFICIENT` against either complete feasible or complete infeasible reference. The inherited evaluator's narrower feasible-only refusal count is also preserved in `analysis.json`. Components overlap; their denominator is completed terminal proposals, 16 for Qwen/DeepSeek/Mistral/D-INT and 15 for Luna. Appropriate insufficiency is conditional on the established available-channel semantics, not proof about real receiver permission.

In enriched cases the reference-instance physical checker flagged 3/9 submitted plans for Qwen, 4/12 for DeepSeek, 0/2 for Mistral and 3/9 for Luna; denominators are proposals with a plan and complete reference inputs. Action-transition errors were 3/9, 6/13, 0/2 and 3/9 numeric terminal proposals, respectively. These overlap with other errors. Among unsupported numeric commitments, I2 admitted 0, 1, 2 and 2, while I3 admitted 0 in each model arm; useful I2 and I3 outcomes were unchanged, and there were no correct I2-admitted proposals additionally rejected by I3 in these 16 cases. These are gate outcomes against the same original proposals, not proof of real-world harm prevention.

The broad literal-citation diagnostic can flag explanatory text in an otherwise correct `INSUFFICIENT` response. Thus 16 Mistral enriched terminal proposals with at least one nonliteral `evidence` element do **not** equal 16 incorrect source-grounding decisions; four are correctly scored insufficiencies. Likewise, a superseded source ID cited alongside the operative source need not imply a wrong decision. Numeric grounding failures, literal citation diagnostics and full-contract correctness are distinct. The detailed machine-readable component counts are in [analysis.json](../../results/r1/analysis.json).

## Six matched pairs

The primary finite-cohort contrast is mean enriched-minus-control correctness per provider, with the pair as unit. All six pairs have both observed outcomes, so the prespecified missing-data bounds collapse to the observed difference. A `0→0` pair means both variants failed, not that both were correct.

| Pair | Qwen C→E | DeepSeek C→E | Mistral C→E | Luna C→E | D-INT C→E |
|---|---|---|---|---|---|
| OPV2-01 | 1→0 | 1→1 | 0→0 | 0→0 | 1→1 |
| OPV2-02 | 1→1 | 0→0 | 0→0 | 0→0 | 1→1 |
| OPV2-03 | 1→1 | 1→1 | 1→1 | 1→1 | 1→1 |
| OPV2-04 | 1→0 | 1→1 | 0→0 | 0→0 | 1→1 |
| OPV2-08 | 1→1 | 0→0 | 1→1 | 1→1 | 1→1 |
| OPV2-13 | 0→0 | 0→0 | 0→0 | 0→0 | 1→1 |
| **Mean E − C** | **−2/6** | **0/6** | **0/6** | **0/6** | **0/6** |

For Qwen, OPV2-01 enriched returned UPDATE when unchanged parameters and route required RETAIN; OPV2-04 enriched returned INSUFFICIENT although the required tool source was available. The original control outcomes were correct. These observations support the possibility that the added context or associated presentation affected correctness in this particular six-pair design; they do **not** show which visual fact caused the differences, or establish a general or population-level effect. The other three model contrasts are zero in this sample, frequently because both variants were incorrect; this is not evidence of equivalent general robustness. Common instructions already warn against treating visual clues as authority, the enriched prompts are longer, cases and POIs are shared, serving profiles differ and only one trajectory per variant was sampled. The experiment does not validate actual freight access, business identity, receiver permission or legal loading.

## Capture, reproducibility and accounting

The scientific journal recorded 150 model dispatch intents and responses, all HTTP 200 and with usage; Qwen 31, DeepSeek 35, Mistral 61 and Luna 23. D-INT has 44 synthetic journal calls and zero model requests. No scientific request was retried or replaced. Independent readback recomputed 108 terminal traces and evaluations, verified both gate proposal hashes, and checked 388 individual request/response hashes including D-INT; no discrepancies were found. The two model-format failures have original capture evidence but no terminal replay. The archive was extracted independently and all 1,993 file hashes matched capture-manifest.json (`../evidence/eval-op-v2-r1/capture-manifest.json`; original source artifact, not included here); the approved analysis and replay report were reproduced byte-for-byte. The raw [captures archive](../../examples/r1.json) SHA-256 is `c5d2e877c04e18ff23f99f0f1478c8f7274c6462128a6bc4d0992fdc31951479`. The 1,993 files were scanned against the four selected credential values; no matches were found. This is a scoped credential scan, not a general privacy guarantee.

| Route | Requests | Input tokens | Output tokens | Reserved USD | Usage-based estimate / upper USD |
|---|---:|---:|---:|---:|---:|
| Qwen local | 31 | 82,962 | 3,015 | 0.00 | 0 external-provider charge |
| DeepSeek | 35 | 94,975 | 2,652 | 0.35 | ≤ 0.0316749 |
| Mistral | 61 | 182,372 | 6,281 | 0.61 | ≤ 0.0311244 |
| GPT-6 Luna | 23 | 56,233 | 1,905 | 0.23 | ≈ 0.00520465 |
| **Total paid** | **119** | | | **1.19** | **≤ approximately 0.068004** |

Estimates use published standard tariffs checked before execution: DeepSeek peak rates with all inputs priced as cache misses, Mistral standard rates without cache discounts, and OpenAI standard rates accounting for reported cached and cache-write tokens. They exclude taxes, account-specific prices and other charges and are not an invoice. Actual billed consumption is not available from the retained usage records. OpenAI reported 23,590 cached input tokens and 30,078 cache-write tokens; DeepSeek reported 61,184 cache-hit and 33,791 cache-miss input tokens. The $1.19 figure is conservative durable **reservation**, not billed spend. The [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/), [Mistral](https://docs.mistral.ai/inference/pricing), and [OpenAI](https://developers.openai.com/api/docs/models/gpt-6-luna) rates and account terms may change.

The first-to-last request window was approximately 1,459 seconds. Measured minimum completion-to-next-dispatch gaps were 15.206 s for Mistral and 1.205 s for OpenAI using client-side timestamps and filesystem metadata; these are not server timing guarantees. All four expected model IDs were found by authenticated non-inference model catalog GET requests before collection. Account-specific RPM/TPM limits were not returned by the catalogs and remained unverified. All scientific responses reported the expected model ID; no observed identity/fingerprint drift was flagged. Provider serving profiles, history replay and wire formats differ, so the counts cannot isolate model capability from profile effects. No new four-provider rerun, prompt tuning, scenario replacement or historical rescoring occurred.

## Offline readback

Extract `captures.tar.gz` into a fresh directory, verify file bytes against `capture-manifest.json` with paths relative to the extracted `collection/`, and check the approved source manifest. With `PYTHONPATH=.:implementation/padua_evidence_v1`, run `python -m tools.eval_op_v2.analyze_r1 <extracted>/collection/results.json <new-analysis.json>` and `python evidence/eval-op-v2-r1/replay_audit.py <extracted>/collection <new-replay.json>`. No inference is required. AI-assisted independent methodology, provenance and engineering checks and their mutual criticism are recorded in review.md (`../evidence/eval-op-v2-r1/review.md`; original source artifact, not included here); these are not independent human expert validation.
