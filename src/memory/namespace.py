"""
Redis namespace management with Hash Tag patterns for Cluster safety.

This module provides centralized key generation for the MAS Memory Layer,
ensuring Redis Cluster compatibility through Hash Tags. Hash Tags guarantee
that related keys colocate to the same cluster slot, enabling atomic
MULTI/EXEC and Lua script operations across multiple keys.

Hash Tag Format:
- Session keys: {session:ID}:resource  (e.g., "{session:abc123}:turns")
- Global keys:  {mas}:resource         (e.g., "{mas}:lifecycle")

The substring within braces {} is used for CRC16 slot calculation. All keys
with the same Hash Tag value are guaranteed to reside on the same Redis node.

Key Design Patterns:
1. L1 Active Context:    {session:ID}:turns  (list of raw turns)
2. Personal State:       {session:ID}:agent:AGENT_ID:state
3. Shared Workspace:     {session:ID}:workspace
4. Lifecycle Stream:     {mas}:lifecycle (single global stream)

Performance Implications:
- Hash Tags enable server-side Lua atomicity (eliminates 90% of WATCH retries)
- All session operations can use MULTI/EXEC without CROSSSLOT errors
- Global stream is fire-and-forget (non-atomic with session state)

References:
- ADR-003: Four-Tier Memory Architecture
- ADR-007: LangGraph Integration Architecture
- docs/research/redis-global-local-stream.md
- docs/research/consolidation-hooks-and-signals.md
"""

