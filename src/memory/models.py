"""
Data models for memory system.

Defines Pydantic models for facts, episodes, and knowledge documents
with validation and serialization support.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from .ciar_formula import (
    DEFAULT_AGE_DECAY_LAMBDA,
    DEFAULT_RECENCY_ALPHA,
    calculate_age_decay,
    calculate_ciar_score,
    calculate_recency_boost,
)


class FactType(StrEnum):
    """Classification of fact types."""

    PREFERENCE = "preference"  # User preferences (high impact)
    CONSTRAINT = "constraint"  # Business rules, requirements
    ENTITY = "entity"  # Named entities, objects
    MENTION = "mention"  # Casual mentions (low impact)
    RELATIONSHIP = "relationship"  # Entity relationships
    EVENT = "event"  # Temporal events
    INSTRUCTION = "instruction"  # Behavioral constraints, delayed commands


class FactCategory(StrEnum):
    """Domain-specific fact categories."""

    PERSONAL = "personal"
    BUSINESS = "business"
    TECHNICAL = "technical"
    OPERATIONAL = "operational"


class TurnData(BaseModel):
    """
    Represents a single conversational turn in L1 Active Context.

    Attributes:
        turn_id: Unique identifier for the turn
        session_id: Associated session identifier
        role: Speaker role (user, assistant, system)
        content: Turn content
        timestamp: Turn timestamp (UTC)
        metadata: Additional context for the turn
    """

    turn_id: str = Field(..., min_length=1, max_length=200)
    session_id: str = Field(..., min_length=1, max_length=200)
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=200000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", mode="before")
    @classmethod
    def coerce_turn_id(cls, value: Any) -> str:
        """Normalize turn_id to string for consistent identifiers."""
        if value is None:
            raise ValueError("turn_id cannot be None")
        return str(value)


class Fact(BaseModel):
    """
    Represents a significant fact in L2 Working Memory.

    Attributes:
        fact_id: Unique identifier
        session_id: Associated session
        content: Natural language fact statement
        ciar_score: Computed CIAR significance score
        certainty: Confidence in fact accuracy (0.0-1.0)
        impact: Estimated importance (0.0-1.0)
        age_decay: Time-based decay factor
        recency_boost: Access-based boost factor
        source_uri: Reference to source turn in L1
        source_type: How fact was obtained
        fact_type: Classification of fact
        fact_category: Domain category
        metadata: Additional context
        extracted_at: When fact was extracted
        last_accessed: Most recent access time
        access_count: Number of times accessed
    """

    fact_id: str
    session_id: str
    content: str = Field(..., min_length=1, max_length=5000)

    # CIAR components
    ciar_score: float = Field(default=0.0, ge=0.0, le=1.0)
    certainty: float = Field(default=0.7, ge=0.0, le=1.0)
    impact: float = Field(default=0.5, ge=0.0, le=1.0)
    age_decay: float = Field(default=1.0, ge=0.0, le=1.0)
    recency_boost: float = Field(default=1.0, ge=0.0)

    # Provenance
    source_uri: str | None = None
    source_type: str = Field(default="extracted")

    # Topic Segmentation (ADR-003: batch processing context)
    topic_segment_id: str | None = None  # Links to source TopicSegment
    topic_label: str | None = None  # Brief topic from segment

    # Classification
    fact_type: FactType | None = None
    fact_category: FactCategory | None = None

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)
    justification: str | None = None  # Explanation for extraction/promotion logic

    # Timestamps
    created_at: datetime | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    access_count: int = Field(default=0, ge=0)

    model_config = {"use_enum_values": True}

    @field_validator("ciar_score")
    @classmethod
    def validate_ciar_score(cls, v: float, info: ValidationInfo) -> float:
        """Ensure CIAR score is consistent with components if all are present."""
        values = info.data
        if all(k in values for k in ["certainty", "impact", "age_decay", "recency_boost"]):
            expected = calculate_ciar_score(
                values["certainty"],
                values["impact"],
                values["age_decay"],
                values["recency_boost"],
            )
            # Allow small floating point differences
            if abs(v - expected) > 0.01:
                return float(round(expected, 4))
        return v

    def mark_accessed(self, alpha: float = DEFAULT_RECENCY_ALPHA) -> None:
        """Update access tracking."""
        self.last_accessed = datetime.now(UTC)
        self.access_count += 1
        self.recency_boost = round(calculate_recency_boost(self.access_count, alpha=alpha), 4)
        self.ciar_score = round(
            calculate_ciar_score(
                self.certainty,
                self.impact,
                self.age_decay,
                self.recency_boost,
            ),
            4,
        )

    def calculate_age_decay(
        self,
        decay_lambda: float = DEFAULT_AGE_DECAY_LAMBDA,
        max_age_days: float | None = None,
        min_score: float = 0.0,
    ) -> None:
        """
        Calculate age decay factor based on time since extraction.

        Args:
            decay_lambda: Decay rate (default: 0.1 per day)
        """
        source_timestamp = self.created_at or self.extracted_at
        self.age_decay = round(
            calculate_age_decay(
                source_timestamp,
                decay_lambda=decay_lambda,
                max_age_days=max_age_days,
                min_score=min_score,
            ),
            4,
        )
        self.ciar_score = round(
            calculate_ciar_score(
                self.certainty,
                self.impact,
                self.age_decay,
                self.recency_boost,
            ),
            4,
        )

    # Provide lightweight dict-style access for compatibility with callers that
    # expect mapping semantics from Fact instances.
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to database-compatible dictionary."""
        import json

        return {
            "fact_id": self.fact_id,
            "session_id": self.session_id,
            "content": self.content,
            "ciar_score": self.ciar_score,
            "certainty": self.certainty,
            "impact": self.impact,
            "age_decay": self.age_decay,
            "recency_boost": self.recency_boost,
            "source_uri": self.source_uri,
            "source_type": self.source_type,
            "topic_segment_id": self.topic_segment_id,
            "topic_label": self.topic_label,
            "fact_type": self.fact_type.value
            if isinstance(self.fact_type, FactType)
            else self.fact_type,
            "fact_category": self.fact_category.value
            if isinstance(self.fact_category, FactCategory)
            else self.fact_category,
            "metadata": json.dumps(self.metadata) if self.metadata else "{}",
            "extracted_at": self.created_at or self.extracted_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "justification": self.justification,
        }


