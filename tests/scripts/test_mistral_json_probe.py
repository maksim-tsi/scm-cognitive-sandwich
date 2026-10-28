"""SDK wire-fidelity checks without provider calls."""
import copy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from mistralai.client import Mistral, models
from mistralai.extra.utils._pydantic_helper import rec_strict_json_schema


spec = importlib.util.spec_from_file_location('probe', Path(__file__).parents[2] / 'scripts/mistral_json_probe.py')
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
pytestmark = pytest.mark.skipif(not probe.CANONICAL.exists(), reason='External canonical Padua source not present')


@pytest.mark.parametrize('status', [400, 429, 503])
def test_sdk_preserves_full_schema_and_sampling_and_does_not_retry(status):
    schema = probe.canonical_schema()
    original = copy.deepcopy(schema)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(status, json={'message': 'synthetic rejection'})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        sdk = Mistral(api_key='synthetic-only', client=http, retry_config=None)
        try:
            sdk.chat.complete(model='mistral-small-latest', messages=[{'role': 'user', 'content': 'JSON'}],
                response_format=models.ResponseFormat(type='json_schema', json_schema=models.JSONSchema(
                    name='padua_action', schema_definition=schema, strict=True)),
                temperature=0, max_tokens=2048, reasoning_effort='none', random_seed=20261027,
                tools=[], tool_choice='none', retries=None)
        except Exception:
            pass
    assert len(requests) == 1
    body = requests[0]
    assert body['response_format']['json_schema'] == {'name': 'padua_action', 'schema': schema, 'strict': True}
    assert body['reasoning_effort'] == 'none' and body['random_seed'] == 20261027
    assert body['max_tokens'] == 2048 and body['temperature'] == 0
    assert body['tools'] == [] and body['tool_choice'] == 'none'
    assert schema == original


def test_canonical_branch_fixtures_and_logically_redundant_root_type():
    schema = probe.canonical_schema()
    root = probe.wire_schema(schema, 'root-object')
    assert root == {'type': 'object', **schema}
    assert all(branch['type'] == 'object' for branch in schema['oneOf'])
    for name, event in probe.FIXTURES.items():
        assert Draft202012Validator(schema).is_valid(event) == (name not in ('tiny', 'action-only', 'evidence-only'))
        assert Draft202012Validator(root).is_valid(event) == (name not in ('tiny', 'action-only', 'evidence-only'))


def test_action_branches_are_disjoint_before_anyof_substitution():
    schema = probe.canonical_schema()
    branches = schema['oneOf']
    actions = [b['properties']['action']['const'] for b in branches]
    assert len(set(actions)) == len(branches)
    assert all('action' in b['required'] for b in branches)
    # Each branch requires the same field to have a distinct constant: no instance can match two.
    wire = probe.wire_schema(schema, 'anyof')
    for event in probe.FIXTURES.values():
        assert Draft202012Validator(schema).is_valid(event) == Draft202012Validator(wire).is_valid(event)


def test_no_unique_wire_is_broader_but_canonical_validator_still_rejects_duplicates():
    schema = probe.canonical_schema()
    before = copy.deepcopy(schema)
    wire = probe.wire_schema(schema, 'no-unique')
    event = copy.deepcopy(probe.FIXTURES['numeric'])
    event['decision']['evidence'] = ['DEV-RECORD', 'DEV-RECORD']
    assert Draft202012Validator(wire).is_valid(event)
    assert not Draft202012Validator(schema).is_valid(event)
    assert schema == before
    event['decision']['parameters'] = {'dev_slot': [7]}
    assert not Draft202012Validator(wire).is_valid(event)
    event['decision']['parameters'] = {'dev_slot': 86401}
    assert not Draft202012Validator(wire).is_valid(event)


def test_sdk_parse_helper_would_destroy_nonempty_parameter_dictionary():
    schema = probe.canonical_schema()
    rewritten = rec_strict_json_schema(copy.deepcopy(schema))
    event = probe.FIXTURES['numeric']
    assert Draft202012Validator(schema).is_valid(event)
    assert not Draft202012Validator(rewritten).is_valid(event)
    assert rewritten['oneOf'][2]['properties']['decision']['properties']['parameters']['additionalProperties'] is False
