"""Reference-free mock workflow and exact-byte capture, never a live runner."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import jsonschema

from ..core.episode import run_event_episode
from ..core.evaluator import evaluate
from ..core.solver import solve
from ..evidence_layer.proposal_replay import replay
from ..evidence_layer.runtime import apply_decision, s1
from .protocol import build_request, public_packet, serialize_request
from .transport import MockTransport, strict_json


def _failed_lane(
    packet: dict[str, Any], status: str, original: bytes | None
) -> dict[str, Any]:
    return {
        "state": copy.deepcopy(packet["current_state"]),
        "admission": {"admitted": False, "reason": status},
        "attempt_status": status,
        "normalized_proposal": None,
        "final_decision": None,
        "gate_rejection": None,
        "gate_fallback": None,
        "original_sha256": hashlib.sha256(original).hexdigest()
        if original is not None
        else None,
    }


def _seconds(value: str) -> int:
    hour, minute = (int(v) for v in value.split(":"))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError("invalid local clock")
    return hour * 3600 + minute * 60


def state_to_instance(
    instance: dict[str, Any], state: dict[str, Any], entity_nodes: dict[str, int]
) -> dict[str, Any]:
    result = copy.deepcopy(instance)
    if len(set(entity_nodes.values())) != len(entity_nodes):
        raise ValueError("entity-to-node map must be one-to-one")
    orders = {order["node"]: order for order in result["orders"]}
    for entity, node in entity_nodes.items():
        if entity not in state or node not in orders:
            raise ValueError("missing entity/node routing binding")
        fields = state[entity]
        duration = float(fields["service_duration"]) * 60
        if not duration.is_integer() or duration <= 0:
            raise ValueError("planning duration must map to positive integer seconds")
        orders[node].update(
            open_s=_seconds(fields["receiving_window_start"]),
            close_s=_seconds(fields["receiving_window_end"]),
            service_s=int(duration),
        )
    return result


def run_offline_episode(
    packet: dict[str, Any],
    capture: dict[str, Any],
    *,
    route_instance: dict[str, Any] | None = None,
    entity_nodes: dict[str, int] | None = None,
    solver_budget_s: float = 0.03,
) -> dict[str, Any]:
    """Runtime takes no annotation/reference arguments and loads no case files."""
    public = public_packet(packet)
    original = capture.get("assistant_content_bytes")
    status = capture["status"]
    output_schema = json.loads(
        Path(__file__).with_name("output.schema.json").read_text()
    )
    if status == "complete":
        try:
            if not isinstance(original, bytes):
                raise TypeError("completed response lacks original bytes")
            original_object = strict_json(original)
            if serialize_request(original_object) != serialize_request(
                capture["parsed_output"]
            ):
                raise ValueError("detached parsed output differs from original bytes")
            jsonschema.Draft202012Validator(output_schema).validate(original_object)
        except (
            jsonschema.ValidationError,
            ValueError,
            TypeError,
            KeyError,
            UnicodeError,
        ):
            status = "unqualified_output"
    if status == "complete":
        if not isinstance(original, bytes):
            raise ValueError("completed response must have exact original bytes")
        paired = replay(public, original)
        s2, s3 = paired["s2"], paired["s3"]
    else:
        paired = {
            "original_sha256": hashlib.sha256(original).hexdigest()
            if isinstance(original, bytes)
            else None
        }
        s2 = _failed_lane(public, status, original)
        s3 = copy.deepcopy(s2)
    deterministic = apply_decision(public, s1(public), False)
    lanes = {
        "S0": {
            "lane": "S0",
            "state": copy.deepcopy(public["current_state"]),
            "attempt_status": "static_reference",
        },
        "S1": {**deterministic, "lane": "S1"},
        "S2": {**s2, "lane": "S2"},
        "S3": {**s3, "lane": "S3"},
    }
    routing: dict[str, Any] = {}
    if route_instance is not None:
        if entity_nodes is None:
            raise ValueError("explicit public entity-to-node bindings required")
        matrix_hash = hashlib.sha256(
            serialize_request({k: route_instance[k] for k in ["distance_m", "time_s"]})
        ).hexdigest()
        for lane, result in lanes.items():
            configured = state_to_instance(
                route_instance, result["state"], entity_nodes
            )
            solution = solve(configured, solver_budget_s)
            routing[lane] = {
                "instance": configured,
                "solution": solution,
                "checker": evaluate(configured, solution),
                "matrix_sha256": matrix_hash,
                "solver_budget_s": solver_budget_s,
                "rolling_replay": run_event_episode(
                    route_instance,
                    [
                        {
                            "at_s": route_instance["shift_start_s"],
                            "order_updates": [
                                {
                                    k: order[k]
                                    for k in ["node", "open_s", "close_s", "service_s"]
                                }
                                for order in configured["orders"]
                            ],
                        }
                    ],
                    solver_budget_s,
                ),
            }
    return {
        "classification": "OFFLINE_MOCK_ONLY",
        "case_id": public["case_id"],
        "public_packet": public,
        "s0_state": lanes["S0"]["state"],
        "lanes": lanes,
        "routing": routing,
        "original_sha256": paired["original_sha256"],
        "same_original_s2_s3": (
            lanes["S2"].get("proposal_hash") == lanes["S3"].get("proposal_hash")
        )
        if status == "complete"
        else None,
        "capture_status": status,
    }


def mock_attempt(
    packet: dict[str, Any], request_id: str, transport: MockTransport, **kwargs: Any
) -> dict[str, Any]:
    if type(transport) is not MockTransport:
        raise TypeError("offline entrypoint accepts only the exact mock transport")
    body = build_request(packet, request_id)
    capture = transport.send(request_id, serialize_request(body))
    return {
        "request": body,
        "capture": capture,
        "workflow": run_offline_episode(packet, capture, **kwargs),
    }


class MockBatch:
    """One attempted generation per base ID, including errors; never retry."""

    def __init__(self, transport: MockTransport, *, ceiling: int = 60):
        if (
            type(transport) is not MockTransport
            or type(ceiling) is not int
            or not 1 <= ceiling <= 60
        ):
            raise ValueError("mock batch needs fixed mock transport and ceiling 1..60")
        self.transport = transport
        self.ceiling = ceiling
        self.case_ids: set[str] = set()
        self.request_ids: set[str] = set()

    def attempt(
        self, packet: dict[str, Any], request_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        case_id = public_packet(packet)["case_id"]
        if case_id in self.case_ids or request_id in self.request_ids:
            raise ValueError("case/request already attempted; replacement forbidden")
        if len(self.case_ids) >= self.ceiling:
            raise ValueError("request ceiling exhausted")
        # Reserve before send: even exceptions never create retry eligibility.
        self.case_ids.add(case_id)
        self.request_ids.add(request_id)
        return mock_attempt(packet, request_id, self.transport, **kwargs)


def write_capture(root: Path, capture: dict[str, Any]) -> Path:
    """Immutable per-attempt files; raw bytes are not parsed and reserialized."""
    request_id = capture["request_id"]
    if (
        not isinstance(request_id, str)
        or re.fullmatch(r"[A-Za-z0-9_-]+", request_id) is None
    ):
        raise ValueError("unsafe capture request ID")
    directory = root / request_id
    directory.mkdir(parents=True, exist_ok=False)
    metadata: dict[str, Any] = {}
    for key, value in capture.items():
        if isinstance(value, bytes):
            (directory / (key + ".bin")).write_bytes(value)
            metadata[key] = {
                "sha256": hashlib.sha256(value).hexdigest(),
                "bytes": len(value),
                "base64": base64.b64encode(value).decode("ascii"),
            }
        else:
            metadata[key] = value
    (directory / "capture.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n"
    )
    return directory
