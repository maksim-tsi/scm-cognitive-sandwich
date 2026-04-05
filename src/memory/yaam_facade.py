"""
YAAMFacade: direct, explicit memory read/write surface for the orchestrator.

WinterSim constraints:
- No YAAM HTTP "frontgate" (YAAM_API_URL is deprecated).
- No autonomous background engines/polling/consolidation logic inside the facade.
- The orchestrator (LangGraph nodes) owns when and how memory is read/written.

This module intentionally keeps implementations lightweight and adapter-agnostic:
callers inject concrete Redis/Postgres/Qdrant/Typesense clients (sync or async).
"""

from __future__ import annotations

import asyncio
import inspect
import os
import threading
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Coroutine
from typing import Any, cast


def _run_awaitable(value: Awaitable[Any]) -> Any:
    return asyncio.run(cast(Coroutine[Any, Any, Any], value))


def _resolve_awaitable(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_awaitable(cast(Awaitable[Any], value))

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _target() -> None:
        try:
            result["value"] = _run_awaitable(cast(Awaitable[Any], value))
        except BaseException as exc:  # pragma: no cover - defensive safety net
            error["value"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result.get("value")


@dataclass(frozen=True)
class _L2Key:
    namespace: str
    key: str


class YAAMFacade:
    """Direct orchestrator memory facade for L1-L4."""

    def __init__(
        self,
        *,
        project: str,
        agent_id: str | None = None,
        redis_client: Any | None = None,
        postgres: Any | None = None,
        qdrant: Any | None = None,
        typesense: Any | None = None,
    ) -> None:
        self.project = project
        self.agent_id = agent_id

        self._redis = redis_client
        self._postgres = postgres
        self._qdrant = qdrant
        self._typesense = typesense

        # Deterministic in-process fallbacks (used when no external client is injected).
        self._l1_kv: dict[str, Any] = {}
        self._l2_kv: dict[_L2Key, Any] = {}
        self._l3_collections: dict[str, list[dict[str, Any]]] = {}
        self._l4_collections: dict[str, list[dict[str, Any]]] = {}

        self._artifacts: dict[str, dict[str, Any]] = {}

    # --- L1 (Redis) ---
    def l1_get(self, key: str) -> Any | None:
        if self._redis is None:
            return self._l1_kv.get(key)
        get = getattr(self._redis, "get", None)
        if not callable(get):
            raise RuntimeError("Redis client does not support get().")
        return _resolve_awaitable(get(key))

    def l1_set(self, key: str, value: Any, *, ttl_s: int | None = None) -> None:
        if self._redis is None:
            self._l1_kv[key] = value
            return

        if ttl_s is not None:
            setex = getattr(self._redis, "setex", None)
            if callable(setex):
                _resolve_awaitable(setex(key, ttl_s, value))
                return

        set_ = getattr(self._redis, "set", None)
        if not callable(set_):
            raise RuntimeError("Redis client does not support set().")
        _resolve_awaitable(set_(key, value))
        if ttl_s is not None:
            expire = getattr(self._redis, "expire", None)
            if callable(expire):
                _resolve_awaitable(expire(key, ttl_s))

    # --- L2 (Postgres) ---
    def l2_put(self, namespace: str, key: str, value_json: str) -> None:
        if self._postgres is None:
            self._l2_kv[_L2Key(namespace=namespace, key=key)] = value_json
            return

        put = getattr(self._postgres, "put", None)
        if callable(put):
            _resolve_awaitable(put(namespace=namespace, key=key, value_json=value_json))
            return

        raise RuntimeError("Postgres client is injected but does not implement put().")

    def l2_get(self, namespace: str, key: str) -> str | None:
        if self._postgres is None:
            value = self._l2_kv.get(_L2Key(namespace=namespace, key=key))
            return cast(str | None, value)

        get = getattr(self._postgres, "get", None)
        if callable(get):
            return cast(str | None, _resolve_awaitable(get(namespace=namespace, key=key)))

        raise RuntimeError("Postgres client is injected but does not implement get().")

    # --- L3 (Qdrant) ---
    def l3_upsert(self, collection: str, points: list[dict[str, Any]]) -> None:
        if self._qdrant is None:
            self._l3_collections.setdefault(collection, []).extend(points)
            return

        upsert = getattr(self._qdrant, "upsert", None)
        if callable(upsert):
            _resolve_awaitable(upsert(collection=collection, points=points))
            return

        raise RuntimeError("Qdrant client is injected but does not implement upsert().")

    def l3_search(
        self,
        collection: str,
        query_vector: list[float],
        *,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if self._qdrant is None:
            # Deterministic fallback: no real vector search; return latest N.
            rows = self._l3_collections.get(collection, [])
            return list(rows[-limit:])

        search = getattr(self._qdrant, "search", None)
        if callable(search):
            result = _resolve_awaitable(
                search(collection=collection, query_vector=query_vector, limit=limit, filters=filters)
            )
            return cast(list[dict[str, Any]], result)

        raise RuntimeError("Qdrant client is injected but does not implement search().")

    # --- L4 (Typesense) ---
    def l4_upsert(self, collection: str, document: dict[str, Any]) -> None:
        if self._typesense is None:
            self._l4_collections.setdefault(collection, []).append(document)
            return

        upsert = getattr(self._typesense, "upsert", None)
        if callable(upsert):
            _resolve_awaitable(upsert(collection=collection, document=document))
            return

        index_document = getattr(self._typesense, "index_document", None)
        if callable(index_document):
            _resolve_awaitable(index_document(collection_name=collection, document=document))
            return

        raise RuntimeError("Typesense client is injected but does not implement upsert().")

    def l4_search(self, collection: str, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        if self._typesense is None:
            rows = self._l4_collections.get(collection, [])
            return list(rows[-limit:])

        search = getattr(self._typesense, "search", None)
        if callable(search):
            result = _resolve_awaitable(search(collection=collection, query=query, limit=limit))
            return cast(list[dict[str, Any]], result)

        raise RuntimeError("Typesense client is injected but does not implement search().")

    # --- Artifact helpers (compat for existing baseline graph) ---
    def artifact_save_draft(self, artifact_data: dict[str, Any]) -> str:
        artifact_id = f"draft-{uuid.uuid4().hex}"
        self._artifacts[artifact_id] = {"draft": artifact_data, "feedback": [], "revisions": []}
        return artifact_id

    def artifact_attach_feedback(self, artifact_id: str, feedback: str) -> None:
        artifact = self._artifacts.setdefault(artifact_id, {"draft": None, "feedback": [], "revisions": []})
        cast(list[str], artifact["feedback"]).append(feedback)

    def artifact_create_revision(self, previous_artifact_id: str, new_artifact_data: dict[str, Any]) -> str:
        revision_id = f"rev-{uuid.uuid4().hex}"
        artifact = self._artifacts.setdefault(
            previous_artifact_id, {"draft": None, "feedback": [], "revisions": []}
        )
        cast(list[dict[str, Any]], artifact["revisions"]).append(
            {"revision_id": revision_id, "data": new_artifact_data}
        )
        return revision_id

    def artifact_commit_final(self, artifact_id: str) -> None:
        self._artifacts.setdefault(artifact_id, {"draft": None, "feedback": [], "revisions": []})


_FACADE: YAAMFacade | None = None


def set_facade(facade: YAAMFacade | None) -> None:
    global _FACADE
    _FACADE = facade


def get_facade() -> YAAMFacade:
    global _FACADE
    if _FACADE is None:
        project = (os.getenv("PHOENIX_PROJECT_NAME") or "scm-cognitive-sandwich").strip()
        _FACADE = YAAMFacade(project=project)
    return _FACADE


def _delegate(method: str) -> Callable[..., Any]:
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        facade = get_facade()
        fn = getattr(facade, method)
        return fn(*args, **kwargs)

    return _wrapper


# Backwards-compatible module-level functions used by `src/agents/graph.py`.
artifact_save_draft = _delegate("artifact_save_draft")
artifact_attach_feedback = _delegate("artifact_attach_feedback")
artifact_create_revision = _delegate("artifact_create_revision")
artifact_commit_final = _delegate("artifact_commit_final")
