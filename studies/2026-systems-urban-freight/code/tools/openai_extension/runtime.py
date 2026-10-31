"""Luna Responses transport and capture on the existing episode/journal path.

No credential discovery or API calls on import. Exactly one HTTP attempt per
capture. The wrapper is serial because the existing controller's capture hook
is process-global; never use it concurrently.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tools.openai_extension.adapter import build_request, parse_response
from tools.p4_world.world import canonical
from tools.p5_interactive.experiment import run_episode
from tools.p5_interactive.providers import (
    BudgetExhausted,
    HttpClient,
    IntegrityError,
    Journal,
    save_json,
    utc,
)
from tools.p5_interactive.token_budget import message_bytes
from tools.padua_pilot.transport import _save
from stage2.runner.transport import strict_json

_LOCK = threading.Lock()
MODEL = "gpt-6-luna"
INPUT_RATE = 0.10
CACHE_WRITE_RATE = 0.125
OUTPUT_RATE = 0.50


class ResponsesClient(HttpClient):
    kind = "https_openai_responses"

    def __init__(self, secret: str, *, test_url: str | None = None):
        super().__init__("deepseek", secret, test_url=test_url)
        if test_url is None:
            self.url = "https://api.openai.com/v1/responses"
        self._last_completion: float | None = None
        self.last_pacing_s = 0.0

    def _pace(self) -> None:
        started = time.monotonic()
        if self._last_completion is not None:
            time.sleep(max(0.0, 1.0 - (started - self._last_completion)))
        self.last_pacing_s = time.monotonic() - started

    def send(
        self, body: bytes, request_id: str, directory: Path
    ) -> tuple[str, int | None]:
        try:
            return super().send(body, request_id, directory)
        finally:
            self._last_completion = time.monotonic()


def _usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Missing usage")
    a, b, total = (
        value.get("input_tokens"),
        value.get("output_tokens"),
        value.get("total_tokens"),
    )
    if type(a) is not int or type(b) is not int or type(total) is not int:
        raise ValueError("Invalid usage")
    if a < 0 or b < 0 or total != a + b:
        raise ValueError("Invalid usage")
    inp = value.get("input_tokens_details") or {}
    out = value.get("output_tokens_details") or {}
    if not isinstance(inp, dict) or not isinstance(out, dict):
        raise ValueError("Invalid usage details")
    cached, reasoning = inp.get("cached_tokens", 0), out.get("reasoning_tokens", 0)
    cache_write = inp.get("cache_write_tokens")
    if (
        type(cached) is not int
        or type(reasoning) is not int
        or not 0 <= cached <= a
        or not 0 <= reasoning <= b
        or (
            cache_write is not None
            and (
                type(cache_write) is not int
                or cache_write < 0
                or cached + cache_write > a
            )
        )
    ):
        raise ValueError("Invalid token details")
    return {
        "input_tokens": a,
        "output_tokens": b,
        "total_tokens": total,
        "cached_input_tokens": cached,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": reasoning,
        "estimated_cost_usd_upper_standard": (a * CACHE_WRITE_RATE + b * OUTPUT_RATE)
        / 1_000_000,
    }


def replay_input(
    journal: Journal, episode: str, messages: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Replay original output items, bound to the controller's selected actions."""
    with journal.connect() as db:
        rows = db.execute(
            "SELECT id,status FROM calls WHERE episode=? ORDER BY rowid", (episode,)
        ).fetchall()
    assistants = [m for m in messages if m["role"] == "assistant"]
    if len(rows) != len(assistants) or any(status != "processed" for _, status in rows):
        raise IntegrityError("Transcript and processed journal differ")
    history: list[dict[str, Any]] = []
    index = 0
    for message in messages:
        if message["role"] != "assistant":
            history.append(dict(message))
            continue
        directory = journal.root / rows[index][0]
        raw = (directory / "response.bin").read_bytes()
        metadata = json.loads((directory / "capture.json").read_text())
        if hashlib.sha256(raw).hexdigest() != metadata.get("response_sha256"):
            raise IntegrityError("Replay response hash mismatch")
        envelope = strict_json(raw)
        selected, _ = parse_response(envelope)
        if selected != message["content"]:
            raise IntegrityError("Controller action differs from retained response")
        history.extend(envelope["output"])
        index += 1
    return history


