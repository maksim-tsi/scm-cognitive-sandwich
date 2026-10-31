"""Official Mistral request fields; no SDK prompt rewriting or output repair."""
from __future__ import annotations

import copy
from typing import Any


def build_request(body: dict[str,Any], schema: dict[str,Any]|None = None, *, omit_uniqueness: bool = False) -> dict[str,Any]:
    result={**body,'reasoning_effort':'none','random_seed':20261027}
    if omit_uniqueness:
        if schema is None:raise ValueError('Native P8 schema required for explicit uniqueness adaptation')
        schema=copy.deepcopy(schema)
        for field in ('evidence','missing_slots'):
            node=schema['oneOf'][2]['properties']['decision']['properties'][field]
            if node.get('uniqueItems') is not True:raise ValueError('Expected canonical uniqueness constraint differs')
            del node['uniqueItems']
    if schema is not None:
        result['response_format']={'type':'json_schema','json_schema':{'name':'padua_action','strict':True,'schema':schema}}
    return result
