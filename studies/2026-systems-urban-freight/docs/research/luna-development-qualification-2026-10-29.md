# GPT-6 Luna Responses connector: development qualification

**Status: QUALIFIED for the bounded connector criterion, 2026-10-29.** Six new live GPT-6 Luna Responses calls were made on four existing P8 development cases; no EVAL30 case was sent. Two distinct multi-step trajectories completed through the unchanged controller: P8-11 `CALL_TOOL → FINAL`, and P8-12 `ASK_USER → FINAL`. This demonstrates the specified development interaction, not model accuracy on EVAL30 or operational reliability.

The connector replays every original output item of each completed response, including commentary/final_answer phases and content, into the next scenario-local Responses input. The shared controller receives only the sole canonical final-answer action. Commentary never triggers a tool or user action. The adapter verifies that prior journal entries are processed, response hashes match and each selected action equals the controller history; mismatches stop. Full replay adds provider-generated commentary to later context and may affect comparability with other serving profiles; it is not new external scenario evidence. No persistent conversation state or previous_response_id is used (`store=false`). Reasoning `none`, temperature 0, JSON-object mode and output cap 2048 remain as documented. The historic 16 KiB guard applies to controller messages; the reservation envelope accounts for the larger serialized replay body. Dynamic arguments and local canonical validation remain unchanged. Messages lacking an unambiguous final phase fail closed. No response repair is performed.

## Observed trajectories

| Case | Real actions | Result | Independent outcome / I2 / I3 |
|---|---|---|---|
| P8-01 | FINAL | Completed, one call | false / admitted / rejected |
| P8-11 | CALL_TOOL → FINAL | Completed, two calls; tool released ROAD-01, value 1800 | true / admitted / admitted |
| P8-02 | FINAL | Completed, one call | false / admitted / rejected |
| P8-12 | ASK_USER → FINAL | Completed, two calls; user channel released VAN-1, value 75 | false / rejected / rejected |

P8-01, P8-02 and P8-12 incorrect independent outcomes are retained, not corrected; their controller completion demonstrates protocol flow only. On P8-11 the next request includes the exact original output item and exact tool response. On P8-12 the next request includes both original commentary and final_answer items in order, unchanged, followed by the exact simulated dispatcher observation. The commentary was not executed. Each case begins a fresh explicit scenario context. No user or tool observations were manually inserted.

## Evidence and budget

The journal contains six request intents, six durable dispatch intents and six completed responses. Original request/response hashes and per-call captures are in `evidence/luna-qualification/development-captures.tar.gz`; its SHA-256 is `95e07daadf9605b7509bb13a2bb2a49328a08d6d4dac16670495281393b60f08`, with a 66-file hash manifest. Export was scanned for the selected local API credential and each archive member was rehashed against the manifest. The original smoke archive is unchanged. The durable journal's separate analysis is authoritative for counts; the legacy controller's `actual_model_generation_attempts` field does not recognize this client and must not be used.

New usage totals: 11,305 input and 557 output tokens. Journal reservation is $0.06 of the new $0.50 cap; with the earlier smoke's $0.01, $0.07 is reserved against the overarching $3 cap. Conservative usage-based upper estimate for the six calls at documented standard rates is $0.001691625, not an invoice. Cache writes and cached tokens are retained per call. Minimum observed interval from completion marker to next dispatch marker was 1.223 s; rate-limit headers were not available in the earlier model lookup, so account-specific RPM/TPM remain unverified. No 429 or uncertain execution occurred.

A qualification journal is bounded to 30 new request intents and $0.50; each development case has a unique output directory and no automatic retries. The original $3 cap includes previous reservations. No scientific collection is authorized by this report. API service and serving profile may drift, and this six-call qualification is not a prediction of future model behavior.

## Final verification

Full offline regression after implementation and live development: **909 tests passed, 10 subtests passed**, with three third-party SWIG deprecation warnings. Ruff passed on the added tools; mypy passed on six OpenAI production modules. The 59-file freeze manifest and the historical EVAL30 archive matched; Git diff showed no changes to frozen evaluation files or the earlier Luna smoke evidence. No EVAL30 calls were made.
