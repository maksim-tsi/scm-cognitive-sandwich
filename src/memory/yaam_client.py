import logging
import os
import secrets
from typing import Any
from urllib.parse import urlparse

import httpx
from opentelemetry import trace as trace_api

LOGGER = logging.getLogger(__name__)

DEFAULT_YAAM_API_URL = "http://localhost:8002/v1/memory/episode/consolidate"


def _normalize_endpoint(raw_url: str) -> str:
    """Allow either a full endpoint URL or a bare host:port base URL."""
    normalized = raw_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.path and parsed.path != "/":
        return normalized
    return f"{normalized}/v1/memory/episode/consolidate"


def _build_traceparent() -> str:
    span = trace_api.get_current_span()
    context = span.get_span_context() if span is not None else None

    if context is not None and context.is_valid:
        trace_id = f"{context.trace_id:032x}"
        span_id = f"{context.span_id:016x}"
    else:
        # Keep the header valid even when no active span is available.
        trace_id = secrets.token_hex(16)
        span_id = secrets.token_hex(8)

    return f"00-{trace_id}-{span_id}-01"


class YAAMClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        raw_url = base_url if base_url is not None else os.getenv("YAAM_API_URL")
        configured_url = (raw_url or DEFAULT_YAAM_API_URL).strip()
        self._endpoint = _normalize_endpoint(configured_url)
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def consolidate_episode(self, session_id: str, episode_state: dict[str, Any]) -> bool:
        payload = {
            "session_id": session_id,
            "episode_state": episode_state,
        }
        headers = {
            "traceparent": _build_traceparent(),
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    self._endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self._endpoint,
                        json=payload,
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )

            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            LOGGER.warning(
                "YAAM consolidate call failed for session_id=%s endpoint=%s error=%s",
                session_id,
                self._endpoint,
                exc,
            )
            return False
