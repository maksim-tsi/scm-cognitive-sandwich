"""Scripted offline transport. This module cannot dispatch a network request."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any


class DuplicateKeyError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("nonfinite JSON constant")


def strict_json(data: bytes) -> Any:
    return json.loads(
        data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant
    )


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


class MockTransport:
    """Consume exactly one explicit event per request, never retry or replace.

    Events: status=complete + raw_response_bytes (the exact server envelope);
    or timeout_connect / timeout_unknown_completion / transport_error. Partial
    events may include raw_response_bytes and assistant_content_bytes explicitly;
    these are preserved, never guessed from invalid/truncated envelopes. Valid
    envelopes yield UTF-8 encoding of the ORIGINAL decoded content string, not
    reserialized output JSON. A JSON envelope cannot retain source string escape
    spellings in its decoded assistant content; raw_response_bytes preserves them.
    """

    max_retries = 0

    def __init__(
        self, events: Iterable[Mapping[str, Any]], *, clock: Callable[[], Any] = _now
    ):
        self._events = iter(events)
        self._clock = clock
        self._used_ids: set[str] = set()

    def send(self, request_id: str, request_bytes: bytes) -> dict[str, Any]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a nonempty string")
        if not isinstance(request_bytes, bytes):
            raise TypeError("request_bytes must be bytes")
        if request_id in self._used_ids:
            raise ValueError(
                "request_id already attempted; replacement attempts forbidden"
            )
        self._used_ids.add(request_id)
        started = self._clock()
        try:
            event = dict(next(self._events))
        except StopIteration as exc:
            raise ValueError("mock script exhausted; no replacement attempt") from exc
        status = event.get("status", "complete")
        if status not in {
            "complete",
            "timeout_connect",
            "timeout_unknown_completion",
            "transport_error",
        }:
            raise ValueError("unsupported scripted status")
        raw = event.get("raw_response_bytes")
        content = event.get("assistant_content_bytes")
        if raw is not None and not isinstance(raw, bytes):
            raise TypeError("raw_response_bytes must be bytes")
        if content is not None and not isinstance(content, bytes):
            raise TypeError("assistant_content_bytes must be bytes")
        capture: dict[str, Any] = {
            "transport_kind": "scripted_mock_only",
            "clock_source": "local_utc" if self._clock is _now else "injected_test_clock",
            "request_id": request_id,
            "request_bytes": request_bytes,
            "started_at": started,
            "finished_at": None,
            "status": status,
            "attempt_count": 1,
            "retries": 0,
            "dispatched": False
            if status == "timeout_connect"
            else event.get(
                "dispatched",
                True if status in {"complete", "timeout_unknown_completion"} else None,
            ),
            "unknown_completion": status
            in {"timeout_unknown_completion", "transport_error"},
            "raw_response_bytes": raw,
            "assistant_content_bytes": content,
            "response_id": None,
            "model": None,
            "usage": None,
            "system_fingerprint": None,
            "identity_verified": False,
            "finish_reason": None,
            "parsed_output": None,
            "error": None,
        }
        if status == "complete":
            capture["unknown_completion"] = False
            if raw is None:
                capture.update(
                    status="malformed_envelope", error="missing_response_envelope"
                )
            else:
                try:
                    envelope = strict_json(raw)
                    if not isinstance(envelope, dict):
                        raise TypeError("envelope_must_be_object")
                    capture["response_id"] = envelope.get("id")
                    # Reported metadata is observation, never runtime identity proof.
                    # The preserved raw envelope remains authoritative evidence.
                    capture["model"] = envelope.get("model")
                    capture["usage"] = envelope.get("usage")
                    capture["system_fingerprint"] = envelope.get("system_fingerprint")
                    choices = envelope.get("choices")
                    if not isinstance(choices, list) or len(choices) != 1:
                        raise ValueError("exactly_one_choice_required")
                    choice = choices[0]
                    capture["finish_reason"] = choice.get("finish_reason")
                    message = choice.get("message")
                    if (
                        not isinstance(message, dict)
                        or message.get("role") != "assistant"
                        or not isinstance(message.get("content"), str)
                    ):
                        raise ValueError("original_assistant_string_required")
                    extracted = message["content"].encode("utf-8")
                    if content is not None and content != extracted:
                        raise ValueError("scripted_content_disagrees_with_envelope")
                    capture["assistant_content_bytes"] = extracted
                except DuplicateKeyError:
                    capture.update(
                        status="duplicate_keys", error="duplicate_envelope_keys"
                    )
                except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
                    capture.update(
                        status="malformed_envelope", error="invalid_response_envelope"
                    )
                else:
                    if capture["finish_reason"] == "length":
                        capture.update(
                            status="truncation", error="finish_reason_length"
                        )
                    elif (
                        capture["finish_reason"] != "stop"
                        or message.get("tool_calls")
                        or message.get("function_call")
                    ):
                        capture.update(
                            status="incomplete_completion",
                            error="nonstop_or_tool_completion",
                        )
                    else:
                        try:
                            output = strict_json(extracted)
                            if not isinstance(output, dict):
                                raise TypeError("output_must_be_object")
                            capture["parsed_output"] = output
                        except DuplicateKeyError:
                            capture.update(
                                status="duplicate_keys", error="duplicate_output_keys"
                            )
                        except (ValueError, TypeError, UnicodeError):
                            capture.update(
                                status="malformed_json", error="invalid_assistant_json"
                            )
        capture["finished_at"] = self._clock()
        return capture
