"""Fixed public request contract. No provider, network or credential access."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..evidence_layer.conditional_instructions import CONDITION_ALIASES
from ..evidence_layer.runtime import released_packet

_ROOT = Path(__file__).parent
PACKET_KEYS = frozenset(
    {
        "case_id",
        "decision_time",
        "effective_time",
        "field",
        "target_entity",
        "entities",
        "message",
        "current_state",
        "facts",
        "evidence",
    }
)
ENTITY_KEYS = frozenset({"id", "name", "aliases"})
STATE_KEYS = frozenset(
    {"receiving_window_start", "receiving_window_end", "service_duration"}
)
EVIDENCE_KEYS = frozenset(
    {
        "id",
        "source_type",
        "verified",
        "content",
        "available_at",
        "published_at",
        "effective_from",
        "effective_until",
        "entity_ids",
        "fields",
        "supersedes",
        "revoked_at",
    }
)


def public_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Project only public fields, then reuse common release redaction.

    Unknown nested objects are not forwarded through scalar or list slots.
    Malformed input fails closed rather than leaking diagnostic dictionaries.
    """
    result = copy.deepcopy({k: v for k, v in packet.items() if k in PACKET_KEYS})
    result["entities"] = [
        {k: v for k, v in item.items() if k in ENTITY_KEYS}
        for item in result.get("entities", [])
    ]
    result["evidence"] = [
        {k: v for k, v in item.items() if k in EVIDENCE_KEYS}
        for item in result.get("evidence", [])
    ]
    result["current_state"] = {
        entity: {k: v for k, v in state.items() if k in STATE_KEYS}
        for entity, state in result.get("current_state", {}).items()
    }
    if "facts" in result and (
        not isinstance(result["facts"], dict)
        or any(type(v) is not bool for v in result["facts"].values())
    ):
        raise ValueError("facts must contain explicit boolean scenario facts")
    if "facts" in result:
        # Only declared public scenario facts can enter a model prompt. An
        # extra analysis/gold boolean is not public merely because it is bool.
        result["facts"] = {
            key: value
            for key, value in result["facts"].items()
            if key in CONDITION_ALIASES
        }
    # Validate against public packet schema so arbitrary nested analysis objects
    # cannot be hidden inside an otherwise allowed property.
    import jsonschema

    schema = json.loads(
        (_ROOT.parent / "evidence_layer" / "packet.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).validate(result)
    return released_packet(result)


def serialize_request(body: Mapping[str, Any]) -> bytes:
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def build_request(packet: Mapping[str, Any], request_id: str) -> dict[str, Any]:
    """Build a server body; request_id belongs to capture metadata only."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must be a nonempty string")
    schema = json.loads((_ROOT / "output.schema.json").read_text(encoding="utf-8"))
    system = (
        (_ROOT / "prompt.txt").read_text(encoding="utf-8")
        + "\nOUTPUT JSON SCHEMA:\n"
        + serialize_request(schema).decode("utf-8")
    )
    return {
        "model": "qwen3.8-27b-ud-q4_k_m",
        "temperature": 0,
        "top_p": 1,
        "seed": 20261024,
        "max_tokens": 2048,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "tools": [],
        "tool_choice": "none",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": serialize_request(public_packet(packet)).decode("utf-8"),
            },
        ],
    }
