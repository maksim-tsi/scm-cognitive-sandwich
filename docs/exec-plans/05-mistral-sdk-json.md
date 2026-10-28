# Mistral SDK v2 JSON compatibility diagnostic

Scope: use the official Python SDK v2, without Playground, to distinguish JSON mode from native JSON Schema support. This is independent development diagnostics, not an SCM maritime run or a Padua evaluation cohort. No YAAM, sandbox, graph, solver or historical evaluation changes.

1. Read official model/SDK/structured-output documentation and current SCM rules.
2. Create isolated worktree from dev and optional SDK dependency group; use its `.venv`.
3. Read model metadata, then submit sequential synthetic fixtures with retries disabled and at least15s after previous completion. Preserve exact HTTP bodies, raw content, usage, identity and canonical validation. Stop on unknown completion, identity drift, budget or provider service failure.
4. Load P8 schema declarations from the existing publication source, never re-author them. Diagnose one schema change per attempt. Preserve full local canonical validation even if a provider wire representation is broader/narrower.
5. Run repository lint, mypy and pytest; report evidence and minimal next step. No scientific batch or historical rescore. Commit on the experiment branch, no merge.

Budget: historical reservations USD0.34. Reserve USD0.05 per development POST, maximum12 POSTs, within the combined USD2 ceiling. A full262144-token context at USD0.15/M plus2048 output tokens at USD0.60/M bounds the tariff estimate by USD0.0405504 per call; USD0.05 is a reservation, not billing. Model metadata must continue to identify the Small2603 profile. API GET metadata is separate from generation counts.

Documentation: https://docs.mistral.ai/models/mistral-small-4-0-26-03 ; https://docs.mistral.ai/resources/sdks ; https://docs.mistral.ai/resources/migration-guides ; https://docs.mistral.ai/studio/conversations/structured-output/custom ; https://docs.mistral.ai/studio/conversations/structured-output/json_mode .

Completed:11 POSTs,7 successful completions,4 retained3051 rejections. Tiny uniqueItems contrast isolates the incompatibility; the full schema minus only its two uniqueItems keywords succeeds on four canonical-valid synthetic branch fixtures. This wire schema is broader; canonical validation remains mandatory. SDK2.10.1 direct complete preserves the schema, whereas its parse helper rewrites object dictionaries. No more live calls planned. Final checks: Ruff PASS, mypy83files PASS, pytest72passed/1existing skip. Report/captures/accounting: `docs/reports/mistral-sdk-json/`.
