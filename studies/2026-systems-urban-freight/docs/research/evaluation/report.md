# 30-case source-first evaluation: live scientific results

One fresh interactive trajectory was assigned to each of30 frozen scenarios for Qwen, official DeepSeek and fixed Mistral Small4; D-INT used the same public sources/channels/tools. This is an evaluation of incremental terminal evidence admission, not a model leaderboard. The researcher reviewed the original28 cases and approved the final amendments plus two additional source-first cases before inference. [Frozen study/rubric](study.md), [configuration](../../../data/research/evaluation/collection-config.json), [references](../../../data/research/evaluation/references.json), [full analysis](../../../results/eval30/analysis.json), episode table (`../../evidence/evaluation-30/live/episodes.csv`; original source artifact, not included here), request table (`../../evidence/evaluation-30/live/calls.csv`; original source artifact, not included here).

## Freeze, execution and preserved history

Final scientific/runtime source commit `eb411c73544e39fc0813c4c79214a7738210acf2`; pre-inference manifest commit `375560c`. Scenario SHA256 `43e20fa3e6efd60d47902c7ab24f94b3338cb988be7441db25eee0810d18f01e`. Reference SHA256 `abb0413400a1a724fe02a5dedd6bb4033d2313ceaaaae99224890496312bc27f`. Full59-file hashes are in the pre-inference freeze (`../../evidence/evaluation-30/pre-inference-freeze.json`; original source artifact, not included here). No frozen world, reference, rubric, prompt, serving profile, reader or gate was changed after the first model request. The authoring review_status denotes authorization of the final design/amendments; the exact new29/30 operational facts and conversions were authored and deterministically checked by the research assistant under that authorization, not separately annotated by an external human domain expert.

PR22 continues on `codex/padua-independent-evaluation`, based on native Stack21 merge `b4a2153`. P7–P9/Mistral development outputs and the previous28-case offline findings remain unchanged at their original commits/artifacts. The pre-amendment28 scenarios/references are additionally retained in `evidence/evaluation-30`. Current core extensions are versioned new code, not a claim that old source hashes match the extended core. Canonical SCM and original pilot ledgers were not modified.

Original generation captures span `2026-10-28T21:31:03.859902+00:00` through `2026-10-28T22:05:49.916613+00:00` (UTC). Actual collection elapsed 34.77minutes; shared deadline8hours. Maximum210 generation attempts per provider/630 total; DeepSeek ceilingUSD3, Mistral ceilingUSD2.50, local Qwen provider chargeUSD0. At most3 atomic questions,3 tools,7 responses per episode; no automatic retries or replacement trajectories. Mistral15second pacing is measured separately from API latency. Route isolation: `{}`. Every assigned outcome, including failure/incomplete/unattempted status, remains in the denominator.

## Reference outcomes and actual decisions

15 normalized cases (01–14,30) and15 message cases (15–29) are separate strata; their different task content prevents a causal prose-versus-normalized contrast.21 references are feasible-plan,4 infeasible and5 insufficient-evidence. Any supported feasible route is valid; a fixed optimum is not required. The following cells show action and independent full-contract correctness, not admission alone.

