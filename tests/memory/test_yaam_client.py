import asyncio

import httpx
from opentelemetry import context as context_api
from opentelemetry import trace as trace_api
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from memory.yaam_client import DEFAULT_AGENT_ID, YAAMClient, _build_traceparent


class DummyResponse:
    def __init__(self, should_raise: bool = False):
        self._should_raise = should_raise

    def raise_for_status(self) -> None:
        if self._should_raise:
            request = httpx.Request("POST", "http://localhost")
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError("server error", request=request, response=response)


class DummyAsyncClient:
    def __init__(self, response: DummyResponse | Exception):
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def post(self, url: str, json: dict, headers: dict, timeout: float):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_default_endpoint_is_disabled_by_default():
    client = YAAMClient()

    assert client.endpoint is None


def test_base_url_without_path_is_normalized_to_endpoint():
    client = YAAMClient(base_url="http://localhost:8002")

    assert client.endpoint == "http://localhost:8002/v1/memory/episode/consolidate"


def test_consolidate_episode_returns_false_when_disabled(monkeypatch):
    client = YAAMClient()

    success = asyncio.run(
        client.consolidate_episode(
            session_id="session-1",
            final_state={
                "prompt": None,
                "drafts": [],
                "solver_iis_logs": [],
                "final_routing_parameters": {},
            },
            metadata={"status": "success", "duration_seconds": 0.0, "solver_attempts": 1},
        )
    )

    assert success is False


def test_consolidate_episode_success_includes_traceparent_header():
    dummy = DummyAsyncClient(response=DummyResponse())
    client = YAAMClient(base_url="http://localhost:8002", client=dummy)
    final_state = {
        "prompt": "storm alert",
        "drafts": [],
        "solver_iis_logs": [],
        "final_routing_parameters": {},
    }
    metadata = {
        "status": "success",
        "duration_seconds": 0.0,
        "solver_attempts": 1,
    }

    success = asyncio.run(
        client.consolidate_episode(
            session_id="session-1",
            final_state=final_state,
            metadata=metadata,
            agent_id="scm-sandwich-experiment-v1",
        )
    )

    assert success is True
    assert len(dummy.calls) == 1
    call = dummy.calls[0]
    headers = call["headers"]
    assert isinstance(headers, dict)
    assert "traceparent" in headers
    assert str(headers["traceparent"]).startswith("00-")
    payload = call["json"]
    assert payload == {
        "session_id": "session-1",
        "agent_id": "scm-sandwich-experiment-v1",
        "final_state": final_state,
        "metadata": metadata,
    }


def test_consolidate_episode_uses_default_agent_id_when_omitted():
    dummy = DummyAsyncClient(response=DummyResponse())
    client = YAAMClient(base_url="http://localhost:8002", client=dummy)

    success = asyncio.run(
        client.consolidate_episode(
            session_id="session-1",
            final_state={
                "prompt": None,
                "drafts": [],
                "solver_iis_logs": [],
                "final_routing_parameters": {},
            },
            metadata={"status": "success", "duration_seconds": 0.0, "solver_attempts": 1},
        )
    )

    assert success is True
    assert len(dummy.calls) == 1
    payload = dummy.calls[0]["json"]
    assert payload["agent_id"] == DEFAULT_AGENT_ID


def test_consolidate_episode_returns_false_on_http_status_error():
    dummy = DummyAsyncClient(response=DummyResponse(should_raise=True))
    client = YAAMClient(base_url="http://localhost:8002", client=dummy)

    success = asyncio.run(
        client.consolidate_episode(
            "session-1",
            {
                "prompt": None,
                "drafts": [],
                "solver_iis_logs": [],
                "final_routing_parameters": {},
            },
            {"status": "success", "duration_seconds": 0.0, "solver_attempts": 1},
        )
    )

    assert success is False


def test_consolidate_episode_returns_false_on_transport_error():
    dummy = DummyAsyncClient(response=httpx.ConnectError("boom"))
    client = YAAMClient(base_url="http://localhost:8002", client=dummy)

    success = asyncio.run(
        client.consolidate_episode(
            "session-1",
            {
                "prompt": None,
                "drafts": [],
                "solver_iis_logs": [],
                "final_routing_parameters": {},
            },
            {"status": "success", "duration_seconds": 0.0, "solver_attempts": 1},
        )
    )

    assert success is False


def test_build_traceparent_uses_active_span_context():
    trace_id_hex = "1" * 32
    span_id_hex = "2" * 16
    span_context = SpanContext(
        trace_id=int(trace_id_hex, 16),
        span_id=int(span_id_hex, 16),
        is_remote=False,
        trace_flags=TraceFlags(0x01),
        trace_state=trace_api.TraceState(),
    )

    token = context_api.attach(trace_api.set_span_in_context(NonRecordingSpan(span_context)))
    try:
        traceparent = _build_traceparent()
    finally:
        context_api.detach(token)

    assert traceparent == f"00-{trace_id_hex}-{span_id_hex}-01"
