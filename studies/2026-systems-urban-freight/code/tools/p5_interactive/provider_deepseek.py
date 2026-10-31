"""Official DeepSeek JSON-object profile; native JSON Schema is not documented."""
from __future__ import annotations

from typing import Any


def build_request(body: dict[str,Any], schema: dict[str,Any]|None = None) -> dict[str,Any]:
    if schema is not None:raise ValueError('DeepSeek does not document native JSON Schema; no hidden fallback')
    return {**body,'thinking':{'type':'disabled'}}
