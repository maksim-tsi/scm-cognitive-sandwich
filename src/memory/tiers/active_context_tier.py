"""
L1 Active Context Tier - Working Memory Buffer (ADR-003).

This module implements the L1 tier of the four-tier cognitive memory
architecture. It maintains a high-speed buffer of the most recent 10-20
conversational turns per session with automatic TTL expiration.

Architecture:
- Primary: Redis (hot cache for sub-millisecond access)
- Secondary: PostgreSQL (persistent backup for recovery)
- Pattern: Write-through cache with automatic windowing
"""

import json
import logging
import time
import warnings
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.memory.models import TurnData
from src.memory.tiers.base_tier import BaseTier, TierOperationError
from src.storage.base import StorageDataError, validate_required_fields
from src.storage.metrics.collector import MetricsCollector
from src.storage.metrics.timer import OperationTimer
from src.storage.postgres_adapter import PostgresAdapter
from src.storage.redis_adapter import RedisAdapter

logger = logging.getLogger(__name__)


class ActiveContextTier(BaseTier[TurnData]):
    """
    L1: Active Context - Working Memory Buffer.

    Maintains 10-20 most recent conversational turns per session.
    Uses Redis for speed, PostgreSQL for durability.
    Automatic TTL expiration after 24 hours.

    Key Features:
    - Turn windowing: Keeps only N most recent turns
    - TTL management: Auto-expires after 24 hours
    - Write-through cache: Redis (hot) + PostgreSQL (cold)
    - Graceful fallback: Falls back to PostgreSQL if Redis fails
    - Sub-millisecond latency: Target <5ms for retrieve operations

    Usage Example:
        ```python
        tier = ActiveContextTier(
            redis_adapter=redis,
            postgres_adapter=postgres,
            config={'window_size': 20, 'ttl_hours': 24}
        )
        await tier.initialize()

        # Store turn
        turn_id = await tier.store({
            'session_id': 'session-123',
            'turn_id': 'turn-001',
            'role': 'user',
            'content': 'Hello, world!',
            'timestamp': datetime.now(timezone.utc)
        })

        # Retrieve recent turns
        turns = await tier.retrieve('session-123')
        ```
    """

    # Default configuration
    DEFAULT_WINDOW_SIZE = 20
    DEFAULT_TTL_HOURS = 24
    REDIS_KEY_PREFIX = "l1:session:"

    def __init__(
        self,
        redis_adapter: RedisAdapter,
        postgres_adapter: PostgresAdapter,
        metrics_collector: MetricsCollector | None = None,
        config: dict[str, Any] | None = None,
        telemetry_stream: Any | None = None,
    ):
        """
        Initialize L1 Active Context Tier.

        Args:
            redis_adapter: Redis adapter for hot cache
            postgres_adapter: PostgreSQL adapter for persistent storage
            metrics_collector: Optional metrics collector
            config: Optional configuration with keys:
                - window_size: Max turns per session (default: 20)
                - ttl_hours: TTL in hours (default: 24)
                - enable_postgres_backup: Store in PostgreSQL (default: True)
            telemetry_stream: Optional stream for emitting events
        """
        storage_adapters = {"redis": redis_adapter, "postgres": postgres_adapter}
        super().__init__(storage_adapters, metrics_collector, config, telemetry_stream)

        self.redis = redis_adapter
        self.postgres = postgres_adapter
        self.window_size = (
            config.get("window_size", self.DEFAULT_WINDOW_SIZE)
            if config
            else self.DEFAULT_WINDOW_SIZE
        )
        self.ttl_hours = (
            config.get("ttl_hours", self.DEFAULT_TTL_HOURS) if config else self.DEFAULT_TTL_HOURS
        )
        self.enable_postgres_backup = config.get("enable_postgres_backup", True) if config else True

        logger.info(
            f"L1 ActiveContextTier initialized: window_size={self.window_size}, "
            f"ttl_hours={self.ttl_hours}, postgres_backup={self.enable_postgres_backup}"
        )

    def _tier_name(self) -> str:
        """Return tier identifier for telemetry."""
        return "L1_Active"

    async def store(self, data: TurnData | dict[str, Any]) -> str:
        """
        Store a conversational turn in L1.

        Args:
            data: TurnData model or dict (deprecated) with required fields:
                - session_id: str - Session identifier
                - turn_id: str - Unique turn identifier
                - role: str - 'user' or 'assistant'
                - content: str - Turn content
                - timestamp: datetime (optional, defaults to utcnow)
                - metadata: Dict (optional, additional context)

        Returns:
            Unique turn identifier (turn_id)

        Raises:
            TierOperationError: If storage operation fails
            StorageDataError: If required fields are missing
        """
        async with OperationTimer(self.metrics, "l1_store"):
            try:
                turn: TurnData
                if isinstance(data, dict):
                    warnings.warn(
                        "Passing dict to ActiveContextTier.store() is deprecated. "
                        "Use TurnData model directly.",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                    # Validate required fields for dict input
                    required = ["session_id", "turn_id", "role", "content"]
                    validate_required_fields(data, required)
                    turn = TurnData.model_validate(data)
                else:
                    turn = data

                session_id = turn.session_id
                turn_id = turn.turn_id
                timestamp = turn.timestamp

                logger.debug(f"Storing turn {turn_id} in session {session_id}")

                start_time = time.perf_counter()

                # Prepare turn data
                turn_data = {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "role": turn.role,
                    "content": turn.content,
                    "timestamp": timestamp.isoformat()
                    if isinstance(timestamp, datetime)
                    else timestamp,
                    "metadata": turn.metadata,
                }

                # Store in Redis (hot cache)
                redis_key = f"{self.REDIS_KEY_PREFIX}{session_id}"
                turn_json = json.dumps(turn_data)

                # Use Redis list operations for turn window
                # LPUSH: Add to front (most recent)
                await self.redis.lpush(redis_key, turn_json)

                # LTRIM: Keep only window_size most recent turns
                await self.redis.ltrim(redis_key, 0, self.window_size - 1)

                # Set TTL
                ttl_seconds = self.ttl_hours * 3600
                await self.redis.expire(redis_key, ttl_seconds)

                logger.debug(f"Stored turn {turn_id} in Redis with TTL {ttl_seconds}s")

                # Store in PostgreSQL (persistent backup)
                if self.enable_postgres_backup:
                    postgres_data = {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "role": turn.role,
                        "content": turn.content,
                        "timestamp": timestamp,
                        "tier": "L1",
                        "metadata": json.dumps(turn.metadata),
                    }
                    await self.postgres.insert("active_context", postgres_data)
                    logger.debug(f"Stored turn {turn_id} in PostgreSQL backup")

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="STORE",
                    session_id=session_id,
                    status="HIT",
                    latency_ms=latency_ms,
                    item_count=1,
                    metadata={"turn_id": turn_id, "role": turn.role},
                )

                # Metrics are tracked by OperationTimer
                return turn_id

            except ValidationError:
                raise
            except StorageDataError:
                # Re-raise validation errors as-is
                raise
            except Exception as e:
                logger.error(f"Failed to store turn in L1: {e}")
                raise TierOperationError(f"Failed to store turn: {e}") from e
        raise AssertionError("Unreachable: store should return or raise.")

    async def retrieve(self, turn_id: str) -> TurnData | None:
        """
        Retrieve a turn by ID.

        Args:
            turn_id: Turn identifier

        Returns:
            TurnData or None if not found
        """
        async with OperationTimer(self.metrics, "l1_retrieve"):
            start_time = time.perf_counter()
            try:
                logger.debug(f"Retrieving turn {turn_id} from L1")

                if not self.enable_postgres_backup:
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    await self._emit_tier_access(
                        operation="RETRIEVE",
                        session_id="unknown",
                        status="MISS",
                        latency_ms=latency_ms,
                        metadata={"turn_id": turn_id},
                    )
                    return None

                postgres_result = await self.postgres.query(
                    table="active_context",
                    filters={"turn_id": turn_id, "tier": "L1"},
                    limit=1,
                )

                if not postgres_result:
                    logger.debug(f"Turn {turn_id} not found in L1")
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    await self._emit_tier_access(
                        operation="RETRIEVE",
                        session_id="unknown",
                        status="MISS",
                        latency_ms=latency_ms,
                        metadata={"turn_id": turn_id},
                    )
                    return None

                row = postgres_result[0]
                metadata = row.get("metadata", {})
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)

                turn: TurnData = TurnData.model_validate(
                    {
                        "turn_id": row["turn_id"],
                        "session_id": row["session_id"],
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"],
                        "metadata": metadata,
                    }
                )

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="RETRIEVE",
                    session_id=turn.session_id,
                    status="HIT",
                    latency_ms=latency_ms,
                    item_count=1,
                    metadata={"turn_id": turn_id},
                )

                return turn

            except Exception as e:
                logger.error(f"Failed to retrieve turn from L1: {e}")
                raise TierOperationError(f"Failed to retrieve turn: {e}") from e
        raise AssertionError("Unreachable: retrieve should return or raise.")

    async def retrieve_session(self, session_id: str) -> list[TurnData] | None:
        """
        Retrieve recent turns for a session.

        Implements hot/cold cache pattern:
        1. Try Redis first (hot path - fast)
        2. Fallback to PostgreSQL (cold path - slower)
        3. Rebuild Redis cache if found in PostgreSQL

        Args:
            session_id: Session identifier

        Returns:
            List of recent turns (newest first) or None if not found
        """
        async with OperationTimer(self.metrics, "l1_retrieve_session"):
            start_time = time.perf_counter()
            try:
                redis_key = f"{self.REDIS_KEY_PREFIX}{session_id}"

                logger.debug(f"Retrieving turns for session {session_id}")

                # Try Redis first (hot path)
                try:
                    turns_json = await self.redis.lrange(redis_key, 0, -1)
                    if turns_json:
                        turns = []
                        for turn_json in turns_json:
                            turn_payload = json.loads(turn_json)
                            if "session_id" not in turn_payload:
                                turn_payload["session_id"] = session_id
                            turns.append(TurnData.model_validate(turn_payload))
                        logger.debug(f"Retrieved {len(turns)} turns from Redis (hot)")

                        latency_ms = (time.perf_counter() - start_time) * 1000
                        await self._emit_tier_access(
                            operation="QUERY",
                            session_id=session_id,
                            status="HIT",
                            latency_ms=latency_ms,
                            item_count=len(turns),
                            metadata={"source": "redis"},
                        )
                        return turns
                except Exception as redis_error:
                    logger.warning(
                        f"Redis retrieval failed: {redis_error}, falling back to PostgreSQL"
                    )

                # Fallback to PostgreSQL (cold path)
                if self.enable_postgres_backup:
                    logger.debug(f"Attempting PostgreSQL fallback for session {session_id}")
                    postgres_result = await self.postgres.query(
                        table="active_context",
                        filters={"session_id": session_id, "tier": "L1"},
                        order_by="timestamp DESC",
                        limit=self.window_size,
                    )

                    if postgres_result:
                        logger.info(
                            f"Retrieved {len(postgres_result)} turns from PostgreSQL (cold)"
                        )

                        turns = []
                        for row in postgres_result:
                            metadata = row.get("metadata", {})
                            if isinstance(metadata, str):
                                metadata = json.loads(metadata)
                            turns.append(
                                TurnData.model_validate(
                                    {
                                        "turn_id": row["turn_id"],
                                        "session_id": row["session_id"],
                                        "role": row["role"],
                                        "content": row["content"],
                                        "timestamp": row["timestamp"],
                                        "metadata": metadata,
                                    }
                                )
                            )

                        # Rebuild Redis cache
                        try:
                            for turn in reversed(turns):
                                turn_data = turn.model_dump(mode="json")
                                await self.redis.lpush(redis_key, json.dumps(turn_data))

                            # Set TTL
                            ttl_seconds = self.ttl_hours * 3600
                            await self.redis.expire(redis_key, ttl_seconds)

                            logger.debug(f"Rebuilt Redis cache for session {session_id}")
                        except Exception as rebuild_error:
                            logger.warning(f"Failed to rebuild Redis cache: {rebuild_error}")

                        latency_ms = (time.perf_counter() - start_time) * 1000
                        await self._emit_tier_access(
                            operation="QUERY",
                            session_id=session_id,
                            status="HIT",
                            latency_ms=latency_ms,
                            item_count=len(turns),
                            metadata={"source": "postgres"},
                        )
                        return turns

                # Not found in either storage
                logger.debug(f"Session {session_id} not found in L1")
                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="QUERY",
                    session_id=session_id,
                    status="MISS",
                    latency_ms=latency_ms,
                )
                return None

            except Exception as e:
                logger.error(f"Failed to retrieve session from L1: {e}")
                raise TierOperationError(f"Failed to retrieve session: {e}") from e
        raise AssertionError("Unreachable: retrieve_session should return or raise.")

    async def query(
        self, filters: dict[str, Any] | None = None, limit: int = 10, **kwargs: Any
    ) -> list[TurnData]:
        """
        Query turns with filters.

        L1 queries always go to PostgreSQL for flexibility as they are
        typically used for administrative operations, not hot path retrieval.

        Args:
            filters: Query filters:
                - session_id: str (optional)
                - role: str (optional, 'user' or 'assistant')
                - timestamp_after: datetime (optional)
                - timestamp_before: datetime (optional)
            limit: Maximum results
            **kwargs: Additional query parameters

        Returns:
            List of matching turns (newest first)
        """
        async with OperationTimer(self.metrics, "l1_query"):
            try:
                # Add L1 tier filter
                query_filters = {**(filters or {}), "tier": "L1"}

                result = await self.postgres.query(
                    table="active_context",
                    filters=query_filters,
                    order_by="timestamp DESC",
                    limit=limit,
                )

                turns = []
                for row in result:
                    metadata = row.get("metadata", {})
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    turns.append(
                        TurnData.model_validate(
                            {
                                "turn_id": row["turn_id"],
                                "session_id": row["session_id"],
                                "role": row["role"],
                                "content": row["content"],
                                "timestamp": row["timestamp"],
                                "metadata": metadata,
                            }
                        )
                    )

                logger.debug(f"Query returned {len(turns)} turns")
                return turns

            except Exception as e:
                logger.error(f"Failed to query L1: {e}")
                raise TierOperationError(f"Failed to query L1: {e}") from e
        raise AssertionError("Unreachable: query should return or raise.")

    async def delete(self, session_id: str) -> bool:
        """
        Delete session from L1.

        Removes session from both Redis and PostgreSQL.

        Args:
            session_id: Session to delete

        Returns:
            True if deleted, False if not found
        """
        async with OperationTimer(self.metrics, "l1_delete"):
            start_time = time.perf_counter()
            try:
                redis_key = f"{self.REDIS_KEY_PREFIX}{session_id}"
                deleted = False

                # Delete from Redis
                try:
                    redis_result = await self.redis.delete(redis_key)
                    if redis_result:
                        deleted = True
                        logger.debug(f"Deleted session {session_id} from Redis")
                except Exception as redis_error:
                    logger.warning(f"Redis deletion failed: {redis_error}")

                # Delete from PostgreSQL
                if self.enable_postgres_backup:
                    if isinstance(self.postgres, PostgresAdapter):
                        postgres_result = await self.postgres.delete_by_filters(
                            "active_context",
                            filters={"session_id": session_id, "tier": "L1"},
                        )
                    else:
                        postgres_result = await self.postgres.delete(session_id)

                    if bool(postgres_result):
                        deleted = True
                        logger.debug(f"Deleted session {session_id} from PostgreSQL")

                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="DELETE",
                    session_id=session_id,
                    status="HIT" if deleted else "MISS",
                    latency_ms=latency_ms,
                )

                return deleted

            except Exception as e:
                logger.error(f"Failed to delete session from L1: {e}")
                raise TierOperationError(f"Failed to delete session: {e}") from e
        raise AssertionError("Unreachable: delete should return or raise.")

    async def get_window_size(self, session_id: str) -> int:
        """
        Get current window size (number of turns) for a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of turns currently stored
        """
        try:
            redis_key = f"{self.REDIS_KEY_PREFIX}{session_id}"
            size = await self.redis.llen(redis_key)
            return size
        except Exception as e:
            logger.error(f"Failed to get window size: {e}")
            return 0

    async def health_check(self) -> dict[str, Any]:
        """
        Check health of Redis and PostgreSQL.

        Returns:
            Health status with per-adapter details
        """
        try:
            redis_health = await self.redis.health_check()
            postgres_health = await self.postgres.health_check()

            # Overall status is healthy only if both are healthy
            overall_status = (
                "healthy"
                if (
                    redis_health.get("status") == "healthy"
                    and postgres_health.get("status") == "healthy"
                )
                else "degraded"
            )

            return {
                "tier": "L1_active_context",
                "status": overall_status,
                "timestamp": datetime.now(UTC).isoformat(),
                "storage": {"redis": redis_health, "postgres": postgres_health},
                "config": {
                    "window_size": self.window_size,
                    "ttl_hours": self.ttl_hours,
                    "postgres_backup_enabled": self.enable_postgres_backup,
                },
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "tier": "L1_active_context",
                "status": "unhealthy",
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
            }
