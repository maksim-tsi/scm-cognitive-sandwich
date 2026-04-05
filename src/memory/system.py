"""
Unified Memory System.

This module provides the main entry point for the MAS Memory Layer, orchestrating
all memory tiers (L1-L4), engines, and telemetry signals. It implements the
"Glass Box" observability pattern via the LifecycleStream.
"""

import logging
from typing import Any

from src.llm.client import LLMClient
from src.memory.artifacts.repository import ArtifactRepository
from src.memory.artifacts.service import ArtifactService
from src.memory.ciar_scorer import CIARScorer
from src.memory.engines.consolidation_engine import ConsolidationEngine
from src.memory.engines.distillation_engine import DistillationEngine
from src.memory.engines.fact_extractor import FactExtractor
from src.memory.engines.promotion_engine import PromotionEngine
from src.memory.engines.topic_segmenter import TopicSegmenter
from src.memory.lifecycle_stream import LifecycleStreamProducer
from src.memory.models import ContextBlock, TurnData
from src.memory.tiers.active_context_tier import ActiveContextTier
from src.memory.tiers.episodic_memory_tier import EpisodicMemoryTier
from src.memory.tiers.semantic_memory_tier import SemanticMemoryTier
from src.memory.tiers.working_memory_tier import WorkingMemoryTier

logger = logging.getLogger(__name__)


class UnifiedMemorySystem:
    """
    Orchestrates the complete memory lifecycle (L1->L2->L3->L4).

    Features:
    - Feature Flags: Enable/disable specific tiers or engines (Ablation support).
    - Telemetry: Emits "Glass Box" events for visualization.
    - Facade: Simplified API for agents (`store`, `retrieve`, `search`).
    """

    def __init__(
        self,
        # Adapters
        redis_client: Any,
        postgres_adapter: Any,
        neo4j_adapter: Any,
        qdrant_adapter: Any,
        typesense_adapter: Any,
        # Infrastructure
        llm_client: LLMClient | None = None,
        # Feature Flags (Ablation)
        enable_promotion: bool = True,
        enable_consolidation: bool = True,
        enable_distillation: bool = True,
        enable_telemetry: bool = True,
        # Config
        system_config: dict[str, Any] | None = None,
    ):
        self.config = system_config or {}
        self.llm_client = llm_client or LLMClient.from_env()

        # Flags
        self.enable_promotion = enable_promotion
        self.enable_consolidation = enable_consolidation
        self.enable_distillation = enable_distillation
        self.enable_telemetry = enable_telemetry

        # Telemetry
        self.telemetry_stream: LifecycleStreamProducer | None = None
        if self.enable_telemetry and redis_client:
            # LifecycleStreamProducer needs a raw redis.Redis client, not the adapter.
            # If passed a RedisAdapter, extract its internal client.
            raw_redis = getattr(redis_client, "client", redis_client)
            if raw_redis:
                self.telemetry_stream = LifecycleStreamProducer(raw_redis)

        # Tiers
        self.l1_tier = ActiveContextTier(
            redis_adapter=redis_client,
            postgres_adapter=postgres_adapter,
            telemetry_stream=self.telemetry_stream,
        )
        self.l2_tier = WorkingMemoryTier(
            postgres_adapter=postgres_adapter, telemetry_stream=self.telemetry_stream
        )
        self.l3_tier = EpisodicMemoryTier(
            qdrant_adapter=qdrant_adapter,
            neo4j_adapter=neo4j_adapter,
            telemetry_stream=self.telemetry_stream,
        )
        self.l4_tier = SemanticMemoryTier(
            typesense_adapter=typesense_adapter, telemetry_stream=self.telemetry_stream
        )
        self.artifact_service = ArtifactService(
            ArtifactRepository(
                neo4j_adapter=neo4j_adapter,
                l1_tier=self.l1_tier,
                l2_tier=self.l2_tier,
                l4_tier=self.l4_tier,
            )
        )
        self.artifacts = self.artifact_service

        # Components
        self.topic_segmenter = TopicSegmenter(self.llm_client)
        self.fact_extractor = FactExtractor(self.llm_client)
        self.ciar_scorer = CIARScorer()

        # Engines
        self.promotion_engine = PromotionEngine(
            l1_tier=self.l1_tier,
            l2_tier=self.l2_tier,
            topic_segmenter=self.topic_segmenter,
            fact_extractor=self.fact_extractor,
            ciar_scorer=self.ciar_scorer,
            config=self.config.get("promotion", {}),
            telemetry_stream=self.telemetry_stream,
        )
        self.consolidation_engine = ConsolidationEngine(
            l2_tier=self.l2_tier,
            l3_tier=self.l3_tier,
            llm_provider=self.llm_client,
            config=self.config.get("consolidation", {}),
            telemetry_stream=self.telemetry_stream,
        )
        self.distillation_engine = DistillationEngine(
            l3_tier=self.l3_tier,
            l4_tier=self.l4_tier,
            llm_provider=self.llm_client,
            config=self.config.get("distillation", {}),
            telemetry_stream=self.telemetry_stream,
        )

    async def initialize(self) -> None:
        """Initialize all tiers and engines."""
        # Tiers usually don't need explicit async init if adapters are ready,
        # but specialized connections might.
        pass

    async def get_context_block(
        self,
        session_id: str,
        min_ciar: float = 0.6,
        max_turns: int = 20,
        max_facts: int = 10,
    ) -> ContextBlock:
        """
        Assemble context from L1 and L2 for an agent.
        """
        if self.enable_telemetry and self.telemetry_stream:
            await self.telemetry_stream.publish(
                event_type="context_retrieval_start",
                session_id=session_id,
                data={"min_ciar": min_ciar, "max_turns": max_turns},
            )

        # 1. Retrieve Recent Turns (L1)
        recent_turns_data = await self.l1_tier.retrieve_session(session_id)
        recent_turns = (recent_turns_data or [])[:max_turns]

        # 2. Retrieve Significant Facts (L2)
        significant_facts = await self.l2_tier.query_by_session(
            session_id, min_ciar_score=min_ciar, limit=max_facts
        )

        block = ContextBlock(
            session_id=session_id,
            recent_turns=[t.model_dump() if isinstance(t, TurnData) else t for t in recent_turns],
            significant_facts=significant_facts,
        )

        if self.enable_telemetry and self.telemetry_stream:
            await self.telemetry_stream.publish(
                event_type="context_retrieval_end",
                session_id=session_id,
                data={
                    "turn_count": len(block.recent_turns),
                    "fact_count": len(block.significant_facts),
                    "estimated_tokens": block.estimate_token_count(),
                },
            )

        return block

    async def run_promotion_cycle(self, session_id: str) -> dict[str, Any]:
        """Trigger L1->L2 promotion if enabled."""
        if not self.enable_promotion:
            logger.info("DEBUG: Promotion cycle skipped (disabled)")
            return {"status": "skipped", "reason": "promotion_disabled"}

        logger.info(f"DEBUG: UnifiedMemorySystem triggering promotion for {session_id}")
        return await self.promotion_engine.process_session(session_id)

    async def cleanup_session(self, session_id: str) -> None:
        """Clean up session data across all tiers."""
        await self.l1_tier.delete(session_id)
        # Add other tier cleanup if implemented
