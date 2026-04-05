"""
L2: Working Memory Tier - Significance-Filtered Fact Storage (ADR-003).

This module implements the L2 tier of the four-tier cognitive memory
architecture. It stores facts extracted from L1 that exceed the CIAR
significance threshold (default: 0.6).

Key Features:
- CIAR-based significance filtering
- Access pattern tracking with recency boost
- Automatic age decay calculation
- Fact type classification
- TTL-based cleanup (7 days default)
"""

import json
import logging
import time
import warnings
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from ..ciar_formula import (
    DEFAULT_AGE_DECAY_LAMBDA,
    DEFAULT_RECENCY_ALPHA,
    calculate_ciar_score,
)
from ..metrics import MetricsCollector, OperationTimer
from ..models import Fact, FactType
from .base_tier import BaseTier, TierOperationError

logger = logging.getLogger(__name__)


class WorkingMemoryTier(BaseTier[Fact]):
    """
    L2: Working Memory - CIAR-Scored Fact Storage.

    Manages significant facts with CIAR scoring and access tracking.
    Facts are promoted from L1 based on significance threshold.
    Only stores facts with CIAR score >= threshold (default 0.6).

    Key Features:
    - CIAR threshold enforcement (configurable, default: 0.6)
    - Access tracking with automatic recency boost updates
    - Age decay calculation
    - TTL-based cleanup (7 days default)
    - Query by CIAR score, type, category, session

    Usage Example:
        ```python
        tier = WorkingMemoryTier(
            postgres_adapter=postgres,
            config={'ciar_threshold': 0.6, 'ttl_days': 7}
        )
        await tier.initialize()

        # Store significant fact
        fact_id = await tier.store({
            'fact_id': 'fact-001',
            'session_id': 'session-123',
            'content': 'User prefers async communication',
            'ciar_score': 0.75,
            'certainty': 0.85,
            'impact': 0.90,
            'fact_type': 'preference'
        })

        # Query by session
        facts = await tier.query_by_session('session-123')
        ```
    """

    # Configuration defaults
    DEFAULT_CIAR_THRESHOLD = 0.6
    DEFAULT_TTL_DAYS = 7
    RECENCY_BOOST_ALPHA = DEFAULT_RECENCY_ALPHA
    AGE_DECAY_LAMBDA = DEFAULT_AGE_DECAY_LAMBDA

    def __init__(
        self,
        postgres_adapter: Any,
        metrics_collector: MetricsCollector | None = None,
        config: dict[str, Any] | None = None,
        telemetry_stream: Any | None = None,
    ):
        """
        Initialize L2 Working Memory Tier.

        Args:
            postgres_adapter: PostgreSQL adapter for persistent storage
            metrics_collector: Optional metrics collector
            config: Optional configuration with keys:
                - ciar_threshold: Minimum CIAR score (default: 0.6)
                - ttl_days: TTL in days (default: 7)
                - recency_boost_alpha: Boost factor per access (default: 0.1)
                - age_decay_lambda: Decay rate per day (default: 0.0231)
            telemetry_stream: Optional stream for emitting events
        """
        storage_adapters = {"postgres": postgres_adapter}
        super().__init__(storage_adapters, metrics_collector, config, telemetry_stream)

        self.postgres = postgres_adapter
        # Ensure adapter targets the working_memory table for all operations
        self.postgres.table = "working_memory"
        self.ciar_threshold = (
            config.get("ciar_threshold", self.DEFAULT_CIAR_THRESHOLD)
            if config
            else self.DEFAULT_CIAR_THRESHOLD
        )
        self.ttl_days = (
            config.get("ttl_days", self.DEFAULT_TTL_DAYS) if config else self.DEFAULT_TTL_DAYS
        )
        self.recency_boost_alpha = (
            config.get("recency_boost_alpha", self.RECENCY_BOOST_ALPHA)
            if config
            else self.RECENCY_BOOST_ALPHA
        )
        self.age_decay_lambda = (
            config.get("age_decay_lambda", self.AGE_DECAY_LAMBDA)
            if config
            else self.AGE_DECAY_LAMBDA
        )
        self.cache_limit = config.get("cache_limit", 200) if config else 200
        self._recent_cache: dict[str, deque[Fact]] = {}

        logger.info(
            f"L2 WorkingMemoryTier initialized: ciar_threshold={self.ciar_threshold}, "
            f"ttl_days={self.ttl_days}"
        )

    def _tier_name(self) -> str:
        """Return tier identifier for telemetry."""
        return "L2_Working"

    async def store(self, data: Fact | dict[str, Any]) -> str:
        """
        Store a fact in L2 Working Memory.

        Only stores facts that meet the CIAR threshold requirement.

        Args:
            data: Fact model or dict (deprecated) with required fields:
                - fact_id: str - Unique identifier
                - session_id: str - Session identifier
                - content: str - Fact content
                - ciar_score: float - CIAR significance score
                Optional: certainty, impact, fact_type, metadata, etc.

        Returns:
            Fact identifier

        Raises:
            TierOperationError: If storage fails
            StorageDataError: If required fields missing
            ValueError: If CIAR score below threshold
        """
        async with OperationTimer(self.metrics, "l2_store"):
            try:
                # Convert to Fact model for validation
                fact: Fact
                if isinstance(data, dict):
                    warnings.warn(
                        "Passing dict to WorkingMemoryTier.store() is deprecated. "
                        "Use Fact model directly.",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                    fact = Fact.model_validate(data)
                else:
                    fact = data

                start_time = time.perf_counter()

                # Check CIAR threshold
                if fact.ciar_score < self.ciar_threshold:
                    logger.debug(
                        f"Fact {fact.fact_id} rejected: CIAR {fact.ciar_score} < "
                        f"threshold {self.ciar_threshold}"
                    )
                    raise ValueError(
                        f"Fact CIAR score {fact.ciar_score} below threshold {self.ciar_threshold}"
                    )

                logger.debug(
                    f"Storing fact {fact.fact_id} with CIAR {fact.ciar_score} "
                    f"(certainty={fact.certainty}, impact={fact.impact})"
                )

                # Store in PostgreSQL
                await self.postgres.insert("working_memory", fact.to_db_dict())

                self._cache_fact(fact)
                logger.debug(f"Fact {fact.fact_id} stored successfully in L2")

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="STORE",
                    session_id=fact.session_id,
                    status="HIT",
                    latency_ms=latency_ms,
                    item_count=1,
                    metadata={
                        "fact_id": fact.fact_id,
                        "fact_type": fact.fact_type,
                        "ciar_score": fact.ciar_score,
                    },
                )

                return fact.fact_id

            except ValidationError:
                raise
            except ValueError:
                # Re-raise CIAR threshold errors
                raise
            except Exception as e:
                logger.error(f"Failed to store fact in L2: {e}")
                raise TierOperationError(f"Failed to store fact: {e}") from e
        raise AssertionError("Unreachable: store should return or raise.")

    def _cache_fact(self, fact: Fact) -> None:
        """Keep a small recent fact buffer per session for fast retrieval."""
        cache = self._recent_cache.setdefault(fact.session_id, deque(maxlen=self.cache_limit))
        cache.append(fact)

    def get_recent_cached(self, session_id: str) -> list[Fact]:
        """Return recently stored facts for a session (in-process cache)."""
        return list(self._recent_cache.get(session_id, []))

    async def retrieve(self, fact_id: str) -> Fact | None:
        """
        Retrieve a fact by ID and update access tracking.

        Automatically updates:
        - last_accessed timestamp
        - access_count (incremented)
        - recency_boost (recalculated)
        - ciar_score (recalculated with new recency_boost)

        Args:
            fact_id: Unique fact identifier

        Returns:
            Fact object or None if not found
        """
        async with OperationTimer(self.metrics, "l2_retrieve"):
            start_time = time.perf_counter()
            try:
                result = await self.postgres.query(
                    table="working_memory", filters={"fact_id": fact_id}, limit=1
                )

                if not result:
                    logger.debug(f"Fact {fact_id} not found in L2")
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    await self._emit_tier_access(
                        operation="RETRIEVE",
                        session_id="unknown",
                        status="MISS",
                        latency_ms=latency_ms,
                        metadata={"fact_id": fact_id},
                    )
                    return None

                # Convert to Fact model
                fact_data = result[0]
                # Parse metadata if it's a string
                if isinstance(fact_data.get("metadata"), str):
                    fact_data["metadata"] = json.loads(fact_data["metadata"])

                # Backfill fact_id when underlying storage returns generic id
                if "fact_id" not in fact_data and "id" in fact_data:
                    fact_data["fact_id"] = str(fact_data["id"])

                fact = Fact(**fact_data)

                # Update access tracking
                await self._update_access_tracking(fact)

                logger.debug(
                    f"Retrieved fact {fact_id} (access_count={fact.access_count}, "
                    f"CIAR={fact.ciar_score})"
                )

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="RETRIEVE",
                    session_id=fact.session_id,
                    status="HIT",
                    latency_ms=latency_ms,
                    item_count=1,
                    metadata={
                        "fact_id": fact.fact_id,
                        "fact_type": fact.fact_type,
                        "ciar_score": fact.ciar_score,
                    },
                )
                return fact

            except Exception as e:
                logger.error(f"Failed to retrieve fact from L2: {e}")
                raise TierOperationError(f"Failed to retrieve fact: {e}") from e
        raise AssertionError("Unreachable: retrieve should return or raise.")

    async def query(
        self, filters: dict[str, Any] | None = None, limit: int = 10, **kwargs: Any
    ) -> list[Fact]:
        """
        Query facts with optional filters.

        Args:
            filters: Query filters (all optional):
                - session_id: str - Filter by session
                - min_ciar_score: float - Minimum CIAR threshold
                - fact_type: str - Filter by fact type
                - fact_category: str - Filter by category
                - extracted_after: datetime - Facts after date
                - extracted_before: datetime - Facts before date
            limit: Maximum results (default: 10)
            **kwargs: Additional parameters:
                - order_by: str (default: 'ciar_score DESC, last_accessed DESC')
                - include_low_ciar: bool (default: False)

        Returns:
            List of matching facts (newest/highest CIAR first)
        """
        async with OperationTimer(self.metrics, "l2_query"):
            start_time = time.perf_counter()
            try:
                # Build query filters
                query_filters = filters.copy() if filters else {}

                # Enforce CIAR threshold unless explicitly disabled
                if not kwargs.get("include_low_ciar", False):
                    min_ciar = query_filters.pop("min_ciar_score", self.ciar_threshold)
                    # Note: postgres adapter needs to support __gte suffix
                    # For now, we'll filter in-memory
                    query_filters["tier"] = "L2"

                # Query PostgreSQL
                order_by = kwargs.get("order_by", "ciar_score DESC, last_accessed DESC")
                results = await self.postgres.query(
                    table="working_memory",
                    filters=query_filters,
                    order_by=order_by,
                    limit=limit * 2,  # Query more to allow for filtering
                )

                # Convert to Fact objects and filter by CIAR if needed
                facts = []
                min_ciar = (
                    filters.get("min_ciar_score", self.ciar_threshold)
                    if filters
                    else self.ciar_threshold
                )

                for row in results:
                    if isinstance(row.get("metadata"), str):
                        row["metadata"] = json.loads(row["metadata"])

                    # Backfill fact_id when underlying storage returns generic id
                    if "fact_id" not in row and "id" in row:
                        row["fact_id"] = str(row["id"])

                    fact = Fact(**row)

                    # Some storage adapters omit CIAR components; ensure we don't
                    # filter out facts purely due to missing scores.
                    if row.get("ciar_score") is None:
                        fact.ciar_score = max(fact.ciar_score, self.ciar_threshold)

                    # Apply CIAR filter
                    if not kwargs.get("include_low_ciar", False) and fact.ciar_score < min_ciar:
                        continue

                    facts.append(fact)

                    if len(facts) >= limit:
                        break

                logger.debug(f"Query returned {len(facts)} facts")

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="QUERY",
                    session_id=filters.get("session_id", "unknown") if filters else "unknown",
                    status="HIT",
                    latency_ms=latency_ms,
                    item_count=len(facts),
                    metadata={
                        "filters": str(filters)[:100] if filters else None,
                        "min_ciar": min_ciar,
                    },
                )
                return facts

            except Exception as e:
                logger.error(f"Failed to query L2: {e}")
                raise TierOperationError(f"Failed to query L2: {e}") from e
        raise AssertionError("Unreachable: query should return or raise.")

    async def query_by_session(
        self, session_id: str, min_ciar_score: float | None = None, limit: int = 100
    ) -> list[Fact]:
        """
        Query facts for a specific session.

        Args:
            session_id: Session identifier
            min_ciar_score: Minimum CIAR threshold (default: tier threshold)
            limit: Maximum results (default: 100 to support consolidation)

        Returns:
            List of facts ordered by CIAR score descending
        """
        filters = {
            "session_id": session_id,
            "min_ciar_score": min_ciar_score or self.ciar_threshold,
        }
        return await self.query(filters=filters, limit=limit)

    async def query_by_type(
        self, fact_type: FactType, session_id: str | None = None, limit: int = 100
    ) -> list[Fact]:
        """
        Query facts by type.

        Args:
            fact_type: Type of fact to retrieve
            session_id: Optional session filter
            limit: Maximum results (default: 100)

        Returns:
            List of matching facts
        """
        filters = {"fact_type": fact_type.value}
        if session_id:
            filters["session_id"] = session_id

        return await self.query(filters=filters, limit=limit)

    async def search_facts(
        self, query: str, session_id: str, min_ciar: float | None = None, limit: int = 20
    ) -> list[Fact]:
        """
        Full-text search for facts using PostgreSQL tsvector.

        Uses 'simple' language config (no stemming) for exact keyword/entity
        matching, ideal for SKUs, container IDs, error codes, and polyglot content.

        This is L2's lightweight alternative to vector search - fast keyword
        lookup for working memory without external API calls or embeddings.

        Args:
            query: Search query string (e.g., "MAEU1234567", "Port of Los Angeles")
            session_id: Session identifier to scope search
            min_ciar: Minimum CIAR score threshold (default: tier threshold)
            limit: Maximum results (default: 20)

        Returns:
            List of matching facts ordered by relevance (ts_rank) DESC, then CIAR DESC

        Example:
            ```python
            # Search for container ID in current session
            facts = await tier.search_facts(
                query="MAEU1234567",
                session_id="session-123",
                min_ciar=0.6,
                limit=10
            )
            ```
        """
        async with OperationTimer(self.metrics, "l2_search_facts"):
            start_time = time.perf_counter()
            try:
                min_ciar_threshold = min_ciar if min_ciar is not None else self.ciar_threshold

                # Build PostgreSQL full-text search query
                # Using plainto_tsquery for simple natural language queries
                sql = """
                    SELECT *,
                        ts_rank(content_tsv, plainto_tsquery('simple', %s)) as rank
                    FROM working_memory
                    WHERE session_id = %s
                        AND ciar_score >= %s
                        AND (ttl_expires_at IS NULL OR ttl_expires_at > NOW())
                        AND content_tsv @@ plainto_tsquery('simple', %s)
                    ORDER BY rank DESC, ciar_score DESC, last_accessed DESC
                    LIMIT %s
                """

                results = await self.postgres.execute(
                    sql, query, session_id, min_ciar_threshold, query, limit
                )

                facts = []
                for row in results:
                    # Remove the 'rank' field before creating Fact model
                    fact_data = dict(row)
                    fact_data.pop("rank", None)
                    fact_data.pop("content_tsv", None)  # Remove tsvector field

                    # Parse metadata if it's a string
                    if isinstance(fact_data.get("metadata"), str):
                        fact_data["metadata"] = json.loads(fact_data["metadata"])

                    # Backfill fact_id when underlying storage returns generic id
                    if "fact_id" not in fact_data and "id" in fact_data:
                        fact_data["fact_id"] = str(fact_data["id"])

                    facts.append(Fact(**fact_data))

                logger.info(
                    f"L2 search found {len(facts)} facts for query '{query}' "
                    f"(session={session_id}, min_ciar={min_ciar_threshold})"
                )

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="QUERY",
                    session_id=session_id,
                    status="HIT",
                    latency_ms=latency_ms,
                    item_count=len(facts),
                    metadata={
                        "query": query[:50],
                        "min_ciar": min_ciar_threshold,
                    },
                )

                return facts

            except Exception as e:
                logger.error(f"Failed to search facts in L2: {e}")
                raise TierOperationError(f"Failed to search facts: {e}") from e
        raise AssertionError("Unreachable: search_facts should return or raise.")

    async def update_ciar_score(
        self, fact_id: str, ciar_score: float | None = None, **components: float
    ) -> bool:
        """
        Update CIAR score and/or components.

        If individual components are provided, CIAR score is recalculated.

        Args:
            fact_id: Fact to update
            ciar_score: New CIAR score (optional if components provided)
            **components: Optional individual components:
                - certainty: float
                - impact: float
                - age_decay: float
                - recency_boost: float

        Returns:
            True if updated
        """
        try:
            update_data = {}

            # If components provided, recalculate CIAR
            if components:
                # First get current fact to merge components
                current = await self.retrieve(fact_id)
                if not current:
                    return False

                certainty = components.get("certainty", current.certainty)
                impact = components.get("impact", current.impact)
                age_decay = components.get("age_decay", current.age_decay)
                recency_boost = components.get("recency_boost", current.recency_boost)

                calculated_ciar = calculate_ciar_score(certainty, impact, age_decay, recency_boost)

                update_data["certainty"] = certainty
                update_data["impact"] = impact
                update_data["age_decay"] = age_decay
                update_data["recency_boost"] = recency_boost
                update_data["ciar_score"] = round(calculated_ciar, 4)
            elif ciar_score is not None:
                update_data["ciar_score"] = ciar_score

            if not update_data:
                return False

            await self.postgres.update(
                "working_memory", filters={"fact_id": fact_id}, data=update_data
            )

            logger.debug(f"Updated CIAR score for fact {fact_id}: {update_data}")
            return True

        except Exception as e:
            logger.error(f"Failed to update CIAR score: {e}")
            raise TierOperationError(f"Failed to update CIAR score: {e}") from e
        raise AssertionError("Unreachable: update_ciar_score should return or raise.")

    async def delete(self, fact_id: str) -> bool:
        """
        Delete a fact from L2.

        Args:
            fact_id: Fact identifier

        Returns:
            True if deleted, False if not found
        """
        async with OperationTimer(self.metrics, "l2_delete"):
            start_time = time.perf_counter()
            try:
                delete_by_filters = getattr(self.postgres, "delete_by_filters", None)
                if callable(delete_by_filters):
                    result = await delete_by_filters("working_memory", filters={"fact_id": fact_id})
                else:
                    delete = getattr(self.postgres, "delete", None)
                    if not callable(delete):
                        raise TierOperationError("Postgres adapter does not support delete operations")
                    result = await delete(fact_id)

                result = bool(result)

                if result:
                    logger.debug(f"Deleted fact {fact_id} from L2")
                else:
                    logger.debug(f"Fact {fact_id} not found for deletion")

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="DELETE",
                    session_id="unknown",
                    status="HIT" if result else "MISS",
                    latency_ms=latency_ms,
                    metadata={"fact_id": fact_id},
                )

                return result

            except Exception as e:
                logger.error(f"Failed to delete fact from L2: {e}")
                raise TierOperationError(f"Failed to delete fact: {e}") from e
        raise AssertionError("Unreachable: delete should return or raise.")

    async def cleanup_expired(self) -> int:
        """
        Clean up facts older than TTL.

        Returns:
            Number of facts deleted
        """
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=self.ttl_days)

            # Query expired facts
            results = await self.postgres.query(
                table="working_memory",
                filters={},  # Would need extracted_at filter support
                order_by="extracted_at ASC",
                limit=1000,
            )

            deleted_count = 0
            for row in results:
                fact = Fact(**row)
                if fact.extracted_at < cutoff_date:
                    await self.delete(fact.fact_id)
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired facts from L2")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired facts: {e}")
            return 0

    async def health_check(self) -> dict[str, Any]:
        """
        Check health of PostgreSQL and L2 tier statistics.

        Returns:
            Health status with tier statistics
        """
        try:
            postgres_health = await self.postgres.health_check()

            # Get tier statistics
            try:
                all_facts = await self.postgres.query(
                    table="working_memory", filters={}, limit=10000
                )

                total_facts = len(all_facts)
                high_ciar_facts = sum(
                    1 for f in all_facts if f.get("ciar_score", 0) >= self.ciar_threshold
                )
                avg_ciar = (
                    sum(f.get("ciar_score", 0) for f in all_facts) / total_facts
                    if total_facts > 0
                    else 0
                )

            except Exception:
                total_facts = -1
                high_ciar_facts = -1
                avg_ciar = 0

            overall_status = "healthy" if postgres_health.get("status") == "healthy" else "degraded"

            return {
                "tier": "L2_working_memory",
                "status": overall_status,
                "timestamp": datetime.now(UTC).isoformat(),
                "storage": {"postgres": postgres_health},
                "statistics": {
                    "total_facts": total_facts,
                    "high_ciar_facts": high_ciar_facts,
                    "average_ciar_score": round(avg_ciar, 4),
                },
                "config": {
                    "ciar_threshold": self.ciar_threshold,
                    "ttl_days": self.ttl_days,
                    "recency_boost_alpha": self.recency_boost_alpha,
                    "age_decay_lambda": self.age_decay_lambda,
                },
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "tier": "L2_working_memory",
                "status": "unhealthy",
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
            }

    async def _update_access_tracking(self, fact: Fact) -> None:
        """
        Update access tracking for a fact.

        Updates:
        - last_accessed timestamp
        - access_count
        - recency_boost (based on access count)
        - ciar_score (recalculated with new recency_boost)
        """
        try:
            # Update fact object
            fact.mark_accessed(alpha=self.recency_boost_alpha)

            # Update in database
            await self.postgres.update(
                "working_memory",
                filters={"fact_id": fact.fact_id},
                data={
                    "last_accessed": fact.last_accessed,
                    "access_count": fact.access_count,
                    "recency_boost": round(fact.recency_boost, 4),
                    "ciar_score": round(fact.ciar_score, 4),
                },
            )

            logger.debug(
                f"Updated access tracking for {fact.fact_id}: "
                f"count={fact.access_count}, boost={fact.recency_boost:.4f}"
            )

        except Exception as e:
            logger.warning(f"Failed to update access tracking: {e}")
            # Don't fail the retrieve operation if tracking update fails
