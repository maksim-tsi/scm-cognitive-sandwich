"""Single sequential SDK development probe; never a scientific cohort runner."""
from __future__ import annotations

import argparse
import ast
import copy
import datetime as dt
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

import httpx
from dotenv import dotenv_values
from jsonschema import Draft202012Validator
from mistralai.client import Mistral, models

PUBLICATION = Path('/Users/max/Documents/papers/ltx-mdpi-optimizing-urban-freight-2026')
CANONICAL = Path(os.environ.get('PADUA_CANONICAL_SOURCE', str(
    PUBLICATION / '.local-worktrees/publication-mistral/tools/p5_interactive/operational.py')))
OUT = Path(__file__).resolve().parents[1] / 'docs/reports/mistral-sdk-json'
FIXTURES: dict[str, Any] = {
    'tiny': {'ok': True},
    'action-only': {'action': 'FINAL'},
    'evidence-only': {'evidence': ['DEV-A', 'DEV-B']},
    'ask': {'action': 'ASK_USER', 'questions': [{'wording': 'Development value?', 'entity': 'DEV',
        'field': 'dev_slot', 'scope': 'DEV', 'owner': 'dispatcher', 'kind': 'indispensable'}]},
    'tool': {'action': 'CALL_TOOL', 'tool': 'plan_route', 'arguments': {'parameters': {'dev_slot': 7}}},
    'numeric': {'action': 'FINAL', 'decision': {'action': 'UPDATE', 'parameters': {'dev_slot': 7},
        'plan': {'status': 'FEASIBLE', 'routes': [{'vehicle': 0, 'nodes': [0, 1, 0]}]},
        'evidence': ['DEV-RECORD'], 'missing_slots': []}},
    'null': {'action': 'FINAL', 'decision': {'action': 'INSUFFICIENT', 'parameters': {},
        'plan': None, 'evidence': [], 'missing_slots': ['dev_slot']}},
}


