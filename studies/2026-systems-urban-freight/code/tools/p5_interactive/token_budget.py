"""Bounded serialization plus exact local accounting for long Qwen histories."""
from __future__ import annotations

import functools
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.p4_world.world import canonical
from tools.p5_interactive.build_token_counter import DEFAULT

MESSAGE_BYTE_GUARD=16*1024
CONSERVATIVE_MESSAGE_BYTES=11264
PROMPT_TOKEN_CEILING=12288
MAX_OUTPUT_TOKENS=2048
CONTEXT_TOKENS=16384
VOCAB_SHA='9ccc7c4d9d2606ec46dacf12338c7400261670b402b4440a6a25002275455c80'
TEMPLATE_SHA='12827f24b742ea4e80cdc12dbcf9622227056b9f797252a3149263d4f9aaadce'


def message_bytes(messages: list[dict[str,str]]) -> int:
    size=len(canonical(messages).encode())
    if size>MESSAGE_BYTE_GUARD:raise ValueError('Full transcript exceeds16KiB serialization guard; never truncate')
    return size


@functools.lru_cache(maxsize=16)
def _identity(helper: str, vocabulary: str, receipt: str) -> dict[str,Any]:
    binding=json.loads(Path(receipt).read_text())
    if (binding['llama_commit']!='7170cad4d02f7907517613931840cbb2367399a3' or
        hashlib.sha256(Path(helper).read_bytes()).hexdigest()!=binding['helper_sha256'] or
        hashlib.sha256(Path(vocabulary).read_bytes()).hexdigest()!=VOCAB_SHA or
        hashlib.sha256(Path(__file__).with_name('token_accounting.cpp').read_bytes()).hexdigest()!=binding['source_sha256']):
        raise ValueError('Local tokenizer artifact identity differs; rebuild/requalify offline')
    return binding


@functools.lru_cache(maxsize=64)
def exact_qwen(body: bytes) -> dict[str,Any]:
    helper=DEFAULT/'p8/padua-token-accounting';vocabulary=DEFAULT/'vocabulary-only.gguf';receipt=DEFAULT/'p8/build.json'
    try:
        binding=_identity(str(helper),str(vocabulary),str(receipt))
        payload=canonical({'case_id':'runtime','body':json.loads(body)}).encode()+b'\n'
        done=subprocess.run([str(helper),str(vocabulary)],input=payload,capture_output=True,timeout=30,check=False)
        if done.returncode:raise ValueError('Offline tokenizer refused request profile')
        r=json.loads(done.stdout)
        if (hashlib.sha256(r['template_source'].encode()).hexdigest()!=TEMPLATE_SHA or
            r['generation_calls']!=0 or r['llama_context_created'] or r['count']!=len(r['token_ids'])):
            raise ValueError('Offline tokenizer/template invariant failed')
    except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        raise ValueError('Long Qwen request requires the qualified local offline counter') from exc
    return {'method':'b11815_exact_server_path','prompt_tokens':r['count'],
            'rendered_prompt_sha256':hashlib.sha256(r['rendered_prompt'].encode()).hexdigest(),
            'token_ids_sha256':hashlib.sha256(canonical(r['token_ids']).encode()).hexdigest(),
            'helper_sha256':binding['helper_sha256'],'vocabulary_sha256':VOCAB_SHA,'template_sha256':TEMPLATE_SHA}


def account(route: str, body: bytes) -> dict[str,Any]:
    data=json.loads(body);size=message_bytes(data['messages'])
    # This uncapped bound also reserves DeepSeek expenditure; it is not claimed
    # to be an exact measurement of the proprietary DeepSeek chat template.
    schema_bytes=len(canonical(data['response_format']).encode()) if data['response_format'].get('type')=='json_schema' else 0
    result={'method':'conservative_message_bytes_plus1024','message_bytes':size,'input_reservation_envelope':size+schema_bytes+1024}
    if schema_bytes:
        result.update(method='message_and_schema_bytes_plus1024',schema_bytes=schema_bytes)
        if route=='qwen':raise ValueError('Native Qwen schema profile needs separate template/token qualification; no inference authorised')
    if route=='qwen' and size>CONSERVATIVE_MESSAGE_BYTES:
        exact=exact_qwen(body)
        if exact['prompt_tokens']>PROMPT_TOKEN_CEILING:raise ValueError('Exact Qwen prompt exceeds12288 tokens; never truncate')
        result.update(exact)
    return result
