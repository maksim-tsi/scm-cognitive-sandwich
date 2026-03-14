import asyncio
import inspect
import logging
import os
import threading
from collections.abc import Awaitable
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

LOGGER = logging.getLogger(__name__)

DEFAULT_CHECKPOINT_PREFIX = "sandwich:checkpoint:"


async def _await_value(value: Awaitable[Any]) -> Any:
    return await value


def _resolve_awaitable(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_value(value))

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _target() -> None:
        try:
            result["value"] = asyncio.run(_await_value(value))
        except BaseException as exc:  # pragma: no cover - defensive safety net
            error["value"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result["value"]


def _load_redis_saver_class() -> type[Any] | None:
    """Return the best available Redis saver class for sync graph compilation."""
    try:
        from langgraph.checkpoint.redis import RedisSaver

        return RedisSaver
    except Exception:
        pass

    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver

        return AsyncRedisSaver
    except Exception:
        pass

    try:
        from langgraph.checkpoint.redis import AsyncRedisSaver

        return AsyncRedisSaver
    except Exception:
        pass

    return None


def _set_prefix_if_supported(saver: Any, key_prefix: str) -> None:
    for attr_name in ("key_prefix", "prefix"):
        if hasattr(saver, attr_name):
            try:
                setattr(saver, attr_name, key_prefix)
                return
            except Exception:
                continue


def _setup_saver_if_supported(saver: Any) -> None:
    setup = getattr(saver, "setup", None)
    if not callable(setup):
        return

    _resolve_awaitable(setup())


def _try_build_saver(
    saver_cls: type[Any],
    redis_url: str,
    key_prefix: str,
) -> Any:
    builder_names = ("from_conn_string", "from_url")
    for builder_name in builder_names:
        builder = getattr(saver_cls, builder_name, None)
        if not callable(builder):
            continue

        for args, kwargs in (
            ((redis_url,), {"key_prefix": key_prefix}),
            ((redis_url,), {"prefix": key_prefix}),
            ((redis_url,), {}),
        ):
            try:
                saver = builder(*args, **kwargs)
            except TypeError:
                continue

            saver = _resolve_awaitable(saver)
            if not isinstance(saver, saver_cls):
                continue

            _set_prefix_if_supported(saver, key_prefix)
            _setup_saver_if_supported(saver)
            return saver

    for kwargs in (
        {"redis_url": redis_url, "key_prefix": key_prefix},
        {"url": redis_url, "key_prefix": key_prefix},
        {"connection_string": redis_url, "key_prefix": key_prefix},
        {"redis_url": redis_url},
        {"url": redis_url},
        {"connection_string": redis_url},
    ):
        try:
            saver = saver_cls(**kwargs)
        except TypeError:
            continue

        saver = _resolve_awaitable(saver)

        _set_prefix_if_supported(saver, key_prefix)
        _setup_saver_if_supported(saver)
        return saver

    raise RuntimeError(
        "No compatible constructor was found for the installed Redis checkpointer class."
    )


def create_checkpointer(
    redis_url: str | None = None,
    *,
    key_prefix: str = DEFAULT_CHECKPOINT_PREFIX,
) -> Any:
    """Create an adaptive LangGraph checkpointer.

    Behavior:
        - If REDIS_URL is set (for example redis://host:6379/0), attempt Redis saver.
        - If the saver exposes setup(), run it before returning the saver to initialize
            required Redis indices.
    - If REDIS_URL is missing or Redis saver initialization fails, fall back to MemorySaver.

    The Redis database index isolation is intentionally URL-driven.
    """
    raw_redis_url = redis_url if redis_url is not None else os.getenv("REDIS_URL")
    resolved_redis_url = (raw_redis_url or "").strip()
    if not resolved_redis_url:
        return MemorySaver()

    saver_cls = _load_redis_saver_class()
    if saver_cls is None:
        LOGGER.warning(
            "REDIS_URL was provided, but no Redis checkpointer package was found. "
            "Falling back to MemorySaver."
        )
        return MemorySaver()

    try:
        return _try_build_saver(saver_cls=saver_cls, redis_url=resolved_redis_url, key_prefix=key_prefix)
    except Exception as exc:
        LOGGER.warning(
            "Failed to initialize Redis checkpointer from REDIS_URL=%s. "
            "Falling back to MemorySaver. Error: %s",
            resolved_redis_url,
            exc,
        )
        return MemorySaver()