def canonical_schema(path: Path = CANONICAL) -> dict[str, Any]:
    """Evaluate only schema declarations from the owning source, with no solver imports."""
    tree = ast.parse(path.read_text())
    names = {'PARAMETERS', 'DECISION', 'QUESTION', 'SCHEMA'}
    selected = [n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    namespace: dict[str, Any] = {'__builtins__': {'list': list}}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    schema = namespace['SCHEMA']
    Draft202012Validator.check_schema(schema)
    return schema


def wire_schema(schema: dict[str, Any], variant: str) -> dict[str, Any]:
    result = copy.deepcopy(schema)
    if variant == 'tiny':
        return {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                'required': ['ok'], 'additionalProperties': False}
    if variant in ('tiny-oneof', 'tiny-anyof'):
        key = 'oneOf' if variant == 'tiny-oneof' else 'anyOf'
        return {'type': 'object', key: [
            {'type': 'object', 'properties': {'action': copy.deepcopy(b['properties']['action'])},
             'required': ['action'], 'additionalProperties': False} for b in schema['oneOf']]}
    if variant == 'no-unique':
        for key in ('evidence', 'missing_slots'):
            del result['oneOf'][2]['properties']['decision']['properties'][key]['uniqueItems']
        return result
    if variant in ('tiny-unique', 'tiny-array'):
        evidence = copy.deepcopy(schema['oneOf'][2]['properties']['decision']['properties']['evidence'])
        if variant == 'tiny-array':
            del evidence['uniqueItems']
        return {'type': 'object', 'properties': {'evidence': evidence},
                'required': ['evidence'], 'additionalProperties': False}
    if variant == 'root-object':
        result['type'] = 'object'
    elif variant == 'anyof':
        result['anyOf'] = result.pop('oneOf')
    elif variant != 'canonical':
        raise ValueError('Unknown explicit schema variant')
    return result


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def write(path: Path, value: Any) -> None:
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def prior_reservations() -> float:
    total = 0.0
    for cohort in ('padua-mistral-operational-pilot', 'padua-mistral-native-v1'):
        p = PUBLICATION / 'private' / cohort / 'run/calls.sqlite'
        with sqlite3.connect(f'file:{p}?mode=ro', uri=True) as db:
            if db.execute("select count(*) from calls where status!='processed'").fetchone()[0]:
                raise RuntimeError('Unfinished historical call')
            total += db.execute('select coalesce(sum(reservation),0) from calls').fetchone()[0]
    return round(total, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=FIXTURES, required=True)
    parser.add_argument('--variant', choices=['tiny', 'canonical', 'root-object', 'anyof',
                                            'tiny-oneof', 'tiny-anyof', 'no-unique',
                                            'tiny-unique', 'tiny-array'], required=True)
    parser.add_argument('--json-only', action='store_true')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if not args.live:
        parser.error('Explicit --live required')
    OUT.mkdir(parents=True, exist_ok=True)
    schema = canonical_schema()
    wire = wire_schema(schema, args.variant)
    previous = sorted(OUT.glob('attempt-*'))
    for p in previous:
        if not (p / 'result.json').exists():
            raise RuntimeError('Unfinished attempt; never replay')
    if previous:
        last = json.loads((previous[-1] / 'result.json').read_text())
        if last['status'] not in ('complete', 'schema_rejected'):
            raise RuntimeError('Previous attempt requires inspection')
        wait = 15 - (time.time() - last['finished_epoch'])
        if wait > 0:
            time.sleep(wait)
    prior = prior_reservations()
    if len(previous) >= 12 or prior + (len(previous) + 1) * .05 > 2:
        raise RuntimeError('Budget exhausted')
    catalog = json.loads((OUT / 'models.json').read_text())
    small = next(x for x in catalog['models'] if x['id'] == 'mistral-small-latest')
    if small['name'] != 'mistral-small-2603' or small['max_context_length'] > 262144:
        raise RuntimeError('Small identity/context cost envelope changed')
    secret = os.environ.get('MISTRAL_API_KEY') or dotenv_values(
        '/Users/max/Documents/code/scm-cognitive-sandwich/.env').get('MISTRAL_API_KEY')
    if not secret:
        raise RuntimeError('Configured Mistral credential absent')
    directory = OUT / f'attempt-{len(previous)+1:02d}'
    directory.mkdir()
    messages = [{'role': 'system', 'content': 'Return one JSON object for an independent synthetic development serialization test. No tools or search.'},
                {'role': 'user', 'content': 'Serialize this development artifact as JSON: ' + json.dumps(FIXTURES[args.fixture])}]
    write(directory / 'intent.json', {'at': now(), 'fixture': args.fixture, 'variant': args.variant,
        'mode': 'json_object' if args.json_only else 'json_schema', 'messages': messages,
        'schema_source': str(CANONICAL), 'source_sha256': hashlib.sha256(CANONICAL.read_bytes()).hexdigest(),
        'wire_schema': wire, 'reservation_usd': .05, 'prior_reservations_usd': prior,
        'sdk_version': importlib.metadata.version('mistralai'), 'difference': args.variant})
    posted = 0

    def capture_request(request: httpx.Request) -> None:
        nonlocal posted
        if request.method != 'POST' or str(request.url) != 'https://api.mistral.ai/v1/chat/completions':
            raise RuntimeError('Unexpected SDK destination/method')
        posted += 1
        if posted != 1:
            raise RuntimeError('Retry forbidden')
        body = request.read()
        if secret.encode() in body:
            raise RuntimeError('Credential in request body')
        (directory / 'request.json').write_bytes(body)
        write(directory / 'dispatch.json', {'at': now(), 'url': str(request.url), 'method': request.method})

    def capture_response(response: httpx.Response) -> None:
        raw = response.read()
        if secret.encode() in raw:
            raise RuntimeError('Credential echo; stop')
        (directory / 'response.json').write_bytes(raw)
        write(directory / 'http.json', {'at': now(), 'status': response.status_code,
            'headers': {k:v for k,v in response.headers.items() if k in ('content-type', 'x-request-id', 'mistral-correlation-id')}})

    result: dict[str, Any] = {'status': 'unknown_completion', 'validation': None}
    try:
        with httpx.Client(event_hooks={'request': [capture_request], 'response': [capture_response]},
                          timeout=60, follow_redirects=False) as http:
            client = Mistral(api_key=secret, client=http, retry_config=None, timeout_ms=60000)
            fmt = models.ResponseFormat(type='json_object') if args.json_only else models.ResponseFormat(
                type='json_schema', json_schema=models.JSONSchema(name='padua_action', schema_definition=wire, strict=True))
            response = client.chat.complete(model='mistral-small-latest', messages=messages,
                temperature=0, max_tokens=2048, reasoning_effort='none', random_seed=20261027,
                response_format=fmt, tools=[], tool_choice='none', retries=None)
            raw_text = response.choices[0].message.content
            if not isinstance(raw_text, str):
                raise ValueError('Expected raw text')
            (directory / 'content.txt').write_text(raw_text)
            event = json.loads(raw_text)
            errors = [e.message for e in Draft202012Validator(schema).iter_errors(event)]
            result.update(status='complete', model=response.model, usage=response.usage.model_dump(mode='json'),
                validation={'canonical_P8_valid': not errors, 'errors': errors,
                'wire_valid': Draft202012Validator(wire).is_valid(event), 'fixture_exact': event == FIXTURES[args.fixture]},
                finish_reason=response.choices[0].finish_reason)
            if response.model not in ('mistral-small-2603', 'mistral-small-latest'):
                result['status'] = 'identity_mismatch'
            if response.choices[0].finish_reason == 'length':
                result['status'] = 'output_truncated'
    except Exception as exc:
        # Raw bodies retained by hooks; never print exception text (may include credentials).
        result['exception_type'] = type(exc).__name__
        if (directory / 'http.json').exists():
            code = json.loads((directory / 'http.json').read_text())['status']
            raw = json.loads((directory / 'response.json').read_bytes()) if (directory / 'response.json').exists() else {}
            result['status'] = 'schema_rejected' if code == 400 and str(raw.get('code')) == '3051' else 'provider_error'
    result.update(finished_at=now(), finished_epoch=time.time(), posted=posted, reservation_usd=.05)
    write(directory / 'result.json', result)
    with (OUT / 'journal.jsonl').open('a') as log:
        log.write(json.dumps({'attempt': directory.name, **result}) + '\n')
    print(json.dumps({'attempt': directory.name, **result}))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'probe.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
