# Mistral Small native JSON Schema compatibility through Python SDK v2

28 October 2026. Independent synthetic development diagnostics; no scientific cohort, benchmark rerun, maritime world or evaluation-score change. SCM base: dev `3ad9b6d`; feature branch `codex/mistral-sdk-json`. Browser/Playground was not used in this experiment.

## Practical result

**Mistral Small supports native JSON Schema through the official SDK. The failing P8 schema contains `uniqueItems: true`, which this serving profile rejects with HTTP400/code3051.** Remove only the two uniqueness keywords from the provider wire schema; preserve the original canonical schema for validation of every unmodified response. All four independent P8-shaped branch fixtures passed that original validator. This wire schema is **broader**, not fully equivalent: it allows duplicate evidence/missing-slot entries. Do not weaken the canonical scientific contract, normalize duplicates or repair responses.

`oneOf` is supported in the independent discriminated-action example. Neither a redundant root `type: object` nor replacing the full schema's `oneOf` with `anyOf` resolves the original400. The isolated tiny-array pair differs only by `uniqueItems: true`: with it HTTP400, without it HTTP200. This establishes a serving-schema compatibility issue beyond the earlier Playground observations; it does not diagnose the browser editor's failure.

## Documentation and model identity

|Model|Official evidence|This experiment|
|---|---|---|
|Mistral Small4 / `mistral-small-2603`|[Model card](https://docs.mistral.ai/models/mistral-small-4-0-26-03) lists Structured Outputs on Chat Completions and Conversations|Tested through `mistral-small-latest`|
|Ministral3 8B / `ministral-8b-2512`|[Model card](https://docs.mistral.ai/models/ministral-3-8b-25-12) lists Structured Outputs; [custom-output guide](https://docs.mistral.ai/studio/conversations/structured-output/custom) uses `ministral-8b-latest`|No inference; P8 compatibility unknown|
|Mistral Large3 / `mistral-large-2512`|[Model card](https://docs.mistral.ai/models/mistral-large-3-25-12) lists Structured Outputs|No inference; P8 compatibility unknown|

[JSON mode](https://docs.mistral.ai/studio/conversations/structured-output/json_mode) (`json_object`) guarantees JSON formatting, not this action schema. [Custom structured output](https://docs.mistral.ai/studio/conversations/structured-output/custom) uses `json_schema`. No hidden JSON-mode fallback was used in the11 live POSTs.

The vendor [recommends official SDKs](https://docs.mistral.ai/resources/sdks). Its [v2 migration guide](https://docs.mistral.ai/resources/migration-guides) specifies `mistralai>=2` and `from mistralai.client import Mistral`. Optional dependency group `mistral-experiment` resolves to **mistralai2.10.1** in the committed lockfile, a v2 release rather than exactly2.0.0. The production graph's LLM configuration is unchanged.

The authenticated SDK `models.list()` GET returned `mistral-small-latest` with name and billing_model_name `mistral-small-2603`, context262144, and matching aliases ([normalized metadata](models.json)). All seven successful envelopes returned model `mistral-small-latest`; returned identity is therefore the alias, not a fixed-weight hash. Metadata establishes its current mapping, not immutable future weights. The model catalog has no separate structured-output boolean; model-card support and actual POSTs provide the relevant evidence. This read-only GET is separate from generation counts.

## Exact working packaging

`scripts/mistral_json_probe.py` loads only `PARAMETERS`, `DECISION`, `QUESTION` and `SCHEMA` declarations from the existing publication `tools/p5_interactive/operational.py`, without importing its solver or loading scenarios/labels. It deep-copies that schema, then deletes exactly:

```text
/oneOf/2/properties/decision/properties/evidence/uniqueItems
/oneOf/2/properties/decision/properties/missing_slots/uniqueItems
```

Every capture's intent records the canonical source path/hash and exact generated wire schema; request.json contains the actual SDK-serialized HTTP body. There is no second manually authored P8 schema.

```python
from mistralai.client import Mistral, models

client = Mistral(api_key=key, client=http_capture_client, retry_config=None)
response = client.chat.complete(
    model="mistral-small-latest",
    messages=messages,
    temperature=0,
    max_tokens=2048,
    reasoning_effort="none",
    random_seed=20261027,
    tools=[], tool_choice="none", retries=None,
    response_format=models.ResponseFormat(
        type="json_schema",
        json_schema=models.JSONSchema(
            name="padua_action", schema_definition=wire_schema, strict=True,
        ),
    ),
)
```

SDK `schema_definition` serializes to HTTP `schema`. The actual wrapper is `response_format={type:"json_schema",json_schema:{name:"padua_action",schema:WIRE,strict:true}}`. Transport: POST `https://api.mistral.ai/v1/chat/completions`, stream=false. Wire tests verify schema preservation and no retry on400/429/503. System/user messages are preserved as messages, with no native tools or external search. Server-side conditioning remains unobserved.

**Do not substitute `chat.parse()` without auditing schema semantics.** In installed SDK2.10.1, `response_format_from_pydantic_model` calls `rec_strict_json_schema`, which recursively assigns `additionalProperties:false` to all type=object nodes. This destroys the canonical integer dictionary and closes other objects with intentionally unspecified additional properties. An offline regression test demonstrates that a valid nonempty parameter artifact then becomes invalid. Direct `chat.complete()` avoids that helper and preserves the schema body.

## Sequential retained attempts

All fixtures are independently authored serialization artifacts with DEV identifiers. Requested text is retained in each intent and actual request. These are not13 P8 cases or their Gold Labels. A feasible-looking route here is not a mathematically verified operational decision.

|Attempt|Variant / fixture|HTTP|Result|
|---|---|---:|---|
|01|Tiny object, boolean `ok`|200|Exact tiny JSON; intentionally outside P8|
|02|Unchanged canonical / null FINAL|400|Invalid structured output syntax,3051|
|03|Canonical + root type=object / null FINAL|400|3051; root type alone does not resolve rejection|
|04|Canonical oneOf→anyOf only / null FINAL|400|3051; union substitution alone does not resolve rejection|
|05|Tiny rooted oneOf with distinct canonical action consts|200|Exact FINAL discriminator; intentionally incomplete P8 action|
|06|Canonical minus two uniqueItems / null FINAL|200|Original P8 schema valid; exact fixture|
|07|Same wire / numeric FINAL|200|Nonempty integer map, nested route and plan; original P8 schema valid|
|08|Same wire / ASK_USER|200|Questions, enums and strings; original P8 schema valid|
|09|Same wire / CALL_TOOL|200|Nonempty arguments/parameters; original P8 schema valid; no tool executed|
|10|Tiny evidence array with canonical uniqueItems=true|400|3051|
|11|Same tiny evidence array minus uniqueItems only|200|Exact array; isolated contrast|

The full `no-unique` wire retains root oneOf, const/enum, nullable object plan, arbitrary string-key integer dictionary with0..86400 bounds, closed action/decision/question objects, and nested arrays/objects with item/length constraints. Its accepted syntax and representative valid instances are demonstrated; this is not an exhaustive test that the server enforces every retained constraint or preserves every JSON Schema default. Tiny controls intentionally fail canonical P8 validation and are labelled accordingly; failed HTTP requests have no model response to validate.

The same wire schema can be serialized by the existing raw HTTP adapter; SDK capture tests show no special SDK transformation is required. Transfer requires only a provider-specific copy with the two keywords omitted and canonical validation retained. No existing publication adapter was modified by this separate SCM experiment, and no new production SDK integration is implied.

## Native versus local responsibility

The serving profile accepts native schema conditioning with the above grammar. Uniqueness is omitted from that grammar and remains a mandatory canonical-validator constraint. Local validation also remains authoritative for every retained type, range, required field and structural restriction. Source identity/authority, entity/scope/time applicability, evidence completeness, refusal closure, admission and route mathematics are outside the proven native syntax profile and retain their existing checks. Generated responses were not modified. Four valid synthetic artifacts do not establish scientific decision accuracy or superiority of Mistral/Cognitive Sandwich.

## Accounting, evidence and verification

11 sequential POSTs,7 HTTP200 completions,4 HTTP400s; one separate model-catalog GET. Minimum measured completion-to-next-dispatch gap: **15.080s**, using local durable hook timestamps. No retry, replacement, fallback, unknown completion or alternate-model inference. Successful responses report **440 input +244 output tokens**, reasoning tokens0. At Small's documented USD0.15/M input +USD0.60/M output, the successful-response estimate is **USD0.0002124**, ignoring cache discounts. This is not invoice confirmation; failed-request usage/charges are unreported.

Conservative reservations: priorUSD0.34 +11×USD0.05 = **USD0.89**, leaving **USD1.11** underUSD2. Each reservation covers even262144 input tokens plus2048 output tokens at the inspected Small tariff (USD0.0405504). No old SQLite ledger was changed; this diagnostic uses its own append-only JSONL journal and immutable attempt directories. Browser attempts remain0.

Each attempt retains intent/schema/messages, actual request body (without authentication headers), raw response bytes, raw assistant content on success, allowlisted HTTP metadata, usage/model metadata and canonical validation. HTTP captures are bodies observed by the SDK's httpx hooks, not full TLS/network packet captures. Request IDs are retained when supplied in allowlisted headers. `summary.json` aggregates without replacing originals. Credential-value scan and hashes are recorded in `manifest.json`.

Repository validation: **Ruff PASS, mypy PASS (83 source files), pytest72 passed /1 skipped**; logs are retained next to this report. The new tests cover actual SDK wire serialization, retries, canonical fixtures, non-equivalence of omitted uniqueness, dictionary/range rejection and the destructive parse-helper transformation. Tests requiring the external Padua source skip when it is absent; set `PADUA_CANONICAL_SOURCE` to its owning operational.py on another checkout. The5 new test functions (one parameterized across3 statuses) ran locally. One existing suite skip is unrelated.

An initial new-test edit misplaced a range assertion and failed lint/one test; it was corrected offline without repeating any provider call. Final logs show the corrected suite. No historical measurement, private input, old worktree or original cohort was changed.

Smallest next step: port the two-keyword provider wire adjustment into the existing publication HTTP adapter under an explicitly named prospective profile, keeping canonical response validation. Do not launch a scientific batch or reinterpret historical scores automatically.
