"""Responses wire profile for the existing text-only action protocol.

This module is offline only. It does not dispatch, change a model action, or
replace the controller's canonical schema validation.
"""

from __future__ import annotations
import json
import math
from typing import Any


def build_request(
    messages: list[dict[str, str]], *, max_output_tokens: int = 2048
) -> dict[str, Any]:
    if not messages or max_output_tokens < 1:
        raise ValueError("Explicit scenario messages and output limit required")
    if any(
        set(m) != {"role", "content"}
        or m["role"] not in {"system", "user", "assistant"}
        or not isinstance(m["content"], str)
        for m in messages
    ):
        raise ValueError("Expected explicit text-only scenario transcript")
    return {
        "model": "gpt-6-luna",
        "input": [
            {**m, **({"phase": "final_answer"} if m["role"] == "assistant" else {})}
            for m in messages
        ],
        "store": False,
        "reasoning": {"effort": "none"},
        "temperature": 0,
        "max_output_tokens": max_output_tokens,
        "text": {"format": {"type": "json_object"}},
    }


def parse_response(envelope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract the sole final-answer text; retain commentary only in raw evidence.

    Return raw text and parsed JSON. Local canonical action validation remains
    the controller's responsibility; no field normalization or retry occurs.
    """
    if envelope.get("status") != "completed":
        raise ValueError("Response incomplete, failed, or missing status")
    output = envelope.get("output")
    if not isinstance(output, list) or not output:
        raise ValueError("Missing output")
    finals = []
    for item in output:
        if (
            not isinstance(item, dict)
            or item.get("type") != "message"
            or item.get("role") != "assistant"
            or item.get("status") != "completed"
        ):
            raise ValueError("Unsupported output item")
        if item.get("phase") == "final_answer":
            finals.append(item)
        elif item.get("phase") == "commentary":
            parts = item.get("content")
            if (
                not isinstance(parts, list)
                or not parts
                or any(
                    not isinstance(part, dict) or part.get("type") != "output_text"
                    for part in parts
                )
            ):
                raise ValueError("Unsupported or refusal commentary")
        else:
            raise ValueError("Missing or unsupported message phase")
    if len(finals) != 1:
        raise ValueError("Expected exactly one final answer")
    item = finals[0]
    content = item.get("content")
    if (
        not isinstance(content, list)
        or len(content) != 1
        or not isinstance(content[0], dict)
        or content[0].get("type") != "output_text"
        or not isinstance(content[0].get("text"), str)
    ):
        raise ValueError(
            "Expected exactly one output text; refusals are retained failures"
        )
    raw = content[0]["text"]

    def reject_constant(value: str) -> None:
        raise ValueError("Non-finite JSON constant: " + value)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON number")
        return number

    result = json.loads(
        raw,
        parse_constant=reject_constant,
        parse_float=finite_float,
        object_pairs_hook=unique,
    )
    if not isinstance(result, dict):
        raise ValueError("Action must be a JSON object")
    return raw, result
