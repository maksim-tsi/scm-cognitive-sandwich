"""Public packet-quality checks, separate from outcome/gold evaluation."""

from __future__ import annotations

import re
from typing import Any

from .runtime import FIELDS, instant


def check_packet(packet: dict[str, Any]) -> None:
    allowed = {
        "case_id",
        "decision_time",
        "effective_time",
        "field",
        "target_entity",
        "entities",
        "message",
        "current_state",
        "evidence",
        "facts",
    }
    if set(packet) - allowed:
        raise ValueError("Only public runtime packet fields are permitted")
    if packet["field"] not in FIELDS:
        raise ValueError("Unknown field")
    instant(packet["decision_time"])
    instant(packet["effective_time"])
    entities = [e["id"] for e in packet["entities"]]
    if len(set(entities)) != len(entities):
        raise ValueError("Duplicate entity IDs")
    if packet["target_entity"] is not None and packet["target_entity"] not in entities:
        raise ValueError("Unknown target entity")
    if set(packet["current_state"]) != set(entities):
        raise ValueError("State/entity key mismatch")
    for state in packet["current_state"].values():
        for field in ["receiving_window_start", "receiving_window_end"]:
            if not isinstance(state.get(field), str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", state[field]
            ):
                raise ValueError("Invalid current time of day")
        value = state.get("service_duration")
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not 0 < value <= 240
        ):
            raise ValueError("Invalid current service duration")
    ids = [r["id"] for r in packet["evidence"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate evidence IDs")
    graph = {r["id"]: r["supersedes"] for r in packet["evidence"]}
    for record in packet["evidence"]:
        if set(record["entity_ids"]) - set(entities) or set(record["fields"]) - FIELDS:
            raise ValueError("Unknown record scope")
        if set(record["supersedes"]) - set(ids):
            raise ValueError("Dangling supersession reference")
        if (
            record.get("available_at")
            and record.get("published_at")
            and instant(record["published_at"]) > instant(record["available_at"])
        ):
            raise ValueError("Source cannot be available before publication")
        for key in [
            "available_at",
            "published_at",
            "effective_from",
            "effective_until",
            "revoked_at",
        ]:
            if record.get(key) is not None:
                instant(record[key])
        if (
            record.get("effective_from")
            and record.get("effective_until")
            and instant(record["effective_from"]) >= instant(record["effective_until"])
        ):
            raise ValueError("Invalid effective interval")
        if (
            not record.get("available_at")
            or instant(record["available_at"]) > instant(packet["decision_time"])
        ) and record.get("content") is not None:
            raise ValueError(
                "Unavailable content must be null in article runtime packets"
            )

    def visit(node: str, path: set[str]) -> None:
        if node in path:
            raise ValueError("Cyclic supersession")
        for target in graph[node]:
            visit(target, path | {node})

    for node in graph:
        visit(node, set())
