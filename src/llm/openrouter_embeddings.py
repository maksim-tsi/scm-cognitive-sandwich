from __future__ import annotations

import os
import time
from typing import Any

import httpx


DEFAULT_EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
EXPECTED_DIMENSIONS = 4096


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"{key} must be set.")
    return value.strip()


def _openrouter_base_url() -> str:
    base_url = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip()
    return base_url.rstrip("/")


def embed_text(
    text: str,
    *,
    model: str | None = None,
    timeout_s: float = 60.0,
) -> tuple[list[float], float]:
    """Embed text via OpenRouter, returning (embedding_vector, latency_ms)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    api_key = _require_env("OPENROUTER_API_KEY")
    resolved_model = (model or os.getenv("OPENROUTER_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL).strip()
    if not resolved_model:
        raise ValueError("Embedding model must be set (model=... or OPENROUTER_EMBEDDING_MODEL).")

    url = f"{_openrouter_base_url()}/embeddings"
    headers: dict[str, str] = {"Authorization": f"Bearer {api_key}"}

    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    if referer and referer.strip():
        headers["HTTP-Referer"] = referer.strip()
    title = os.getenv("OPENROUTER_X_TITLE")
    if title and title.strip():
        headers["X-Title"] = title.strip()

    payload: dict[str, Any] = {"model": resolved_model, "input": text}

    start_ns = time.perf_counter_ns()
    with httpx.Client() as client:
        response = client.post(url, json=payload, headers=headers, timeout=timeout_s)
        response.raise_for_status()
        data = response.json()
    latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

    embedding: Any | None = None
    if isinstance(data, dict):
        items = data.get("data")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                embedding = first.get("embedding")

    if not isinstance(embedding, list) or not all(isinstance(x, (int, float)) for x in embedding):
        raise ValueError("OpenRouter embeddings response missing numeric data[0].embedding list.")

    vector = [float(x) for x in embedding]
    if len(vector) != EXPECTED_DIMENSIONS:
        raise ValueError(f"Embedding dims mismatch: expected {EXPECTED_DIMENSIONS}, got {len(vector)}.")

    return vector, latency_ms