import binascii
import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class NamespaceManager:
    """
    Redis namespace manager with Hash Tag support for Cluster safety.

    All key generation methods are static to enable usage without instantiation.
    For lifecycle event publishing, instantiate with a Redis client.
    """

    # --- L1: Active Context (Session-Scoped) ---

    @staticmethod
    def l1_turns(session_id: str) -> str:
        """
        Generate key for L1 conversation turns (raw conversation history).

        Args:
            session_id: Unique session identifier

        Returns:
            Redis key with Hash Tag: {session:ID}:turns

        Example:
            key = NamespaceManager.l1_turns("abc123")
            # Returns: "{session:abc123}:turns"
        """
        return f"{{session:{session_id}}}:turns"

    @staticmethod
    def personal_state(agent_id: str, session_id: str) -> str:
        """
        Generate key for agent personal state (scratchpad memory).

        Args:
            agent_id: Unique agent identifier
            session_id: Unique session identifier

        Returns:
            Redis key with Hash Tag: {session:ID}:agent:AGENT_ID:state

        Example:
            key = NamespaceManager.personal_state("agent-1", "abc123")
            # Returns: "{session:abc123}:agent:agent-1:state"
        """
        return f"{{session:{session_id}}}:agent:{agent_id}:state"

    @staticmethod
    def shared_workspace(session_id: str) -> str:
        """
        Generate key for shared workspace (multi-agent collaboration space).

        Args:
            session_id: Unique session identifier

        Returns:
            Redis key with Hash Tag: {session:ID}:workspace

        Example:
            key = NamespaceManager.shared_workspace("abc123")
            # Returns: "{session:abc123}:workspace"
        """
        return f"{{session:{session_id}}}:workspace"

    # --- L2: Working Memory (Session-Scoped) ---

    @staticmethod
    def l2_facts_index(session_id: str) -> str:
        """
        Generate key for L2 fact ID index (Set of fact IDs for O(1) lookup).

        Args:
            session_id: Unique session identifier

        Returns:
            Redis key with Hash Tag: {session:ID}:facts:index

        Example:
            key = NamespaceManager.l2_facts_index("abc123")
            # Returns: "{session:abc123}:facts:index"
        """
        return f"{{session:{session_id}}}:facts:index"

    # --- Global Resources (System-Scoped) ---

    @staticmethod
    def lifecycle_stream() -> str:
        """
        Generate key for global lifecycle event stream.

        This is a single global stream for ALL sessions. Uses {mas} Hash Tag
        to pin to a deterministic cluster slot, preventing CROSSSLOT errors
        with other system-level keys.

        Returns:
            Redis key with Hash Tag: {mas}:lifecycle

        Example:
            key = NamespaceManager.lifecycle_stream()
            # Returns: "{mas}:lifecycle"

        Note:
            Global stream is NOT atomic with session state updates. This is
            acceptable because lifecycle events are async side effects, and
            the Wake-Up Sweep (consolidation_engine.py) provides eventual
            consistency by catching missed events.
        """
        return "{mas}:lifecycle"

    # --- Lifecycle Event Publishing (Requires Redis Client) ---

    def __init__(self, redis_client: redis.Redis | None = None):
        """
        Initialize namespace manager with optional Redis client for publishing.

        Args:
            redis_client: Async Redis client (required for publish_lifecycle_event)
        """
        self.redis = redis_client

    @staticmethod
    def compute_slot(key: str) -> int:
        """Compute Redis Cluster slot for a key using CRC16 (XMODEM)."""
        return binascii.crc_hqx(key.encode(), 0) % 16384

    async def publish_lifecycle_event(
        self,
        event_type: str,
        session_id: str,
        data: dict[str, Any],
        max_length: int = 50000,
    ) -> str:
        """
        Publish a lifecycle event to the global stream with MAXLEN retention.

        Uses fire-and-forget pattern (non-atomic with session state). Stream
        is trimmed automatically at ~50,000 entries (25-50MB RAM) to protect
        Node 1 memory during burst traffic (50 ops/s x 15 min = 45k events).

        Args:
            event_type: Event type (e.g., "promotion", "consolidation", "session_end")
            session_id: Session ID that triggered the event
            data: Event payload (must be JSON-serializable)
            max_length: Maximum stream length (default: 50000)

        Returns:
            Event ID from Redis XADD (format: "{timestamp}-{sequence}")

        Raises:
            ValueError: If redis_client is not configured
            redis.RedisError: If stream write fails

        Example:
            manager = NamespaceManager(redis_client)
            event_id = await manager.publish_lifecycle_event(
                event_type="promotion",
                session_id="abc123",
                data={"fact_count": 5, "ciar_threshold": 0.6}
            )

        Notes:
            - Uses MAXLEN ~ 50000 (approximate trimming) for performance
            - Stream trimming is lazy (happens on macro-node boundaries)
            - Wake-Up Sweep catches missed events if stream write fails
            - See: docs/research/redis-stream-retention-policy.md
        """
        if self.redis is None:
            raise ValueError(
                "NamespaceManager requires redis_client for publish_lifecycle_event. "
                "Initialize with NamespaceManager(redis_client)."
            )

        stream_key = self.lifecycle_stream()

        type RedisFieldDict = dict[
            bytes | memoryview | str | int | float,
            bytes | memoryview | str | int | float,
        ]

        # Build event payload with metadata
        event_payload: RedisFieldDict = {
            "type": event_type,
            "session_id": session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": json.dumps(data),  # Serialize nested dict
        }

        try:
            # XADD with approximate MAXLEN for performance
            # The ~ (approximate) flag defers trimming to macro-node boundaries
            event_id = await self.redis.xadd(
                name=stream_key,
                fields=event_payload,
                maxlen=max_length,
                approximate=True,  # Enables lazy trimming (~50k, not exactly 50k)
            )

            logger.debug(
                f"Published lifecycle event: {event_type} "
                f"(session={session_id}, event_id={event_id})"
            )

            if isinstance(event_id, bytes):
                return event_id.decode("utf-8")
            return str(event_id)

        except redis.RedisError as e:
            logger.error(
                f"Failed to publish lifecycle event: {event_type} (session={session_id}): {e}"
            )
            # Don't raise - fire-and-forget pattern
            # Wake-Up Sweep will catch missed events
            return ""
