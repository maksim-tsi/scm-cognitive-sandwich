"""Pinned llama.cpp request fields; schema support is audited separately offline."""
from __future__ import annotations

from typing import Any


def build_request(body: dict[str,Any], schema: dict[str,Any]|None = None) -> dict[str,Any]:
    result={**body,'top_p':1,'seed':20261027,'chat_template_kwargs':{'enable_thinking':False}}
    if schema is not None:result['response_format']={'type':'json_schema','schema':schema}
    return result