class FactQuery(BaseModel):
    """Query parameters for retrieving facts."""

    session_id: str | None = None
    min_ciar_score: float | None = Field(default=0.6, ge=0.0, le=1.0)
    fact_types: list[FactType] | None = None
    fact_categories: list[FactCategory] | None = None
    limit: int = Field(default=10, ge=1, le=100)
    order_by: str = Field(default="ciar_score DESC")


class Episode(BaseModel):
    """
    Represents a consolidated episode in L3 Episodic Memory.

    Episodes are clusters of related facts from L2, summarized into
    coherent narrative experiences. Dual-indexed in Qdrant (vector)
    and Neo4j (graph) for hybrid retrieval.
    """

    episode_id: str
    session_id: str

    # Content
    summary: str = Field(..., min_length=10, max_length=10000)
    narrative: str | None = None  # Longer form narrative

    # Source facts
    source_fact_ids: list[str] = Field(default_factory=list)
    fact_count: int = Field(default=0, ge=0)

    # Temporal boundaries
    time_window_start: datetime
    time_window_end: datetime
    duration_seconds: float = Field(default=0.0, ge=0.0)

    # Bi-temporal properties (ADR-003 requirement)
    fact_valid_from: datetime  # When facts became true
    fact_valid_to: datetime | None = None  # When facts stopped being true
    source_observation_timestamp: datetime  # When we observed/recorded this

    # Embeddings and indexing
    embedding_model: str = Field(default="text-embedding-ada-002")
    vector_id: str | None = None  # Qdrant point ID
    graph_node_id: str | None = None  # Neo4j node ID

    # Metadata
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # Provenance
    consolidated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    consolidation_method: str = Field(default="llm_clustering")

    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_qdrant_payload(self) -> dict[str, Any]:
        """Convert to Qdrant payload format."""
        return {
            "episode_id": self.episode_id,
            "session_id": self.session_id,
            "summary": self.summary,
            "narrative": self.narrative,
            "source_fact_ids": self.source_fact_ids,
            "fact_count": self.fact_count,
            "time_window_start": self.time_window_start.isoformat(),
            "time_window_end": self.time_window_end.isoformat(),
            "fact_valid_from": self.fact_valid_from.isoformat(),
            "fact_valid_to": self.fact_valid_to.isoformat() if self.fact_valid_to else None,
            "topics": self.topics,
            "importance_score": self.importance_score,
            "graph_node_id": self.graph_node_id,
            "consolidated_at": self.consolidated_at.isoformat(),
        }

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "episodeId": self.episode_id,
            "sessionId": self.session_id,
            "summary": self.summary,
            "narrative": self.narrative or "",
            "factCount": self.fact_count,
            "timeWindowStart": self.time_window_start.isoformat(),
            "timeWindowEnd": self.time_window_end.isoformat(),
            "durationSeconds": self.duration_seconds,
            "factValidFrom": self.fact_valid_from.isoformat(),
            "factValidTo": self.fact_valid_to.isoformat() if self.fact_valid_to else None,
            "sourceObservationTimestamp": self.source_observation_timestamp.isoformat(),
            "importanceScore": self.importance_score,
            "vectorId": self.vector_id,
            "consolidatedAt": self.consolidated_at.isoformat(),
            "consolidationMethod": self.consolidation_method,
            # Duplicate snake_case properties for compatibility with legacy queries
            "session_id": self.session_id,
            "episode_id": self.episode_id,
        }