|Case|Reference|Qwen|DeepSeek|Mistral|D-INT|
|---|---|---|---|---|---|
|EVAL-01|FEASIBLE_PLAN|UPDATE ✓|UPDATE ✓|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-02|FEASIBLE_PLAN|UPDATE incorrect|UPDATE incorrect|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-03|FEASIBLE_PLAN|INSUFFICIENT incorrect|UPDATE incorrect|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-04|FEASIBLE_PLAN|INSUFFICIENT incorrect|UPDATE ✓|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-05|FEASIBLE_PLAN|UPDATE ✓|UPDATE ✓|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-06|FEASIBLE_PLAN|UPDATE ✓|UPDATE ✓|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-07|INSUFFICIENT|INSUFFICIENT incorrect|INSUFFICIENT ✓|INSUFFICIENT incorrect|INSUFFICIENT ✓|
|EVAL-08|INFEASIBLE|UPDATE incorrect|UPDATE incorrect|UPDATE incorrect|INFEASIBLE ✓|
|EVAL-09|INFEASIBLE|UPDATE incorrect|UPDATE incorrect|INFEASIBLE incorrect|INFEASIBLE ✓|
|EVAL-10|FEASIBLE_PLAN|UPDATE incorrect|UPDATE incorrect|UPDATE incorrect|UPDATE ✓|
|EVAL-11|FEASIBLE_PLAN|UPDATE ✓|UPDATE incorrect|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-12|FEASIBLE_PLAN|UPDATE ✓|UPDATE incorrect|UPDATE incorrect|UPDATE ✓|
|EVAL-13|INSUFFICIENT|INSUFFICIENT ✓|CLARIFY incorrect|INSUFFICIENT ✓|INSUFFICIENT ✓|
|EVAL-14|FEASIBLE_PLAN|RETAIN ✓|RETAIN ✓|RETAIN incorrect|RETAIN ✓|
|EVAL-15|FEASIBLE_PLAN|UPDATE incorrect|UPDATE incorrect|UPDATE incorrect|UPDATE ✓|
|EVAL-16|FEASIBLE_PLAN|INSUFFICIENT incorrect|UPDATE incorrect|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-17|INSUFFICIENT|INSUFFICIENT ✓|UPDATE incorrect|INSUFFICIENT incorrect|INSUFFICIENT ✓|
|EVAL-18|FEASIBLE_PLAN|INSUFFICIENT incorrect|UPDATE ✓|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-19|FEASIBLE_PLAN|UPDATE incorrect|UPDATE incorrect|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-20|INSUFFICIENT|INSUFFICIENT ✓|INSUFFICIENT ✓|INSUFFICIENT ✓|INSUFFICIENT ✓|
|EVAL-21|FEASIBLE_PLAN|UPDATE ✓|INSUFFICIENT incorrect|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-22|FEASIBLE_PLAN|INSUFFICIENT incorrect|INSUFFICIENT incorrect|UPDATE incorrect|UPDATE ✓|
|EVAL-23|FEASIBLE_PLAN|INSUFFICIENT incorrect|UPDATE incorrect|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-24|INSUFFICIENT|INSUFFICIENT incorrect|INSUFFICIENT incorrect|INSUFFICIENT incorrect|INSUFFICIENT ✓|
|EVAL-25|INFEASIBLE|UPDATE incorrect|UPDATE incorrect|INSUFFICIENT incorrect|INFEASIBLE ✓|
|EVAL-26|INFEASIBLE|UPDATE incorrect|UPDATE incorrect|INSUFFICIENT incorrect|INFEASIBLE ✓|
|EVAL-27|FEASIBLE_PLAN|UPDATE ✓|UPDATE ✓|INSUFFICIENT incorrect|UPDATE ✓|
|EVAL-28|FEASIBLE_PLAN|RETAIN ✓|RETAIN ✓|RETAIN incorrect|UPDATE ✓|
|EVAL-29|FEASIBLE_PLAN|UPDATE incorrect|UPDATE incorrect|prompt_budget_exceeded incorrect|UPDATE ✓|
|EVAL-30|FEASIBLE_PLAN|RETAIN incorrect|RETAIN incorrect|INSUFFICIENT incorrect|UPDATE ✓|

## Independent correctness, admission and interaction cost

|Measure|Qwen|DeepSeek|Mistral|D-INT|
|---|---:|---:|---:|---:|
|Assigned trajectories|30|30|30|30|
|Completed schema-valid FINAL|30|30|29|30|
|Correct feasible plans /21|9|8|0|21|
|Correct INFEASIBLE /4|0|0|0|4|
|Correct INSUFFICIENT /5|3|2|2|5|
|All independently correct /30|12|10|2|30|
|Admitted I2|12|13|7|30|
|Admitted I3|12|10|2|30|
|Useful I2|12|10|2|30|
|Useful I3|12|10|2|30|
|Contract-unsupported commitments admitted I2|0|3|5|0|
|Contract-unsupported commitments admitted I3|0|0|0|0|
|Additional I3 rejections of unsupported commitments|0|3|5|0|
|Fully correct decisions additionally rejected by I3|0|0|0|0|
|Correct values/action and true-feasible plan|9|8|4|21|
|Required values and true-feasible plan, post-hoc key diagnostic|10|9|4|21|
|Reference decision class matched, diagnostic only|20|22|12|30|
|Unnecessary INSUFFICIENT on feasible reference|6|2|14|0|
|Charged atomic questions|4|0|54|6|
|Tool attempts|10|20|15|30|
|Invalid tool arguments|1|4|0|0|
|Actual generation attempts|43|50|92|0|

