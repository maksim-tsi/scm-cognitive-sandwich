"""
L4: Semantic Memory Tier - Distilled Knowledge Store

Stores generalized knowledge documents distilled from L3 episodes.
Provides full-text search, faceted filtering, and provenance tracking.
"""

import logging
import time
import warnings
from datetime import UTC, datetime
from typing import Any

from src.memory.models import KnowledgeDocument
from src.memory.tiers.base_tier import BaseTier
from src.storage.metrics.collector import MetricsCollector
from src.storage.metrics.timer import OperationTimer
from src.storage.typesense_adapter import TypesenseAdapter

logger = logging.getLogger(__name__)


class SemanticMemoryTier(BaseTier[KnowledgeDocument]):
    """
    L4: Semantic Memory - Distilled Knowledge Repository

    Stores permanent, generalized knowledge mined from L3 episodes.
    Supports full-text search, faceted filtering, and provenance tracking.
    """

    COLLECTION_NAME = "knowledge_base"

    def __init__(
        self,
        typesense_adapter: TypesenseAdapter,
        metrics_collector: MetricsCollector | None = None,
        config: dict[str, Any] | None = None,
        telemetry_stream: Any | None = None,
    ):
        storage_adapters = {"typesense": typesense_adapter}
        super().__init__(storage_adapters, metrics_collector, config, telemetry_stream)

        self.typesense = typesense_adapter
        self.collection_name = (
            config.get("collection_name", self.COLLECTION_NAME) if config else self.COLLECTION_NAME
        )

    def _tier_name(self) -> str:
        """Return tier identifier for telemetry."""
        return "L4_Semantic"

    async def initialize(self) -> None:
        """Initialize Typesense collection."""
        # Call parent initialize to connect adapter
        await super().initialize()

    async def store(self, data: KnowledgeDocument | dict[str, Any]) -> str:
        """
        Store a knowledge document in L4.

        Args:
            data: KnowledgeDocument object or dict (deprecated)

        Returns:
            Knowledge identifier
        """
        async with OperationTimer(self.metrics, "l4_store"):
            # Convert to KnowledgeDocument for validation
            knowledge: KnowledgeDocument
            if isinstance(data, dict):
                warnings.warn(
                    "Passing dict to SemanticMemoryTier.store() is deprecated. "
                    "Use KnowledgeDocument model directly.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                knowledge = KnowledgeDocument.model_validate(data)
            else:
                knowledge = data

            document = knowledge.to_typesense_document()

            # Prefer explicit index_document when available (tests mock this)
            index_func = getattr(self.typesense, "index_document", None)

            start_time = time.perf_counter()
            if callable(index_func):
                await index_func(document=document, collection_name=self.collection_name)
            else:
                await self.typesense.store(document)

            logger.info(
                "L4 store confirmed: knowledge_id=%s, type=%s, collection=%s",
                knowledge.knowledge_id,
                knowledge.knowledge_type,
                self.collection_name,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="STORE",
                session_id="unknown",
                status="HIT",
                latency_ms=latency_ms,
                item_count=1,
                metadata={
                    "knowledge_id": knowledge.knowledge_id,
                    "knowledge_type": knowledge.knowledge_type,
                },
            )

            return knowledge.knowledge_id
        raise AssertionError("Unreachable: store should return or raise.")

    async def retrieve(self, knowledge_id: str) -> KnowledgeDocument | None:
        """
        Retrieve knowledge document by ID.

        Args:
            knowledge_id: Knowledge identifier

        Returns:
            KnowledgeDocument or None
        """
        async with OperationTimer(self.metrics, "l4_retrieve"):
            start_time = time.perf_counter()
            result = await self.typesense.get_document(
                collection_name=self.collection_name, document_id=knowledge_id
            )

            if not result:
                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="RETRIEVE",
                    session_id="unknown",
                    status="MISS",
                    latency_ms=latency_ms,
                    metadata={"knowledge_id": knowledge_id},
                )
                return None

            # Convert back to KnowledgeDocument
            knowledge = KnowledgeDocument(
                knowledge_id=result["id"],
                title=result["title"],
                content=result["content"],
                knowledge_type=result["knowledge_type"],
                confidence_score=result["confidence_score"],
                source_episode_ids=result.get("source_episode_ids", []),
                episode_count=result["episode_count"],
                provenance_links=result.get("provenance_links", []),
                category=result.get("category"),
                tags=result.get("tags", []),
                domain=result.get("domain"),
                distilled_at=datetime.fromtimestamp(result["distilled_at"], tz=UTC),
                access_count=result["access_count"],
                usefulness_score=result["usefulness_score"],
                validation_count=result["validation_count"],
            )

            # Update access tracking
            await self._update_access(knowledge)

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="RETRIEVE",
                session_id="unknown",
                status="HIT",
                latency_ms=latency_ms,
                item_count=1,
                metadata={
                    "knowledge_id": knowledge.knowledge_id,
                    "knowledge_type": knowledge.knowledge_type,
                },
            )

            return knowledge
        raise AssertionError("Unreachable: retrieve should return or raise.")

    async def search(
        self,
        query_text: str,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        filter_by: str | None = None,
    ) -> list[KnowledgeDocument]:
        """
        Full-text search for knowledge documents.

        Args:
            query_text: Search query
            filters: Optional filters (knowledge_type, category, tags, min_confidence)
            limit: Max results
            filter_by: Optional raw Typesense filter string (advanced use)

        Returns:
            List of matching knowledge documents
        """
        async with OperationTimer(self.metrics, "l4_search"):
            start_time = time.perf_counter()
            # Build filter string
            filter_terms: list[str] = []
            if filter_by is None and filters:
                if "knowledge_type" in filters:
                    filter_terms.append(f"knowledge_type:={filters['knowledge_type']}")
                if "category" in filters:
                    filter_terms.append(f"category:={filters['category']}")
                if "min_confidence" in filters:
                    filter_terms.append(f"confidence_score:>={filters['min_confidence']}")
                if "tags" in filters:
                    tag_filter = " || ".join([f"tags:={tag}" for tag in filters["tags"]])
                    filter_terms.append(f"({tag_filter})")

            resolved_filter_by = filter_by or (" && ".join(filter_terms) if filter_terms else None)

            # Execute search
            results = await self.typesense.search(
                collection_name=self.collection_name,
                query=query_text,
                query_by="title,content",
                filter_by=resolved_filter_by,
                limit=limit,
                sort_by="usefulness_score:desc",
            )

            # Convert to KnowledgeDocument objects
            documents = []
            max_score = 0
            for hit in results.get("hits", []):
                doc = hit["document"]
                knowledge = KnowledgeDocument(
                    knowledge_id=doc["id"],
                    title=doc["title"],
                    content=doc["content"],
                    knowledge_type=doc["knowledge_type"],
                    confidence_score=doc["confidence_score"],
                    source_episode_ids=doc.get("source_episode_ids", []),
                    episode_count=doc["episode_count"],
                    provenance_links=doc.get("provenance_links", []),
                    category=doc.get("category"),
                    tags=doc.get("tags", []),
                    domain=doc.get("domain"),
                    distilled_at=datetime.fromtimestamp(doc["distilled_at"], tz=UTC),
                    access_count=doc["access_count"],
                    usefulness_score=doc["usefulness_score"],
                    validation_count=doc["validation_count"],
                )
                # Attach search score
                score = hit.get("text_match", 0)
                knowledge.metadata["search_score"] = score
                documents.append(knowledge)
                max_score = max(max_score, score)

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="SEARCH",
                session_id="unknown",
                status="HIT",
                latency_ms=latency_ms,
                item_count=len(documents),
                metadata={
                    "query": query_text[:50],
                    "filters": str(filters)[:100] if filters else None,
                    "max_score": max_score,
                },
            )

            return documents
        raise AssertionError("Unreachable: search should return or raise.")

    async def query(
        self, filters: dict[str, Any] | None = None, limit: int = 10, **kwargs: Any
    ) -> list[KnowledgeDocument]:
        """
        Query knowledge documents with filters (without text search).

        Args:
            filters: Query filters
            limit: Max results

        Returns:
            List of knowledge documents
        """
        # Use search with wildcard query
        return await self.search(query_text="*", filters=filters, limit=limit)

    async def update_usefulness(self, knowledge_id: str, usefulness_score: float) -> bool:
        """
        Update usefulness score based on feedback.

        Args:
            knowledge_id: Knowledge to update
            usefulness_score: New score (0.0-1.0)

        Returns:
            True if updated
        """
        # Retrieve current document
        doc = await self.retrieve(knowledge_id)
        if not doc:
            return False

        # Update score
        doc.usefulness_score = usefulness_score
        doc.validation_count += 1
        doc.last_validated = datetime.now(UTC)

        # Re-index
        await self.typesense.update_document(
            collection_name=self.collection_name,
            document_id=knowledge_id,
            document=doc.to_typesense_document(),
        )

        return True

    async def delete(self, knowledge_id: str) -> bool:
        """
        Delete knowledge document from L4.

        Args:
            knowledge_id: Knowledge identifier

        Returns:
            True if deleted
        """
        async with OperationTimer(self.metrics, "l4_delete"):
            start_time = time.perf_counter()
            await self.typesense.delete_document(
                collection_name=self.collection_name, document_id=knowledge_id
            )

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="DELETE",
                session_id="unknown",
                status="HIT",
                latency_ms=latency_ms,
                metadata={"knowledge_id": knowledge_id},
            )

            return True
        raise AssertionError("Unreachable: delete should return or raise.")

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get collection statistics.

        Returns:
            Statistics dictionary
        """
        # Get all documents (limited sample)
        sample = await self.query(limit=1000)

        if not sample:
            return {"total_documents": 0, "avg_confidence": 0.0, "avg_usefulness": 0.0}

        from collections import Counter

        types = Counter([d.knowledge_type for d in sample])
        categories = Counter([d.category for d in sample if d.category])

        return {
            "total_documents": len(sample),
            "avg_confidence": sum(d.confidence_score for d in sample) / len(sample),
            "avg_usefulness": sum(d.usefulness_score for d in sample) / len(sample),
            "avg_episode_count": sum(d.episode_count for d in sample) / len(sample),
            "knowledge_types": dict(types),
            "categories": dict(categories),
            "most_useful": max(sample, key=lambda d: d.usefulness_score).knowledge_id,
            "most_accessed": max(sample, key=lambda d: d.access_count).knowledge_id,
        }

    async def health_check(self) -> dict[str, Any]:
        """Check health of Typesense."""
        typesense_health = await self.typesense.health_check()

        # Get statistics
        stats = await self.get_statistics()

        return {
            "tier": "L4_semantic_memory",
            "status": typesense_health["status"],
            "storage": {"typesense": typesense_health},
            "statistics": stats,
        }

    async def _update_access(self, knowledge: KnowledgeDocument) -> None:
        """Update access tracking for a knowledge document."""
        knowledge.access_count += 1
        knowledge.last_accessed = datetime.now(UTC)

        await self.typesense.update_document(
            collection_name=self.collection_name,
            document_id=knowledge.knowledge_id,
            document=knowledge.to_typesense_document(),
        )
