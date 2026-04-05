from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"{key} must be set.")
    return value


def get_openrouter_chat(
    *,
    model: str | None = None,
    temperature: float = 0,
    timeout_s: float = 60,
    extra_kwargs: dict[str, Any] | None = None,
) -> BaseChatModel:
    """Create an OpenRouter-backed chat model compatible with tool calling + structured output.

    Env contract:
      - OPENROUTER_API_KEY: required (validated by langchain-openrouter on init)
      - LLM_MODEL: default model name (e.g. x-ai/grok-4.1-fast)
      - OPENROUTER_BASE_URL: optional (defaults to OpenRouter SDK default)
    """
    resolved_model = (model or os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL") or "").strip()
    if not resolved_model:
        raise ValueError("LLM_MODEL (or OPENROUTER_MODEL) must be set (or pass model=...).")

    # langchain-openrouter validates OPENROUTER_API_KEY at init time.
    _require_env("OPENROUTER_API_KEY")

    from langchain_openrouter import ChatOpenRouter  # noqa: WPS433

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "temperature": temperature,
        "timeout": timeout_s,
    }
    base_url = os.getenv("OPENROUTER_BASE_URL")
    if base_url and base_url.strip():
        kwargs["base_url"] = base_url.strip()
    if extra_kwargs:
        kwargs.update(extra_kwargs)

    return ChatOpenRouter(**kwargs)