class EpisodeStoreInput(BaseModel):
    """
    Input model for L3 EpisodicMemoryTier.store().

    Encapsulates the Episode model plus vector embedding and entity/relationship
    data required for dual-index storage (Qdrant + Neo4j).
    """

    episode: Episode
    embedding: list[float] = Field(..., min_length=1)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimension(cls, value: list[float]) -> list[float]:
        """Ensure embedding has reasonable dimensions."""
        if len(value) < 64 or len(value) > 4096:
            raise ValueError(f"Embedding dimension {len(value)} outside valid range [64, 4096]")
        return value


class KnowledgeDocument(BaseModel):
    """
    Represents distilled knowledge in L4 Semantic Memory.

    Knowledge documents are generalized patterns mined from L3 episodes,
    representing durable, reusable insights.
    """

    knowledge_id: str
    session_id: str | None = None

    # Content
    title: str = Field(..., min_length=5, max_length=500)
    content: str = Field(..., min_length=10, max_length=50000)
    knowledge_type: str = Field(default="insight")  # insight, pattern, rule, preference

    # Confidence and provenance
    confidence_score: float = Field(default=0.7, ge=0.0, le=1.0)
    source_episode_ids: list[str] = Field(default_factory=list)
    episode_count: int = Field(default=0, ge=0)

    # Provenance links (for traceability)
    provenance_links: list[str] = Field(default_factory=list)

    # Classification
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    domain: str | None = None

    # Lifecycle
    distilled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_validated: datetime | None = None
    validation_count: int = Field(default=0, ge=0)

    # Usage tracking
    access_count: int = Field(default=0, ge=0)
    last_accessed: datetime | None = None
    usefulness_score: float = Field(default=0.5, ge=0.0, le=1.0)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_typesense_document(self) -> dict[str, Any]:
        """Convert to Typesense document format."""
        return {
            "id": self.knowledge_id,
            "session_id": self.session_id or "",
            "title": self.title,
            "content": self.content,
            "knowledge_type": self.knowledge_type,
            "confidence_score": self.confidence_score,
            "source_episode_ids": self.source_episode_ids,
            "episode_count": self.episode_count,
            "provenance_links": self.provenance_links,
            "category": self.category or "",
            "tags": self.tags,
            "domain": self.domain or "",
            "distilled_at": int(self.distilled_at.timestamp()),
            "access_count": self.access_count,
            "usefulness_score": self.usefulness_score,
            "validation_count": self.validation_count,
        }


class EpisodeQuery(BaseModel):
    """Query parameters for retrieving episodes."""

    session_id: str | None = None
    min_importance: float | None = Field(default=0.0, ge=0.0, le=1.0)
    topics: list[str] | None = None
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    limit: int = Field(default=10, ge=1, le=100)


class KnowledgeQuery(BaseModel):
    """Query parameters for retrieving knowledge documents."""

    search_text: str | None = None
    knowledge_type: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    min_confidence: float | None = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=100)


class SearchWeights(BaseModel):
    """
    Configuration for hybrid cross-tier search weighting.

    Controls how results from different memory tiers are weighted
    when merged into a unified result set. Weights must sum to 1.0.
    """

    l2_weight: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Weight for L2 Working Memory results"
    )
    l3_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Weight for L3 Episodic Memory results"
    )
    l4_weight: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Weight for L4 Semantic Memory results"
    )

    @field_validator("l4_weight")
    @classmethod
    def validate_weights_sum(cls, v: float, info: ValidationInfo) -> float:
        """Ensure weights sum to 1.0."""
        values = info.data
        if "l2_weight" in values and "l3_weight" in values:
            total = values["l2_weight"] + values["l3_weight"] + v
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Weights must sum to 1.0, got {total}")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"l2_weight": 0.3, "l3_weight": 0.5, "l4_weight": 0.2},
                {"l2_weight": 0.4, "l3_weight": 0.4, "l4_weight": 0.2},
            ]
        }
    }


