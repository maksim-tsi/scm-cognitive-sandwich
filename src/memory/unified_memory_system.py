# file: memory_system.py

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal, cast

import redis
from pydantic import BaseModel, Field, ValidationError

from src.llm.client import LLMClient
from src.memory.artifacts.repository import ArtifactRepository
from src.memory.artifacts.service import ArtifactService
from src.memory.engines.consolidation_engine import ConsolidationEngine
from src.memory.engines.distillation_engine import DistillationEngine
from src.memory.engines.promotion_engine import PromotionEngine
from src.memory.knowledge_store_manager import KnowledgeStoreManager
from src.memory.models import (
    ContextBlock,
    Fact,
    SearchWeights,
)
from src.memory.tiers import (
    ActiveContextTier,
    EpisodicMemoryTier,
    SemanticMemoryTier,
    WorkingMemoryTier,
)
from src.observability import set_span_attributes, set_span_error, start_span

# --- Data Schemas for Operating Memory (Data Contracts) ---


class PersonalMemoryState(BaseModel):
    agent_id: str
    current_task_id: str | None = None
    scratchpad: dict[str, Any] = Field(default_factory=dict)
    promotion_candidates: dict[str, Any] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class SharedWorkspaceState(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    status: Literal["active", "resolved", "cancelled"] = "active"
    shared_data: dict[str, Any] = Field(default_factory=dict)
    participating_agents: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# --- Abstract Interface for the COMPLETE Memory System ---


class HybridMemorySystem(ABC):
    """
    Abstract base class defining the contract for the COMPLETE hybrid memory system.
    This is the SINGLE interface agents will use for all memory operations.
    """

    # --- Operating Memory Methods ---
    @abstractmethod
    def get_personal_state(self, agent_id: str) -> PersonalMemoryState:
        pass

    @abstractmethod
    def update_personal_state(self, state: PersonalMemoryState) -> None:
        pass

    @abstractmethod
    def get_shared_state(self, event_id: str) -> SharedWorkspaceState:
        pass

    @abstractmethod
    def update_shared_state(self, state: SharedWorkspaceState) -> None:
        pass

    @abstractmethod
    def publish_update(self, event_id: str, update_summary: dict) -> None:
        pass

    # --- Persistent Knowledge Methods ---
    @abstractmethod
    def query_knowledge(
        self,
        store_type: Literal["vector", "graph"],
        query_text: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Queries the persistent knowledge layer."""
        pass

    # --- Lifecycle Engine Methods ---
    @abstractmethod
    async def run_promotion_cycle(self, session_id: str) -> list[Fact]:
        """Execute L1→L2 promotion cycle with CIAR filtering."""
        pass

    @abstractmethod
    async def run_consolidation_cycle(self, session_id: str) -> dict[str, Any]:
        """Execute L2→L3 consolidation cycle."""
        pass

    @abstractmethod
    async def run_distillation_cycle(self, session_id: str | None = None) -> dict[str, Any]:
        """Execute L3→L4 distillation cycle."""
        pass

    # --- Cross-Tier Query Methods ---
    @abstractmethod
    async def query_memory(
        self, session_id: str, query: str, limit: int = 10, weights: SearchWeights | None = None
    ) -> list[dict[str, Any]]:
        """Hybrid semantic search across L2, L3, and L4 tiers."""
        pass

    @abstractmethod
    async def get_context_block(
        self, session_id: str, min_ciar: float = 0.6, max_turns: int = 20, max_facts: int = 10
    ) -> ContextBlock:
        """Assemble context block for prompt injection."""
        pass


# --- Concrete UNIFIED Implementation ---


class UnifiedMemorySystem(HybridMemorySystem):
    """
    A concrete implementation of the HybridMemorySystem, unifying Operating Memory (Redis)
    and the Persistent Knowledge Layer (via KnowledgeStoreManager).

    Integrates all four memory tiers (L1-L4) with lifecycle engines for automated
    information flow and promotion.
    """

    def __init__(
        self,
        redis_client: redis.StrictRedis,
        knowledge_manager: KnowledgeStoreManager,
        llm_client: LLMClient | None = None,
        l1_tier: ActiveContextTier | None = None,
        l2_tier: WorkingMemoryTier | None = None,
        l3_tier: EpisodicMemoryTier | None = None,
        l4_tier: SemanticMemoryTier | None = None,
        promotion_engine: PromotionEngine | None = None,
        consolidation_engine: ConsolidationEngine | None = None,
        distillation_engine: DistillationEngine | None = None,
    ):
        """
        Initializes the memory system with clients for all layers.

        Args:
            redis_client: Redis client for Operating Memory
            knowledge_manager: Facade for persistent knowledge stores
            llm_client: Optional LLM client used for embedding-backed retrieval
            l1_tier: Active Context tier (L1) - optional for backward compatibility
            l2_tier: Working Memory tier (L2) - optional for backward compatibility
            l3_tier: Episodic Memory tier (L3) - optional for backward compatibility
            l4_tier: Semantic Memory tier (L4) - optional for backward compatibility
            promotion_engine: L1→L2 promotion engine - optional
            consolidation_engine: L2→L3 consolidation engine - optional
            distillation_engine: L3→L4 distillation engine - optional
        """
        # --- Operating Memory Client ---
        self.redis_client = redis_client
        try:
            if not self.redis_client.ping():
                raise ConnectionError("Could not connect to Redis.")
        except redis.exceptions.ConnectionError as e:
            print(f"Error connecting to Redis: {e}")
            raise

        # --- Persistent Knowledge Layer Client ---
        self.knowledge_manager = knowledge_manager
        self.llm_client = llm_client

        # --- Memory Tiers ---
        self.l1_tier = l1_tier
        self.l2_tier = l2_tier
        self.l3_tier = l3_tier
        self.l4_tier = l4_tier

        # --- Lifecycle Engines ---
        self.promotion_engine = promotion_engine
        self.consolidation_engine = consolidation_engine
        self.distillation_engine = distillation_engine
        self.artifact_service: ArtifactService | None = None
        self.artifacts: ArtifactService | None = None
        if self.l3_tier and getattr(self.l3_tier, "neo4j", None):
            self.artifact_service = ArtifactService(
                ArtifactRepository(
                    neo4j_adapter=self.l3_tier.neo4j,
                    l1_tier=self.l1_tier,
                    l2_tier=self.l2_tier,
                    l4_tier=self.l4_tier,
                )
            )
            self.artifacts = self.artifact_service

    @staticmethod
    def _normalize_score(score: float, min_score: float, max_score: float) -> float:
        """Normalize a score to the unit interval using min-max normalization."""
        score_range = max_score - min_score
        if score_range <= 0:
            return 0.5
        return (score - min_score) / score_range

    @staticmethod
    def _fact_to_retrieval_document(fact: Any) -> dict[str, Any]:
        """Serialize an L2 fact into retriever evidence format."""
        fact_id = getattr(fact, "fact_id", None) or "unknown"
        return {
            "document.id": f"L2:{fact_id}",
            "document.content": getattr(fact, "content", ""),
            "document.score": getattr(fact, "ciar_score", None),
            "document.metadata": {
                "tier": "L2",
                "session_id": getattr(fact, "session_id", None),
                "fact_type": getattr(fact, "fact_type", None),
                "ciar_score": getattr(fact, "ciar_score", None),
                "certainty": getattr(fact, "certainty", None),
                "impact": getattr(fact, "impact", None),
                "created_at": getattr(
                    getattr(fact, "created_at", None), "isoformat", lambda: None
                )(),
                "extracted_at": getattr(
                    getattr(fact, "extracted_at", None), "isoformat", lambda: None
                )(),
            },
        }

    @staticmethod
    def _episode_to_retrieval_document(episode: Any) -> dict[str, Any]:
        """Serialize an L3 episode into retriever evidence format."""
        similarity_score = float(
            getattr(episode, "metadata", {}).get(
                "similarity_score", getattr(episode, "importance_score", 0.0)
            )
        )
        episode_id = getattr(episode, "episode_id", None) or "unknown"
        return {
            "document.id": f"L3:{episode_id}",
            "document.content": getattr(episode, "summary", ""),
            "document.score": similarity_score,
            "document.metadata": {
                "tier": "L3",
                "session_id": getattr(episode, "session_id", None),
                "fact_count": getattr(episode, "fact_count", None),
                "importance_score": getattr(episode, "importance_score", None),
                "topics": getattr(episode, "topics", []),
                "consolidated_at": getattr(
                    getattr(episode, "consolidated_at", None), "isoformat", lambda: None
                )(),
            },
        }

    @staticmethod
    def _knowledge_to_retrieval_document(document: Any) -> dict[str, Any]:
        """Serialize an L4 knowledge document into retriever evidence format."""
        search_score = float(
            getattr(document, "metadata", {}).get(
                "search_score", getattr(document, "confidence_score", 0.0)
            )
        )
        knowledge_id = getattr(document, "knowledge_id", None) or "unknown"
        return {
            "document.id": f"L4:{knowledge_id}",
            "document.content": getattr(document, "content", ""),
            "document.score": search_score,
            "document.metadata": {
                "tier": "L4",
                "session_id": getattr(document, "session_id", None),
                "title": getattr(document, "title", None),
                "knowledge_type": getattr(document, "knowledge_type", None),
                "confidence_score": getattr(document, "confidence_score", None),
                "tags": getattr(document, "tags", []),
                "distilled_at": getattr(
                    getattr(document, "distilled_at", None), "isoformat", lambda: None
                )(),
            },
        }

    async def _query_l3_episodes(self, session_id: str, query: str, limit: int) -> list[Any]:
        """Run query-conditioned L3 retrieval when episodic memory is configured."""
        if not self.l3_tier or not self.llm_client:
            return []

        query_embedding = await self.llm_client.get_embedding(query)
        return await self.l3_tier.search_similar(
            query_embedding=query_embedding,
            limit=limit,
            filters={"session_id": session_id},
        )

    async def _query_l4_documents(self, query: str, limit: int) -> list[Any]:
        """Run query-conditioned L4 retrieval when semantic memory is configured."""
        if not self.l4_tier:
            return []
        return await self.l4_tier.search(query_text=query, limit=limit)

    # --- Private Key Helpers for Redis ---
    def _get_personal_key(self, agent_id: str) -> str:
        return f"personal_state:{agent_id}"

    def _get_shared_key(self, event_id: str) -> str:
        return f"shared_state:{event_id}"

    def _get_channel_key(self, event_id: str) -> str:
        return f"channel:shared_state:{event_id}"

    # --- Operating Memory Implementation (Delegates to Redis) ---
    def get_personal_state(self, agent_id: str) -> PersonalMemoryState:
        key = self._get_personal_key(agent_id)
        raw_state = self.redis_client.get(key)
        if raw_state is None:
            return PersonalMemoryState(agent_id=agent_id)
        try:
            return PersonalMemoryState.model_validate_json(raw_state)
        except ValidationError as e:
            print(f"Data validation error for agent '{agent_id}': {e}")
            return PersonalMemoryState(agent_id=agent_id)

    def update_personal_state(self, state: PersonalMemoryState) -> None:
        key = self._get_personal_key(state.agent_id)
        state.last_updated = datetime.utcnow()
        self.redis_client.set(key, state.model_dump_json())

    def get_shared_state(self, event_id: str) -> SharedWorkspaceState:
        key = self._get_shared_key(event_id)
        raw_state = self.redis_client.get(key)
        if raw_state is None:
            raise KeyError(f"No shared workspace found for event_id: {event_id}")
        try:
            return SharedWorkspaceState.model_validate_json(raw_state)
        except ValidationError as e:
            raise ValueError(f"Corrupted data for event_id: {event_id}") from e

    def update_shared_state(self, state: SharedWorkspaceState) -> None:
        key = self._get_shared_key(state.event_id)
        state.last_updated = datetime.utcnow()
        self.redis_client.set(key, state.model_dump_json())
        update_summary = {
            "event_id": state.event_id,
            "status": state.status,
            "last_updated_by": state.participating_agents[-1]
            if state.participating_agents
            else "system",
        }
        self.publish_update(state.event_id, update_summary)

    def publish_update(self, event_id: str, update_summary: dict) -> None:
        channel = self._get_channel_key(event_id)
        self.redis_client.publish(channel, json.dumps(update_summary))

    # --- Persistent Knowledge Implementation (Delegates to KnowledgeStoreManager) ---
    def query_knowledge(
        self,
        store_type: Literal["vector", "graph"],
        query_text: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Delegates the query to the knowledge store manager."""
        return self.knowledge_manager.query(
            store_type=store_type, query_text=query_text, top_k=top_k, filters=filters
        )

    # --- Lifecycle Engine Implementation ---

    async def run_promotion_cycle(self, session_id: str) -> list[Fact]:
        """
        Execute L1→L2 promotion cycle with CIAR filtering.

        Args:
            session_id: Session to promote turns from

        Returns:
            List of Facts promoted to L2

        Raises:
            RuntimeError: If promotion engine or required tiers not configured
        """
        if not self.promotion_engine:
            raise RuntimeError("PromotionEngine not configured")
        if not self.l1_tier or not self.l2_tier:
            raise RuntimeError("L1 and L2 tiers required for promotion")

        # Run promotion engine
        facts = await self.promotion_engine.promote_session(session_id)
        return facts

    async def run_consolidation_cycle(self, session_id: str) -> dict[str, Any]:
        """
        Execute L2→L3 consolidation cycle.

        Args:
            session_id: Session to consolidate facts from

        Returns:
            Dict with consolidation statistics
        """
        if not self.consolidation_engine:
            raise RuntimeError("ConsolidationEngine not configured")
        if not self.l2_tier or not self.l3_tier:
            raise RuntimeError("L2 and L3 tiers required for consolidation")

        # Run consolidation engine
        return await self.consolidation_engine.process_session(session_id)

    async def run_distillation_cycle(self, session_id: str | None = None) -> dict[str, Any]:
        """
        Execute L3→L4 distillation cycle.

        Args:
            session_id: Optional session filter (None = global distillation)

        Returns:
            Dict with distillation statistics
        """
        if not self.distillation_engine:
            raise RuntimeError("DistillationEngine not configured")
        if not self.l3_tier or not self.l4_tier:
            raise RuntimeError("L3 and L4 tiers required for distillation")

        # Run distillation engine
        # Run distillation engine
        if session_id:
            return await self.distillation_engine.distill(session_id=session_id)
        else:
            return await self.distillation_engine.distill()

    async def handle_external_episode(
        self, session_id: str, agent_id: str, final_state: dict[str, Any], metadata: dict[str, Any]
    ) -> None:
        """
        Process a completed reasoning episode from an external cognitive architecture.

        Stores the final state directly into L2 Working Memory and triggers an immediate
        consolidation cycle to move it into L3 Episodic Memory, bypassing L1 caching.
        """
        if not self.l2_tier:
            raise RuntimeError("L2 tier required to handle external episodes")

        import json
        import uuid

        from src.memory.models import Fact, FactType

        fact_id = f"ext_ep_{uuid.uuid4().hex}"
        content = json.dumps(final_state)

        # We store the episode summary as a high-CIAR Fact in L2
        fact = Fact(
            fact_id=fact_id,
            session_id=session_id,
            content=content[:5000],  # Enforce max length
            fact_type=FactType.EVENT,
            ciar_score=1.0,  # Ensure it is prioritized for consolidation
            certainty=1.0,
            impact=1.0,
            source_type="external_handoff",
            metadata={
                "agent_id": agent_id,
                "status": metadata.get("status", "unknown"),
                "duration_seconds": metadata.get("duration_seconds", 0.0),
                "solver_attempts": metadata.get("solver_attempts", 0),
            },
        )

        # 1. Store directly to L2
        await self.l2_tier.store(fact)

        # 2. Trigger L2->L3 Consolidation Cycle
        try:
            await self.run_consolidation_cycle(session_id)
        except Exception as e:
            # We log but do not bubble up, as this is an async background task usually
            print(f"Failed to run consolidation cycle for external episode: {e}")

    # --- Cross-Tier Query Implementation ---

    async def query_memory(
        self, session_id: str, query: str, limit: int = 10, weights: SearchWeights | None = None
    ) -> list[dict[str, Any]]:
        """
        Hybrid semantic search across L2, L3, and L4 tiers.

        Merges results from multiple tiers using configurable weights
        with min-max normalization for comparable scoring.

        Args:
            session_id: Session context for search
            query: Search query string
            limit: Maximum results to return
            weights: Search weighting config (default: 0.3/0.5/0.2 for L2/L3/L4)

        Returns:
            List of ranked results with unified schema:
            [
                {
                    'content': str,
                    'tier': str (L2/L3/L4),
                    'score': float (0.0-1.0),
                    'metadata': dict
                }
            ]
        """
        if weights is None:
            weights = SearchWeights()  # Use defaults

        all_results = []

        # L2: Working Memory (Facts)
        if self.l2_tier and weights.l2_weight > 0:
            with start_span(
                tracer_name="yaam.memory",
                span_name="yaam.retriever.l2",
                kind="RETRIEVER",
                attributes={
                    "session.id": session_id,
                    "input.value": query,
                    "yaam.memory.tier": "L2",
                    "yaam.retrieval.limit": limit,
                },
            ) as span:
                try:
                    if hasattr(self.l2_tier, "search_facts"):
                        l2_facts = await self.l2_tier.search_facts(
                            query=query, session_id=session_id, limit=limit
                        )
                    elif hasattr(self.l2_tier, "query_by_session"):
                        l2_facts = await self.l2_tier.query_by_session(
                            session_id=session_id, limit=limit
                        )
                    else:
                        l2_facts = []

                    set_span_attributes(
                        span,
                        {
                            "retrieval.documents": [
                                self._fact_to_retrieval_document(fact) for fact in l2_facts
                            ],
                            "yaam.retrieval.result_count": len(l2_facts),
                        },
                    )

                    if l2_facts:
                        l2_scores = [f.ciar_score for f in l2_facts]
                        min_score, max_score = min(l2_scores), max(l2_scores)
                        score_range = max_score - min_score if max_score > min_score else 1.0

                        for fact in l2_facts:
                            normalized_score = (
                                (fact.ciar_score - min_score) / score_range
                                if score_range > 0
                                else 0.5
                            )
                            weighted_score = normalized_score * weights.l2_weight
                            all_results.append(
                                {
                                    "content": fact.content,
                                    "tier": "L2",
                                    "score": weighted_score,
                                    "metadata": {
                                        "fact_id": fact.fact_id,
                                        "fact_type": fact.fact_type,
                                        "ciar_score": fact.ciar_score,
                                        "extracted_at": fact.extracted_at.isoformat(),
                                    },
                                }
                            )
                except Exception as e:
                    set_span_error(span, e)
                    print(f"L2 query failed: {e}")

        # L3: Episodic Memory (Episodes)
        if self.l3_tier and weights.l3_weight > 0:
            with start_span(
                tracer_name="yaam.memory",
                span_name="yaam.retriever.l3",
                kind="RETRIEVER",
                attributes={
                    "session.id": session_id,
                    "input.value": query,
                    "yaam.memory.tier": "L3",
                    "yaam.retrieval.limit": limit,
                },
            ) as span:
                try:
                    l3_episodes = await self._query_l3_episodes(
                        session_id=session_id,
                        query=query,
                        limit=limit,
                    )
                    set_span_attributes(
                        span,
                        {
                            "retrieval.documents": [
                                self._episode_to_retrieval_document(episode)
                                for episode in l3_episodes
                            ],
                            "yaam.retrieval.result_count": len(l3_episodes),
                        },
                    )
                    if l3_episodes:
                        l3_scores = [
                            float(e.metadata.get("similarity_score", e.importance_score))
                            for e in l3_episodes
                        ]
                        min_score, max_score = min(l3_scores), max(l3_scores)

                        for episode in l3_episodes:
                            similarity_score = float(
                                episode.metadata.get("similarity_score", episode.importance_score)
                            )
                            normalized_score = self._normalize_score(
                                similarity_score, min_score, max_score
                            )
                            weighted_score = normalized_score * weights.l3_weight
                            all_results.append(
                                {
                                    "content": episode.summary,
                                    "tier": "L3",
                                    "score": weighted_score,
                                    "metadata": {
                                        "episode_id": episode.episode_id,
                                        "fact_count": episode.fact_count,
                                        "importance_score": episode.importance_score,
                                        "similarity_score": similarity_score,
                                        "topics": episode.topics,
                                        "consolidated_at": episode.consolidated_at.isoformat(),
                                    },
                                }
                            )
                except Exception as e:
                    set_span_error(span, e)
                    print(f"L3 query failed: {e}")

        # L4: Semantic Memory (Knowledge Documents)
        if self.l4_tier and weights.l4_weight > 0:
            with start_span(
                tracer_name="yaam.memory",
                span_name="yaam.retriever.l4",
                kind="RETRIEVER",
                attributes={
                    "session.id": session_id,
                    "input.value": query,
                    "yaam.memory.tier": "L4",
                    "yaam.retrieval.limit": limit,
                },
            ) as span:
                try:
                    l4_docs = await self._query_l4_documents(query=query, limit=limit)
                    set_span_attributes(
                        span,
                        {
                            "retrieval.documents": [
                                self._knowledge_to_retrieval_document(doc) for doc in l4_docs
                            ],
                            "yaam.retrieval.result_count": len(l4_docs),
                        },
                    )
                    if l4_docs:
                        l4_scores = [
                            float(d.metadata.get("search_score", d.confidence_score))
                            for d in l4_docs
                        ]
                        min_score, max_score = min(l4_scores), max(l4_scores)

                        for doc in l4_docs:
                            search_score = float(
                                doc.metadata.get("search_score", doc.confidence_score)
                            )
                            normalized_score = self._normalize_score(
                                search_score, min_score, max_score
                            )
                            weighted_score = normalized_score * weights.l4_weight
                            all_results.append(
                                {
                                    "content": doc.content,
                                    "tier": "L4",
                                    "score": weighted_score,
                                    "metadata": {
                                        "knowledge_id": doc.knowledge_id,
                                        "title": doc.title,
                                        "knowledge_type": doc.knowledge_type,
                                        "confidence_score": doc.confidence_score,
                                        "search_score": search_score,
                                        "tags": doc.tags,
                                        "distilled_at": doc.distilled_at.isoformat(),
                                    },
                                }
                            )
                except Exception as e:
                    set_span_error(span, e)
                    print(f"L4 query failed: {e}")

        # Sort by weighted score and limit results
        all_results.sort(key=lambda x: float(cast(float, x["score"])), reverse=True)
        return all_results[:limit]

    async def get_context_block(
        self, session_id: str, min_ciar: float = 0.6, max_turns: int = 20, max_facts: int = 10
    ) -> ContextBlock:
        """
        Assemble context block for prompt injection.

        Retrieves recent L1 turns and high-CIAR L2 facts, optionally
        including L3 episode summaries and L4 knowledge snippets.

        Args:
            session_id: Session to retrieve context for
            min_ciar: Minimum CIAR score for L2 facts
            max_turns: Maximum L1 turns to include
            max_facts: Maximum L2 facts to include

        Returns:
            ContextBlock ready for prompt injection

        Raises:
            RuntimeError: If required tiers not configured
        """
        context = ContextBlock(session_id=session_id, min_ciar_threshold=min_ciar)

        # Retrieve L1 recent turns
        if self.l1_tier:
            try:
                turns = await self.l1_tier.retrieve_session(session_id=session_id)
                if turns is None:
                    turns = []
                if max_turns is not None:
                    from typing import cast

                    # Explicit cast/assignment to satisfy mypy
                    turns_list: list[dict[str, Any]] = [
                        cast(dict[str, Any], t.model_dump() if hasattr(t, "model_dump") else t)
                        for t in turns[:max_turns]
                    ]
                    context.recent_turns = turns_list
                else:
                    context.recent_turns = [] if turns is None else turns
                context.turn_count = len(turns)
            except Exception as e:
                print(f"L1 retrieval failed: {e}")

        # Retrieve L2 high-CIAR facts
        if self.l2_tier:
            try:
                if hasattr(self.l2_tier, "query_by_session"):
                    facts = await self.l2_tier.query_by_session(
                        session_id=session_id, min_ciar_score=min_ciar, limit=max_facts
                    )
                else:
                    facts = []
                context.significant_facts = facts
                context.fact_count = len(facts)
            except Exception as e:
                print(f"L2 retrieval failed: {e}")

        # Estimate token count
        context.estimate_token_count()

        return context


if __name__ == "__main__":
    # --- Example Usage for the UNIFIED System ---

    # This setup requires all database services to be running.
    # We will use mock objects for a simple, self-contained demonstration.

    class MockQdrantStore:
        def query_similar(self, **kwargs):
            return [{"id": 1, "content": "Mock vector search result."}]

        def add_documents(self, **kwargs):
            return [1]

        def delete_documents(self, **kwargs):
            pass

        def recreate_collection(self, **kwargs):
            pass

    class MockNeo4jStore:
        def query(self, **kwargs):
            return [{"node": "Mock graph query result."}]

    print("--- Phase 3: Unified Memory System Demo ---")

    # 1. Instantiate all backend clients (using mocks for this demo)
    mock_qdrant = MockQdrantStore()
    mock_neo4j = MockNeo4jStore()

    knowledge_manager = KnowledgeStoreManager(
        vector_store=mock_qdrant,  # type: ignore
        graph_store=mock_neo4j,  # type: ignore
    )

    # Use an in-memory "fakeredis" for the demo to avoid a real connection
    import fakeredis

    fake_redis_client = fakeredis.FakeStrictRedis(decode_responses=True)

    # 2. Instantiate the single, unified memory system
    memory = UnifiedMemorySystem(
        redis_client=fake_redis_client, knowledge_manager=knowledge_manager
    )
    print("UnifiedMemorySystem instantiated with mock backends.")

    # 3. Use Operating Memory (same as before)
    agent_id = "port_agent_007"
    print(f"\n--- Testing Operating Memory for agent: {agent_id} ---")
    personal_state = memory.get_personal_state(agent_id)
    personal_state.scratchpad["status"] = "monitoring"
    memory.update_personal_state(personal_state)
    retrieved_state = memory.get_personal_state(agent_id)
    print(f"Retrieved personal state from Redis: {retrieved_state.scratchpad['status']}")
    assert retrieved_state.scratchpad["status"] == "monitoring"

    # 4. Use Persistent Knowledge Layer THROUGH THE SAME INTERFACE
    print("\n--- Testing Persistent Knowledge Layer ---")

    # An agent needs to find similar past events
    vector_results = memory.query_knowledge(
        store_type="vector", query_text="Find events about port congestion"
    )
    print(f"Vector search result: {vector_results}")
    assert vector_results[0]["content"] == "Mock vector search result."

    # An agent needs to find a specific relationship
    graph_results = memory.query_knowledge(
        store_type="graph", query_text="MATCH (v:Vessel)-[:HAS]->(c:Cargo) RETURN v, c"
    )
    print(f"Graph query result: {graph_results}")
    assert graph_results[0]["node"] == "Mock graph query result."

    print(
        "\n✅ Demo complete. The UnifiedMemorySystem successfully routes requests to both Operating and Persistent layers."
    )
