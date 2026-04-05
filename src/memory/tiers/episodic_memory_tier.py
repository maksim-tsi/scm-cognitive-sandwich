"""
L3: Episodic Memory Tier (YAAM L3) - Qdrant-backed episodic store.

The upstream YAAM implementation supported a dual-index design (Qdrant + Neo4j).
Per RFC-005 and the WinterSim infrastructure audit, this repository intentionally
excludes Neo4j/graph storage engines and focuses on the current target stack:

- L1: Redis
- L2: Postgres
- L3: Qdrant
- L4: Typesense
"""

from __future__ import annotations

import time
import warnings
from typing import Any

from ..metrics import MetricsCollector, OperationTimer
from ..models import Episode, EpisodeStoreInput
from .base_tier import BaseTier, TierOperationError


class EpisodicMemoryTier(BaseTier[Episode]):
    """L3 episodic memory tier.

    This tier is intentionally lightweight: it assumes an injected Qdrant-like
    client/adapter and does not manage embeddings or autonomous consolidation.
    """

    COLLECTION_NAME = "episodes"

    def __init__(
        self,
        qdrant_adapter: Any,
        metrics_collector: MetricsCollector | None = None,
        config: dict[str, Any] | None = None,
        telemetry_stream: Any | None = None,
    ) -> None:
        super().__init__({"qdrant": qdrant_adapter}, metrics_collector, config, telemetry_stream)
        self.qdrant = qdrant_adapter
        self.collection_name = (
            (config or {}).get("collection_name", self.COLLECTION_NAME)
            if config is not None
            else self.COLLECTION_NAME
        )

        if hasattr(self.qdrant, "collection_name"):
            try:
                self.qdrant.collection_name = self.collection_name
            except Exception:
                pass

    def _tier_name(self) -> str:
        return "L3_Episodic"

    async def store(self, data: Episode | EpisodeStoreInput | dict[str, Any]) -> str:
        async with OperationTimer(self.metrics, "l3_store"):
            start_time = time.perf_counter()

            episode: Episode
            if isinstance(data, dict):
                warnings.warn(
                    "Passing dict to EpisodicMemoryTier.store() is deprecated. Use Episode model.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                episode = Episode.model_validate(data)
            elif isinstance(data, EpisodeStoreInput):
                episode = data.episode
            else:
                episode = data

            upsert = getattr(self.qdrant, "upsert", None)
            if callable(upsert):
                await upsert(episode=episode, collection_name=self.collection_name)

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="STORE",
                session_id=episode.session_id,
                status="HIT",
                latency_ms=latency_ms,
                item_count=1,
                metadata={"episode_id": episode.episode_id},
            )

            return episode.episode_id
        raise AssertionError("Unreachable: store should return or raise.")

    async def retrieve(self, identifier: str) -> Episode | None:
        async with OperationTimer(self.metrics, "l3_retrieve"):
            start_time = time.perf_counter()
            get_by_id = getattr(self.qdrant, "get_by_id", None)
            episode: Episode | None = None
            if callable(get_by_id):
                row = await get_by_id(identifier, collection_name=self.collection_name)
                if row is not None:
                    episode = row if isinstance(row, Episode) else Episode.model_validate(row)

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="RETRIEVE",
                session_id=episode.session_id if episode else "unknown",
                status="HIT" if episode else "MISS",
                latency_ms=latency_ms,
                metadata={"episode_id": identifier},
            )
            return episode
        return None

    async def query(
        self, filters: dict[str, Any] | None = None, limit: int = 10, **kwargs: Any
    ) -> list[Episode]:
        async with OperationTimer(self.metrics, "l3_query"):
            search = getattr(self.qdrant, "search", None)
            if not callable(search):
                return []

            rows = await search(
                query=filters or {}, limit=limit, collection_name=self.collection_name, **kwargs
            )
            episodes: list[Episode] = []
            for row in rows or []:
                episodes.append(row if isinstance(row, Episode) else Episode.model_validate(row))
            return episodes
        return []

    async def delete(self, identifier: str) -> bool:
        async with OperationTimer(self.metrics, "l3_delete"):
            delete = getattr(self.qdrant, "delete", None)
            if not callable(delete):
                raise TierOperationError("Qdrant adapter does not support delete operations")
            result = await delete(identifier, collection_name=self.collection_name)
            return bool(result)
        return False

    async def health_check(self) -> dict[str, Any]:
        qdrant_health = {"status": "unknown"}
        health_check = getattr(self.qdrant, "health_check", None)
        if callable(health_check):
            qdrant_health = await health_check()

        status = "healthy" if qdrant_health.get("status") == "healthy" else "degraded"
        return {
            "tier": self._tier_name(),
            "status": status,
            "storage": {"qdrant": qdrant_health},
        }