class ContextBlock(BaseModel):
    """
    Assembled context for prompt injection into agent conversations.

    Contains recent L1 turns and high-significance L2 facts filtered
    by CIAR score threshold. Used by agents to retrieve focused context
    without overwhelming the prompt window.
    """

    session_id: str

    # L1 Active Context (recent turns)
    recent_turns: list[dict[str, Any]] = Field(
        default_factory=list, description="Recent conversation turns from L1"
    )
    turn_count: int = Field(default=0, ge=0)

    # L2 Working Memory (CIAR-filtered facts)
    significant_facts: list[Fact] = Field(
        default_factory=list, description="High-CIAR facts from L2"
    )
    fact_count: int = Field(default=0, ge=0)
    min_ciar_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum CIAR score used for filtering"
    )

    # Metadata
    assembled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    l1_time_window_hours: float = Field(
        default=24.0, description="Time window for L1 turns retrieval"
    )
    estimated_tokens: int | None = Field(
        default=None, description="Rough token count estimate for LLM context"
    )

    # Optional L3/L4 summary
    episode_summaries: list[str] = Field(
        default_factory=list, description="Optional episode summaries from L3"
    )
    knowledge_snippets: list[str] = Field(
        default_factory=list, description="Optional knowledge from L4"
    )

    def to_prompt_string(self, include_metadata: bool = False) -> str:
        """
        Convert context block to formatted string for LLM prompt injection.

        Args:
            include_metadata: Include metadata like timestamps and CIAR scores

        Returns:
            Formatted context string ready for prompt injection
        """
        sections = []

        # Recent conversation
        if self.recent_turns:
            sections.append("## Recent Conversation")
            for i, turn in enumerate(self.recent_turns[-10:], 1):  # Last 10 turns
                role = turn.get("role", "unknown")
                content = turn.get("content", "")
                if include_metadata:
                    timestamp = turn.get("timestamp", "N/A")
                    sections.append(f"{i}. [{role.upper()}] ({timestamp}): {content}")
                else:
                    sections.append(f"{i}. [{role.upper()}]: {content}")

        # Significant facts
        if self.significant_facts:
            sections.append("\n## Key Facts (Working Memory)")
            for i, fact in enumerate(self.significant_facts, 1):
                if include_metadata:
                    sections.append(
                        f"{i}. {fact.content} [CIAR: {fact.ciar_score:.2f}, Type: {fact.fact_type or 'N/A'}]"
                    )
                else:
                    sections.append(f"{i}. {fact.content}")

        # Episode summaries
        if self.episode_summaries:
            sections.append("\n## Related Episodes (Episodic Memory)")
            for i, summary in enumerate(self.episode_summaries, 1):
                sections.append(f"{i}. {summary}")

        # Knowledge snippets
        if self.knowledge_snippets:
            sections.append("\n## Relevant Knowledge (Semantic Memory)")
            for i, snippet in enumerate(self.knowledge_snippets, 1):
                sections.append(f"{i}. {snippet}")

        return "\n".join(sections)

    def estimate_token_count(self, chars_per_token: float = 4.0) -> int:
        """
        Estimate token count for context block using character-based heuristic.

        Args:
            chars_per_token: Average characters per token (default: 4.0 for GPT models)

        Returns:
            Estimated token count
        """
        total_chars = 0

        # Count turn content
        for turn in self.recent_turns:
            if isinstance(turn, dict):
                total_chars += len(turn.get("content", ""))
            else:
                # Handle TurnData objects
                total_chars += len(getattr(turn, "content", ""))

        # Count fact content
        for fact in self.significant_facts:
            total_chars += len(fact.content)

        # Count summaries
        total_chars += sum(len(s) for s in self.episode_summaries)
        total_chars += sum(len(s) for s in self.knowledge_snippets)

        estimated = int(total_chars / chars_per_token)
        self.estimated_tokens = estimated
        return estimated


# Export all models
__all__ = [
    "ContextBlock",
    "Episode",
    "EpisodeQuery",
    "Fact",
    "FactCategory",
    "FactQuery",
    "FactType",
    "KnowledgeDocument",
    "KnowledgeQuery",
    "SearchWeights",
]
