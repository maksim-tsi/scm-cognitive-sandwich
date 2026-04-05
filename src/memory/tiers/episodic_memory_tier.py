"""
L3: Episodic Memory Tier - Hybrid Dual-Indexed Experience Store

Manages episodes (consolidated fact clusters) with dual indexing:
- Qdrant: Vector embeddings for semantic similarity search
- Neo4j: Graph structure with bi-temporal properties for relationship traversal

This enables both "find similar experiences" (Qdrant) and
"show me the full history" (Neo4j) query patterns.
"""

import json
import time
import uuid
import warnings
from datetime import datetime
from typing import Any

from src.memory.models import Episode, EpisodeStoreInput
from src.memory.tiers.base_tier import BaseTier, TierOperationError
from src.storage.metrics.collector import MetricsCollector
from src.storage.metrics.timer import OperationTimer
from src.storage.neo4j_adapter import Neo4jAdapter
from src.storage.qdrant_adapter import QdrantAdapter


class EpisodicMemoryTier(BaseTier[Episode]):
    """
    L3: Episodic Memory - Dual-Indexed Experience Store

    Stores consolidated episodes with:
    1. Vector embeddings in Qdrant for similarity search
    2. Graph structure in Neo4j for relationship traversal
    3. Bi-temporal properties for temporal reasoning
    """

    COLLECTION_NAME = "episodes"
    VECTOR_SIZE = 768  # Gemini text-embedding-004 default dimension

    def __init__(
        self,
        qdrant_adapter: QdrantAdapter,
        neo4j_adapter: Neo4jAdapter,
        metrics_collector: MetricsCollector | None = None,
        config: dict[str, Any] | None = None,
        telemetry_stream: Any | None = None,
    ):
        storage_adapters = {"qdrant": qdrant_adapter, "neo4j": neo4j_adapter}
        super().__init__(storage_adapters, metrics_collector, config, telemetry_stream)

        self.qdrant = qdrant_adapter
        self.neo4j = neo4j_adapter
        self.collection_name = (
            config.get("collection_name", self.COLLECTION_NAME) if config else self.COLLECTION_NAME
        )
        # Align vector size to Qdrant collection configuration when available
        adapter_vector_size = getattr(qdrant_adapter, "vector_size", self.VECTOR_SIZE)
        self.config_vector_size = config.get("vector_size") if config else None
        self.vector_size = self.config_vector_size or adapter_vector_size
        # Ensure adapter uses the episodic collection name and vector size for all operations
        self.qdrant.collection_name = self.collection_name
        self.qdrant.vector_size = self.vector_size

    def _tier_name(self) -> str:
        """Return tier identifier for telemetry."""
        return "L3_Episodic"

    async def initialize(self) -> None:
        """Initialize Qdrant collection and Neo4j constraints."""
        # Call parent initialize to connect adapters
        await super().initialize()

        # Create collection if needed
        try:
            await self.qdrant.create_collection(self.collection_name)
        except Exception as e:
            # Collection might already exist or require recreation; bubble up unexpected errors
            if "already exists" not in str(e).lower():
                raise

    async def store(self, data: EpisodeStoreInput | Episode | dict[str, Any]) -> str:
        """
        Store an episode with dual indexing.

        Args:
            data: EpisodeStoreInput model or dict (deprecated) including:
                - episode: Episode object
                - embedding: Vector embedding (list of floats)
                - entities: List of entity dicts
                - relationships: List of relationship dicts

        Returns:
            Episode identifier
        """
        async with OperationTimer(self.metrics, "l3_store"):
            if isinstance(data, dict):
                if data.get("embedding") is None:
                    raise ValueError("Embedding required")
                warnings.warn(
                    "Passing dict to EpisodicMemoryTier.store() is deprecated. "
                    "Use EpisodeStoreInput model directly.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                payload = EpisodeStoreInput.model_validate(data)
            elif isinstance(data, Episode):
                raise TierOperationError(
                    "EpisodicMemoryTier.store() requires EpisodeStoreInput with embedding and "
                    "entities/relationships."
                )
            else:
                payload = data

            # Extract components
            episode: Episode = payload.episode
            embedding = payload.embedding
            entities = payload.entities
            relationships = payload.relationships

            start_time = time.perf_counter()

            # Validate and align embedding length
            if embedding is None or len(embedding) == 0:
                raise ValueError(f"Embedding required with size {self.vector_size}")

            if self.config_vector_size is not None:
                if len(embedding) != self.vector_size:
                    raise ValueError(f"Embedding required with size {self.vector_size}")
            elif len(embedding) != self.vector_size:
                if len(embedding) > self.vector_size:
                    embedding = embedding[: self.vector_size]
                else:
                    embedding = embedding + [0.0] * (self.vector_size - len(embedding))

            # Ensure the collection exists before storing
            try:
                await self.qdrant.create_collection(self.collection_name)
            except Exception as e:
                # Ignore if already exists; bubble up unexpected issues
                if "already exists" not in str(e).lower():
                    raise

            # 1. Store in Qdrant (vector index)
            vector_id = await self._store_in_qdrant(episode, embedding)
            episode.vector_id = vector_id

            # 2. Store in Neo4j (graph index)
            graph_node_id = await self._store_in_neo4j(episode, entities, relationships)
            episode.graph_node_id = graph_node_id

            # 3. Update cross-references
            await self._link_indexes(episode)

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="STORE",
                session_id=episode.session_id,
                status="HIT",
                latency_ms=latency_ms,
                item_count=1,
                metadata={
                    "episode_id": episode.episode_id,
                    "fact_count": episode.fact_count,
                    "modality": "dual",
                },
            )

            return episode.episode_id
        raise AssertionError("Unreachable: store should return or raise.")

    async def retrieve(self, episode_id: str) -> Episode | None:
        """
        Retrieve episode by ID from Neo4j.

        Args:
            episode_id: Episode identifier

        Returns:
            Episode object or None
        """
        async with OperationTimer(self.metrics, "l3_retrieve"):
            start_time = time.perf_counter()
            query = """
            MATCH (e:Episode {episodeId: $episode_id})
            RETURN e
            """

            result = await self.neo4j.execute_query(query, {"episode_id": episode_id})

            if not result:
                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="RETRIEVE",
                    session_id="unknown",
                    status="MISS",
                    latency_ms=latency_ms,
                    metadata={"episode_id": episode_id},
                )
                return None

            props = result[0]["e"]
            episode = Episode(
                episode_id=props["episodeId"],
                session_id=props["sessionId"],
                summary=props["summary"],
                narrative=props.get("narrative"),
                source_fact_ids=[],  # Would need separate query
                fact_count=props["factCount"],
                time_window_start=datetime.fromisoformat(props["timeWindowStart"]),
                time_window_end=datetime.fromisoformat(props["timeWindowEnd"]),
                duration_seconds=props["durationSeconds"],
                fact_valid_from=datetime.fromisoformat(props["factValidFrom"]),
                fact_valid_to=datetime.fromisoformat(props["factValidTo"])
                if props.get("factValidTo")
                else None,
                source_observation_timestamp=datetime.fromisoformat(
                    props["sourceObservationTimestamp"]
                ),
                importance_score=props["importanceScore"],
                vector_id=props.get("vectorId"),
                graph_node_id=episode_id,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="RETRIEVE",
                session_id=episode.session_id,
                status="HIT",
                latency_ms=latency_ms,
                item_count=1,
                metadata={"episode_id": episode_id},
            )

            return episode
        raise AssertionError("Unreachable: retrieve should return or raise.")

    async def search_similar(
        self,
        query_embedding: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[Episode]:
        """
        Search for similar episodes using vector similarity.

        Args:
            query_embedding: Query vector
            limit: Max results
            filters: Optional filters (session_id, time_range, etc.)

        Returns:
            List of similar episodes with similarity scores
        """
        async with OperationTimer(self.metrics, "l3_search_similar"):
            start_time = time.perf_counter()
            # Search Qdrant
            results = await self.qdrant.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                filter_dict=filters,
            )

            # Convert to Episode objects
            episodes = []
            max_similarity = 0.0
            for result in results:
                payload = result["payload"]
                episode = Episode(
                    episode_id=payload["episode_id"],
                    session_id=payload["session_id"],
                    summary=payload["summary"],
                    narrative=payload.get("narrative"),
                    source_fact_ids=payload.get("source_fact_ids", []),
                    fact_count=payload["fact_count"],
                    time_window_start=datetime.fromisoformat(payload["time_window_start"]),
                    time_window_end=datetime.fromisoformat(payload["time_window_end"]),
                    fact_valid_from=datetime.fromisoformat(payload["fact_valid_from"]),
                    fact_valid_to=datetime.fromisoformat(payload["fact_valid_to"])
                    if payload.get("fact_valid_to")
                    else None,
                    source_observation_timestamp=datetime.fromisoformat(
                        payload.get("source_observation_timestamp", payload["time_window_start"])
                    ),
                    importance_score=payload["importance_score"],
                    topics=payload.get("topics", []),
                    vector_id=str(result["id"]),
                    graph_node_id=payload.get("graph_node_id"),
                )
                # Attach similarity score
                score = result["score"]
                episode.metadata["similarity_score"] = score
                episodes.append(episode)
                max_similarity = max(max_similarity, score)

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="QUERY",
                session_id=filters.get("session_id", "unknown") if filters else "unknown",
                status="HIT",
                latency_ms=latency_ms,
                item_count=len(episodes),
                metadata={
                    "modality": "vector",
                    "max_similarity": max_similarity,
                },
            )

            return episodes
        raise AssertionError("Unreachable: search_similar should return or raise.")

    async def query_graph(
        self, cypher_query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Execute custom Cypher query on Neo4j graph.

        Args:
            cypher_query: Cypher query string
            parameters: Query parameters

        Returns:
            Query results
        """
        async with OperationTimer(self.metrics, "l3_query_graph"):
            results = await self.neo4j.execute_query(cypher_query, parameters or {})

            return results
        raise AssertionError("Unreachable: query_graph should return or raise.")

    async def get_episode_entities(self, episode_id: str) -> list[dict[str, Any]]:
        """
        Get all entities mentioned in an episode (hypergraph participants).

        Args:
            episode_id: Episode identifier

        Returns:
            List of entity dictionaries
        """
        query = """
        MATCH (e:Episode {episodeId: $episode_id})-[r:MENTIONS]->(entity:Entity)
        RETURN entity, r
        ORDER BY r.confidence DESC
        """

        results = await self.neo4j.execute_query(query, {"episode_id": episode_id})

        entities = []
        for row in results:
            entity_props = row["entity"]
            rel_props = row["r"]
            entities.append(
                {
                    "entity_id": entity_props["entityId"],
                    "name": entity_props["name"],
                    "type": entity_props["type"],
                    "confidence": rel_props.get("confidence", 1.0),
                    "fact_valid_from": rel_props["factValidFrom"],
                    "fact_valid_to": rel_props.get("factValidTo"),
                }
            )

        return entities

    async def query_temporal(
        self, query_time: datetime, session_id: str | None = None, limit: int = 10
    ) -> list[Episode]:
        """
        Query episodes that were valid at a specific time (bi-temporal query).

        Args:
            query_time: Time point to query
            session_id: Optional session filter
            limit: Max results

        Returns:
            List of temporally valid episodes
        """
        query = """
        MATCH (e:Episode)
        WHERE e.factValidFrom <= $query_time
          AND (e.factValidTo IS NULL OR e.factValidTo > $query_time)
        """

        params: dict[str, Any] = {"query_time": query_time.isoformat()}

        if session_id:
            query += " AND e.sessionId = $session_id"
            params["session_id"] = session_id

        query += """
        RETURN e
        ORDER BY e.importanceScore DESC
        LIMIT $limit
        """
        params["limit"] = limit

        results = await self.neo4j.execute_query(query, params)

        episodes = []
        for row in results:
            props = row["e"]
            episode = Episode(
                episode_id=props["episodeId"],
                session_id=props["sessionId"],
                summary=props["summary"],
                narrative=props.get("narrative"),
                source_fact_ids=[],
                fact_count=props["factCount"],
                time_window_start=datetime.fromisoformat(props["timeWindowStart"]),
                time_window_end=datetime.fromisoformat(props["timeWindowEnd"]),
                duration_seconds=props["durationSeconds"],
                fact_valid_from=datetime.fromisoformat(props["factValidFrom"]),
                fact_valid_to=datetime.fromisoformat(props["factValidTo"])
                if props.get("factValidTo")
                else None,
                source_observation_timestamp=datetime.fromisoformat(
                    props["sourceObservationTimestamp"]
                ),
                importance_score=props["importanceScore"],
                graph_node_id=props["episodeId"],
            )
            episodes.append(episode)

        return episodes

    async def delete(self, episode_id: str) -> bool:
        """
        Delete episode from both Qdrant and Neo4j.

        Args:
            episode_id: Episode to delete

        Returns:
            True if deleted
        """
        async with OperationTimer(self.metrics, "l3_delete"):
            start_time = time.perf_counter()
            # Get episode to find vector_id
            episode = await self.retrieve(episode_id)
            if not episode:
                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._emit_tier_access(
                    operation="DELETE",
                    session_id="unknown",
                    status="MISS",
                    latency_ms=latency_ms,
                    metadata={"episode_id": episode_id},
                )
                return False

            # Delete from Qdrant
            if episode.vector_id:
                await self.qdrant.delete(
                    collection_name=self.collection_name, point_ids=[episode.vector_id]
                )

            # Delete from Neo4j (cascade deletes relationships)
            delete_query = """
            MATCH (e:Episode {episodeId: $episode_id})
            DETACH DELETE e
            """
            await self.neo4j.execute_query(delete_query, {"episode_id": episode_id})

            latency_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tier_access(
                operation="DELETE",
                session_id=episode.session_id,
                status="HIT",
                latency_ms=latency_ms,
                metadata={"episode_id": episode_id},
            )

            return True
        raise AssertionError("Unreachable: delete should return or raise.")

    async def query(
        self, filters: dict[str, Any] | None = None, limit: int = 10, **kwargs: Any
    ) -> list[Episode]:
        """
        Query episodes from Neo4j with filters.

        Args:
            filters: Query filters (session_id, min_importance, time_range)
            limit: Max results

        Returns:
            List of episodes
        """
        start_time = time.perf_counter()
        # Build Cypher query dynamically
        query = "MATCH (e:Episode)\nWHERE 1=1"
        params = {"limit": limit}

        if filters:
            if "session_id" in filters:
                query += " AND e.sessionId = $session_id"
                params["session_id"] = filters["session_id"]

            if "min_importance" in filters:
                query += " AND e.importanceScore >= $min_importance"
                params["min_importance"] = filters["min_importance"]

        query += "\nRETURN e ORDER BY e.importanceScore DESC LIMIT $limit"

        results = await self.neo4j.execute_query(query, params)

        episodes = []
        for row in results:
            props = row["e"]
            episode = Episode(
                episode_id=props["episodeId"],
                session_id=props["sessionId"],
                summary=props["summary"],
                narrative=props.get("narrative"),
                source_fact_ids=[],
                fact_count=props["factCount"],
                time_window_start=datetime.fromisoformat(props["timeWindowStart"]),
                time_window_end=datetime.fromisoformat(props["timeWindowEnd"]),
                duration_seconds=props["durationSeconds"],
                fact_valid_from=datetime.fromisoformat(props["factValidFrom"]),
                fact_valid_to=datetime.fromisoformat(props["factValidTo"])
                if props.get("factValidTo")
                else None,
                source_observation_timestamp=datetime.fromisoformat(
                    props["sourceObservationTimestamp"]
                ),
                importance_score=props["importanceScore"],
            )
            episodes.append(episode)

        latency_ms = (time.perf_counter() - start_time) * 1000
        await self._emit_tier_access(
            operation="QUERY",
            session_id=filters.get("session_id", "unknown") if filters else "unknown",
            status="HIT",
            latency_ms=latency_ms,
            item_count=len(episodes),
            metadata={
                "modality": "graph",
                "filters": str(filters)[:100] if filters else None,
            },
        )

        return episodes

    async def health_check(self) -> dict[str, Any]:
        """Check health of both Qdrant and Neo4j."""
        qdrant_health = await self.qdrant.health_check()
        neo4j_health = await self.neo4j.health_check()

        # Get statistics
        episode_count_query = "MATCH (e:Episode) RETURN count(e) as count"
        result = await self.neo4j.execute_query(episode_count_query, {})
        episode_count = result[0]["count"] if result else 0

        return {
            "tier": "L3_episodic_memory",
            "status": "healthy"
            if (qdrant_health["status"] == "healthy" and neo4j_health["status"] == "healthy")
            else "degraded",
            "storage": {"qdrant": qdrant_health, "neo4j": neo4j_health},
            "statistics": {
                "total_episodes": episode_count,
                "collection_name": self.collection_name,
            },
        }

    # Private helper methods

    async def _store_in_qdrant(self, episode: Episode, embedding: list[float]) -> str:
        """Store episode vector in Qdrant."""
        point_id = str(uuid.uuid4())

        payload = {
            "id": point_id,
            "vector": embedding,
            "content": episode.summary,
            "session_id": episode.session_id,
            "episode_id": episode.episode_id,
            "metadata": episode.to_qdrant_payload(),
        }

        if hasattr(self.qdrant, "upsert"):
            await self.qdrant.upsert(payload)
        else:
            await self.qdrant.store(payload)

        return point_id

    async def _store_in_neo4j(
        self, episode: Episode, entities: list[dict[str, Any]], relationships: list[dict[str, Any]]
    ) -> str:
        """Store episode graph in Neo4j with bi-temporal properties."""
        # Create episode node
        create_episode = """
        MERGE (e:Episode {episodeId: $episode_id})
        SET e += $properties
        RETURN e.episodeId as id
        """

        await self.neo4j.execute_query(
            create_episode,
            {"episode_id": episode.episode_id, "properties": episode.to_neo4j_properties()},
            session_id=episode.session_id,
        )

        # Create entity nodes and relationships
        for entity in entities:
            create_entity = """
            MERGE (entity:Entity {entityId: $entity_id})
            SET entity.name = $name,
                entity.type = $type,
                entity.properties = $properties
            
            WITH entity
            MATCH (e:Episode {episodeId: $episode_id})
            MERGE (e)-[r:MENTIONS]->(entity)
            SET r.factValidFrom = $fact_valid_from,
                r.factValidTo = $fact_valid_to,
                r.sourceObservationTimestamp = $source_timestamp,
                r.confidence = $confidence
            """

            await self.neo4j.execute_query(
                create_entity,
                {
                    "entity_id": entity["entity_id"],
                    "name": entity["name"],
                    "type": entity["type"],
                    "properties": json.dumps(entity.get("properties", {})),
                    "episode_id": episode.episode_id,
                    "fact_valid_from": episode.fact_valid_from.isoformat(),
                    "fact_valid_to": episode.fact_valid_to.isoformat()
                    if episode.fact_valid_to
                    else None,
                    "source_timestamp": episode.source_observation_timestamp.isoformat(),
                    "confidence": entity.get("confidence", 1.0),
                },
                session_id=episode.session_id,
            )

        return episode.episode_id

    async def _link_indexes(self, episode: Episode) -> None:
        """Update cross-references between Qdrant and Neo4j."""
        # Update Neo4j node with Qdrant vector ID
        update_query = """
        MATCH (e:Episode {episodeId: $episode_id})
        SET e.vectorId = $vector_id
        """

        await self.neo4j.execute_query(
            update_query,
            {"episode_id": episode.episode_id, "vector_id": episode.vector_id},
            session_id=episode.session_id,
        )