def capture(
    journal: Journal,
    client: Any,
    route: str,
    episode: str,
    messages: list[dict[str, str]],
) -> tuple[dict[str, Any], str, Path]:
    if route != "openai":
        raise ValueError("OpenAI extension route required")
    nbytes = message_bytes(messages)
    request = build_request(messages)
    request["input"] = replay_input(journal, episode, messages)
    body = canonical(request).encode()
    # Reserve separately from the historical 16 KiB serialization guard.
    # The byte-plus-overhead estimate is not an exact provider token count.
    input_bound = max(nbytes, len(body)) + 1024
    ceiling = (
        math.ceil(
            (input_bound * CACHE_WRITE_RATE + 2048 * OUTPUT_RATE) / 1_000_000 * 100
        )
        / 100
    )
    if time.time() >= journal.deadline:
        raise BudgetExhausted("wall_clock_limit")
    request_id, directory = journal.reserve(episode, route, ceiling)
    _save(directory / "request.bin", body)
    started, start = utc(), time.monotonic()
    try:
        transport_status, code = client.send(body, request_id, directory)
    except Exception:
        journal.stop("transport_or_persistence_exception")
        raise
    elapsed = time.monotonic() - start
    raw_path = directory / "response.bin"
    raw = raw_path.read_bytes() if raw_path.exists() else b""
    result: dict[str, Any] = {
        "status": transport_status,
        "unknown_completion": transport_status == "unknown_completion",
        "parsed_output": None,
        "assistant_content_bytes": None,
        "requested_model": MODEL,
        "model": None,
        "system_fingerprint": None,
        "usage": None,
        "http_status": code,
        "started_at": started,
        "finished_at": utc(),
        "elapsed_s": elapsed,
        "pacing_s": getattr(client, "last_pacing_s", 0.0),
        "api_transport_elapsed_s": max(
            0.0, elapsed - getattr(client, "last_pacing_s", 0.0)
        ),
        "request_sha256": hashlib.sha256(body).hexdigest(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "reservation_input_tokens": input_bound,
        "reservation_output_tokens": 2048,
        "committed_reservation_usd": ceiling,
        "provider_route": route,
        "client_kind": client.kind,
        "response_capture_present": raw_path.exists(),
    }
    if transport_status == "complete" and code == 200:
        try:
            envelope = strict_json(raw)
            if not isinstance(envelope, dict):
                raise ValueError("Invalid envelope")
            result["response_id"] = envelope.get("id")
            result["model"] = envelope.get("model")
            result["usage"] = _usage(envelope.get("usage"))
            if not isinstance(result["model"], str) or not (
                result["model"] == MODEL or result["model"].startswith(MODEL + "-")
            ):
                raise ValueError("Unexpected model identity")
            if (
                result["usage"]["input_tokens"] > input_bound
                or result["usage"]["output_tokens"] > 2048
            ):
                journal.stop("reported_token_budget_violation")
                raise ValueError("Token limit exceeded")
            result.update(journal.bind_identity(route, result["model"], None))
            try:
                content, event = parse_response(envelope)
            except (ValueError, TypeError) as exc:
                # Malformed action text and refusal are case outcomes. Unexpected
                # envelope/item types remain technical failures that stop collection.
                model_failures = (
                    "Expected exactly one final answer",
                    "Missing or unsupported message phase",
                    "Expected exactly one output text; refusals are retained failures",
                    "Non-finite JSON",
                    "Duplicate JSON key",
                    "Action must be a JSON object",
                )
                if isinstance(exc, json.JSONDecodeError) or any(
                    str(exc).startswith(x) for x in model_failures
                ):
                    result.update(status="model_output_failure", parsed_output=None)
                else:
                    raise
            else:
                result.update(
                    status="complete",
                    parsed_output=event,
                    assistant_content_bytes=content.encode(),
                )
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            result.update(status="invalid_response", parsed_output=None)
    elif transport_status == "complete":
        result["status"] = "http_error"
    save_json(
        directory / "capture.json",
        {k: v for k, v in result.items() if not isinstance(v, bytes)},
    )
    journal.captured(request_id)
    if result["unknown_completion"] or result["status"] in (
        "http_error",
        "transport_failure",
    ):
        journal.stop("provider_or_transport_failure")
    return result, request_id, directory


def run_luna_episode(
    definition: dict[str, Any], client: Any, journal: Journal, *, name: str
) -> dict[str, Any]:
    """Serial wrapper around the unchanged controller and evaluator."""
    if not _LOCK.acquire(blocking=False):
        raise IntegrityError("Concurrent Responses episodes unsupported")
    try:
        with patch("tools.p5_interactive.experiment.capture", capture):
            result = run_episode(definition, client, journal, "openai", name=name)
        with journal.connect() as db:
            calls = db.execute(
                "SELECT id, status, reservation FROM calls WHERE episode=? ORDER BY rowid",
                (name,),
            ).fetchall()
        accounting = {
            "episode": name,
            "request_intents": len(calls),
            "dispatch_intents": sum(
                (journal.root / row[0] / "dispatch.intent").exists() for row in calls
            ),
            "reserved_usd": sum(row[2] for row in calls),
            "legacy_controller_generation_count_is_not_applicable": True,
            "capture_ids": [row[0] for row in calls],
        }
        save_json(journal.root / name / "luna-accounting.json", accounting)
        return result
    finally:
        _LOCK.release()