Correct feasible planning, proved infeasibility and justified refusal are separate outcomes. A high refusal count is not completed logistics. Pure filtering cannot improve the original proposal; identical I2/I3 replay identifies terminal admission protection/cost, not the effect of interactive repair. Common action/referral/mathematical checks already constrain I2. An unnecessary refusal after self-induced question-budget exhaustion remains independently incorrect even if admitted.

### Paired changes on identical original transcripts/proposals

|Provider / case|I2 → I3|Full-contract correct|Correct values/action and true-feasible plan|Common errors / observable source errors|
|---|---|---|---|---|
|mistral / EVAL-09|True → False|False|False|[] / {'unknown_or_nonliteral_source_id': 5}|
|deepseek / EVAL-11|True → False|False|False|[] / {}|
|mistral / EVAL-12|True → False|False|True|[] / {'unknown_or_nonliteral_source_id': 2}|
|deepseek / EVAL-12|True → False|False|False|[] / {'approximate': 1}|
|mistral / EVAL-14|True → False|False|True|[] / {'unknown_or_nonliteral_source_id': 3}|
|deepseek / EVAL-17|True → False|False|False|[] / {'authority': 1}|
|mistral / EVAL-22|True → False|False|True|[] / {'unknown_or_nonliteral_source_id': 2}|
|mistral / EVAL-28|True → False|False|True|[] / {'unknown_or_nonliteral_source_id': 4}|

DeepSeek’s three incremental rejections are substantive evidence-policy protections: EVAL11 used travel165seconds despite citing an archive entry specifying2400; EVAL12 committed an approximate900second service estimate instead of obtaining the confirmed720second allowance; EVAL17 treated an unverified driver relay as receiver permission. Mistral’s five incremental rejections (09/12/14/22/28) all concern nonliteral/unknown source-ID strings: four had correct values/action and feasible routes, and09 had the correct source-first infeasibility parameters/proof. Do not call these five prevented factually wrong plans. DeepSeek11’s wrong arc time concerns an arc not used by its returned route, and12’s longer estimate can be conservative for route feasibility. Those two blocks establish exact-state evidence consistency, not necessarily prevention of an infeasible tour;17 concerns genuinely missing receiving authority under the declared appointment premise. The imposed full-parameter closure can be stricter than plan-specific sufficient evidence. No real-world harm prevention is measured. Fully contract-correct false rejections are zero, while provenance-link enforcement still has an operational acceptance cost. Useful counts stay12/12,10/10,2/2 for I2/I3 respectively.

“Unsupported” in the primary table is the declared full source/evidence contract: it combines incorrect parameters/authority/applicability with inadequate provenance linkage. It is not automatically a false physical fact. The adjacent component column exposes numerically correct, feasible plans; rejections caused only by citation granularity/identity must not be advertised as prevention of factually wrong deliveries. The acquired-record grounding flag alone is not independent global truth.

## Presentation strata

|Provider|Normalized correct /15|Message correct /15|Normalized useful I2/I3|Message useful I2/I3|
|---|---:|---:|---|---|
|qwen|7|5|7/7|5/5|
|deepseek|6|4|6/6|4/4|
|mistral|1|1|1/1|1/1|
|deterministic|15|15|15/15|15/15|

## Error components

Post-hoc component diagnostics (including mandatory-value matches that ignore extra keys and decision-class matches) do not change primary labels or admit repaired answers. The common runtime requires all and only required parameter keys, while the generic schema permits additional scalar keys and the public prompt says provide all required parameters. Extra-key exclusivity is insufficiently explicit and can penalize plausible overcomplete outputs; this is a limitation of the frozen interface, not proof that the model misunderstood every value. The extra-key flag is separated from incorrect mandatory numeric values.

Counts below are observable episode flags and may overlap. They do not reveal the models’ private reasoning. Unit/volume/clearance checks concern EVAL29; qualification-policy checks concern EVAL30, so their denominators are one assigned case per model, not30 interchangeable opportunities. Citation/authority/temporal flags concern actually cited records, not every hypothetical failure. Unknown/nonliteral IDs prevent reliable record-level authority/time attribution; zero authority/temporal flags for such outputs are unassessed, not evidence of correct interpretation.

|Error flag|Qwen|DeepSeek|Mistral|D-INT|
|---|---:|---:|---:|---:|
|numeric_parameter|1|5|0|0|
|parameter_key_contract|0|0|2|0|
|action_semantics|1|2|0|0|
|route_feasibility_on_true_instance|9|12|3|0|
|authority|3|3|0|0|
|temporal_or_supersession|2|2|0|0|
|scope_or_entity|0|0|0|0|
|citation_identity|1|1|29|0|
|unit_or_rounding|1|1|0|0|
|volume|1|0|0|0|
|clearance|1|1|0|0|
|temperature_qualification_policy|0|0|0|0|

EVAL08 has loads70/60/25/35kg and residual allowances100/90kg: total190 equals190, but no indivisible partition fits. The solver supplies a bounded exhaustive mass-assignment certificate; both independent enumeration paths find no feasible plan. EVAL09 has service duration below its deadline; only minimum travel plus service exceeds the receiving bound. Zero-travel metamorphism becomes feasible.

EVAL29 original UK documentation states170lb,40ft³ and48×40×36in, rigid upright handling. Exact definitions and final upward rounding yield78kg,1133L and1220×1016×915mm. The reference sends the crate alone on vehicle1 (1100mm aperture), and the other three consignments on vehicle0 (1750L≤1800L). A mass-feasible assignment can violate volume or loading clearance. These are actual solver/checker/oracle constraints, not prose-only instructions or general3D packing. Five field records relay the same packing certificate; literal per-field citation coverage can be stricter than ordinary document-level evidence use. Keep physical correctness and provenance-contract compliance separate.

On EVAL29, both Qwen and DeepSeek inferred the imperial-to-metric quantities but rounded mass/length/height downward (77kg,1219mm,914mm instead of78kg,1220mm,915mm); both correctly returned1133litres. Both placed the crate on the1000mm-width vehicle and violated mass; Qwen also violated aggregate volume. These failures were already rejected by I2’s common physical checks, so they do not identify added I3 benefit. Mistral never produced a terminal proposal: after3generations the reconstructed next message history was16490UTF-8bytes,106bytes above the fixed16384byte guard. No fourth POST occurred. This is a local serialization/protocol limit, not a provider context failure or demonstrated inability to convert units. Zero terminal error flags for that incomplete trajectory are unassessed, not a successful unit/volume test.

EVAL30 uses carrier qualification and an applicable batch-specific quality policy: medicines require+2…+8°C and medicine-qualified vehicle0; foods require0…+4°C and cannot share this run with those medicine batches because mixed transport has not been validated. Both vehicles being refrigerated does not make them interchangeable. The run-specific allowed_vehicles implication is checked by solver, independent checker and exact oracle. It is not a universal statutory ban. [GDP2013/C343/01 Chapter9, official full text](https://health.ec.europa.eu/system/files/2016-11/2013_c343_01_en_0.pdf) supports suitable equipment/required transport conditions and risk procedures. [852/2004 AnnexII ChapterIV, official record](https://eur-lex.europa.eu/legal-content/en/ALL/?uri=celex:32004R0852) addresses contamination, separation where necessary and suitable temperature control. Original EU-page access was bot-blocked; official search extracts and the government mirror supported the stated section-level interpretation. No operational legal-compliance validation is claimed.

Qwen and DeepSeek both produced the correct qualified medicine/food vehicle allocation on EVAL30, but labeled the changed routes RETAIN; the shared action rule rejected both. Mistral unnecessarily chose INSUFFICIENT. Thus no model produced a full-contract success on30, but the Qwen/DeepSeek outcomes are not temperature-qualification allocation failures. One example cannot establish general competence or failure.

## Identity, tokens, latency and expenditure

|Provider|Returned identity cohorts|Attempts|Input / output tokens|API transport seconds|Pacing seconds|Committed USD|Peak tariff estimate USD|Timestamp tariff estimate USD|
|---|---|---:|---|---:|---:|---:|---:|---:|
|qwen|[['qwen3.8-27b-ud-q4_k_m', 'b11815-7170cad4d', 'df702a1c6f47e096']]|43|105354 / 4409|836.814|0.000|0.00|0.00000000|0.00000000|
|deepseek|[['deepseek-flash', 'bc19ba97cbe016479903222bb1578db6', 'd5b5434383c0232b']]|50|123214 / 3406|61.347|0.000|0.50|0.04105140|0.00938663|
|mistral|[['mistral-small-2603', None, 'd39190e49672b994']]|92|257189 / 10142|119.179|1061.809|0.92|0.04466355|0.04466355|

Original response IDs, fingerprints where supplied, usage and timestamps are retained per request. Cohorts are observed metadata, not proof of immutable weights. DeepSeek alias drift is recorded without automatic stopping; distinct observed cohorts are not silently pooled. Qwen and Mistral use the fixed qualified requested IDs. Mistral native schema omits only the two wire uniqueItems; canonical local validation remains full. Qwen/DeepSeek retain their qualified JSON profiles, with thinking disabled. No provider-native tools/search or another model was exposed.

All185 actual POST intents and captures are accounted for (Qwen43,DeepSeek50,Mistral92), all journals are processed with STOP=NULL, and no route was isolated. There are 89 schema-valid FINAL episodes and one incomplete Mistral29; zero assigned trajectories are unattempted. Measured minimum Mistral POST-intent gap after prior capture completion is15.200seconds.

Conservative committed reservations protect spending ceilings and are not charges. Usage-based estimates are not invoice verification. DeepSeek timestamp estimate uses published peak/off-peak rates and reported cache counters; Mistral estimate assumes ordinary input/output rates. Unknown usage remains unknown; reservations cover incomplete attempts. Pricing sources were rechecked before collection. Client API elapsed includes transport/TLS/process overhead, not isolated server compute; Mistral pacing is separately measured. Qwen tokenizer counts are not hosted-model token counts.

## Limitations and reproducibility

This purpose-built source-first cohort is new relative to P8, but its authors knew development failure modes. Baseline engineering used candidate cases before inference; there is one trajectory per case/configuration. Cases share sites and mechanisms. The normalized/message strata contain different tasks and serving profiles differ across providers. No population-level power, general causal model ranking, calibrated delivery benefit, labor saving or architectural superiority follows. Synthetic source authentication/authority, payloads, windows, qualifications, messages and carrier policy are premises; archived geometry anchors location, while20km/h travel times and depot are assumptions. Evidence-decision validity is distinct from simulator-conditioned route performance.

The separate87 controlled proposals contain51 supported controls,21 unnecessary refusals and15 unsupported numeric controls. Fourteen unsupported controls are additionally rejected by I3; the pre-lookup EVAL19 obsolete-payload proposal remains falsely admitted. This inherited acquired-evidence gate does not establish completeness against accessible but unconsulted replacements. The limitation was deliberately not repaired. The controlled diagnostic is separate from natural model trajectories and cannot estimate natural error prevalence. The bounded text reader is not general NLP; the spelled-out-number coverage counterexample remains.

Independent score readback reproduced saved results. Replay differences: `[]`. I2/I3 original-proposal hashes are identical for every available terminal decision. D-INT uses explicitly synthetic protocol envelopes and zero model generations; their nominal route/model fields are compatibility fixtures, not Qwen observations. Raw immutable requests/responses, traces, capture metadata and SQLite journals are preserved in the credential-scanned [archive](../../../examples/eval30.json) with its file manifest. No raw answer or failed trajectory was repaired/replaced. Byte-verified export contains2421 original files;185POST intents are distinct from the65 synthetic baseline protocol responses. The source-preservation readback confirms1810 earlier tracked evidence/research files unchanged. Original28-case and earlier pilot artifacts are retained.

Offline qualification:886 tests and3 subtests passed, Ruff/mypy passed before inference; an additional independent analysis-denominator test passed. Compatible offline token counts on65 deterministic requests max3700prompt tokens; per-request token guards remained active for live histories. Initial failed offline test was a stratum-index assumption after adding normalized EVAL30, corrected to inspect the explicit presentation field; its log is preserved. No scientific validator was weakened.

```sh
PYTHONPATH=.:implementation/padua_evidence_v1 python -m tools.evaluation_cohort.qualify --output /tmp/new-final30-offline
PYTHONPATH=.:implementation/padua_evidence_v1 python -m tools.evaluation_cohort.analyze --input /path/to/extracted/captures --output /tmp/new-final30-analysis
```

These reproduction commands are offline. Do not rerun the closed live collector to improve outcomes. The exact extended code and pre-inference manifest are versioned; all initial28 preparation observations remain available at74c1e03.

**Recommendation:** use the complete preserved observations to write the Methods/Results/Discussion as a constrained evidence-admission reliability study, retaining the strong D-INT comparison, physical/provenance distinction, negative outcomes and known source-discovery limitation. Do not tune on this now-exposed evaluation cohort or launch another automatic rerun. Any subsequent external operational cohort would require genuinely new cases/annotation and a separate scientific purpose, rather than more repetitions to manufacture a positive gate effect.
