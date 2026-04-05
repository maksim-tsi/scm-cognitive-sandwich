"""
Artifact repository for lineage graph writes and tier projections.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from .models import (
    Artifact,
    ArtifactCommit,
    ArtifactFeedback,
    ArtifactLineageNode,
    ArtifactLineageQuery,
    ArtifactLineageResult,
    ArtifactRevision,
)
from ..models import Fact, FactCategory, FactType, KnowledgeDocument, TurnData

logger = logging.getLogger(__name__)


class ArtifactRepository:
    """Coordinates graph lineage storage and memory-tier projections."""

    def __init__(
        self,
        neo4j_adapter: Any,
        l1_tier: Any | None = None,
        l2_tier: Any | None = None,
        l4_tier: Any | None = None,
    ) -> None:
        self.neo4j = neo4j_adapter
        self.l1_tier = l1_tier
        self.l2_tier = l2_tier
        self.l4_tier = l4_tier

    async def create_artifact(self, artifact: Artifact) -> None:
        """Create or update the artifact root node."""
        query = """
        MERGE (a:Artifact {artifact_id: $artifact_id})
        SET a.artifact_kind = $artifact_kind,
            a.session_id = $session_id,
            a.workspace_id = $workspace_id,
            a.status = $status,
            a.current_revision_id = $current_revision_id,
            a.created_at = coalesce(a.created_at, $created_at),
            a.updated_at = $updated_at,
            a.metadata = $metadata
        RETURN a.artifact_id AS artifact_id
        """
        await self.neo4j.execute_query(
            query,
            {
                "artifact_id": artifact.artifact_id,
                "artifact_kind": artifact.artifact_kind,
                "session_id": artifact.session_id,
                "workspace_id": artifact.workspace_id,
                "status": artifact.status,
                "current_revision_id": artifact.current_revision_id,
                "created_at": artifact.created_at.isoformat(),
                "updated_at": artifact.updated_at.isoformat(),
                "metadata": artifact.metadata,
            },
            session_id=artifact.session_id,
        )

    async def update_artifact(
        self,
        artifact_id: str,
        *,
        status: str,
        current_revision_id: str | None,
        session_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update artifact status and head revision."""
        query = """
        MATCH (a:Artifact {artifact_id: $artifact_id})
        SET a.status = $status,
            a.current_revision_id = $current_revision_id,
            a.updated_at = $updated_at,
            a.metadata = $metadata
        RETURN a.artifact_id AS artifact_id
        """
        await self.neo4j.execute_query(
            query,
            {
                "artifact_id": artifact_id,
                "status": status,
                "current_revision_id": current_revision_id,
                "updated_at": datetime.now(UTC).isoformat(),
                "metadata": metadata or {},
            },
            session_id=session_id,
        )

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        """Fetch artifact root metadata."""
        query = """
        MATCH (a:Artifact {artifact_id: $artifact_id})
        RETURN
            a.artifact_id AS artifact_id,
            a.artifact_kind AS artifact_kind,
            a.session_id AS session_id,
            a.workspace_id AS workspace_id,
            a.status AS status,
            a.current_revision_id AS current_revision_id,
            a.created_at AS created_at,
            a.updated_at AS updated_at,
            a.metadata AS metadata
        """
        results = await self.neo4j.execute_query(query, {"artifact_id": artifact_id})
        if not results:
            return None
        row = results[0]
        return Artifact(
            artifact_id=row["artifact_id"],
            artifact_kind=row["artifact_kind"],
            session_id=row["session_id"],
            workspace_id=row.get("workspace_id"),
            status=row["status"],
            current_revision_id=row.get("current_revision_id"),
            created_at=self._parse_dt(row.get("created_at")) or datetime.now(UTC),
            updated_at=self._parse_dt(row.get("updated_at")) or datetime.now(UTC),
            metadata=row.get("metadata") or {},
        )

    async def store_revision(self, artifact: Artifact, revision: ArtifactRevision) -> None:
        """Store a revision node and working-memory projections."""
        query = """
        MATCH (a:Artifact {artifact_id: $artifact_id})
        MERGE (r:ArtifactRevision {revision_id: $revision_id})
        SET r.artifact_id = $artifact_id,
            r.revision_number = $revision_number,
            r.payload = $payload,
            r.payload_hash = $payload_hash,
            r.verification_state = $verification_state,
            r.tier_state = $tier_state,
            r.parent_revision_id = $parent_revision_id,
            r.trigger_feedback_id = $trigger_feedback_id,
            r.created_by = $created_by,
            r.created_at = $created_at,
            r.summary = $summary,
            r.metadata = $metadata
        MERGE (a)-[:HAS_REVISION]->(r)
        WITH r
        OPTIONAL MATCH (parent:ArtifactRevision {revision_id: $parent_revision_id})
        FOREACH (_ IN CASE WHEN parent IS NULL THEN [] ELSE [1] END |
            MERGE (r)-[:SUPERSEDES]->(parent)
        )
        RETURN r.revision_id AS revision_id
        """
        await self.neo4j.execute_query(
            query,
            {
                "artifact_id": artifact.artifact_id,
                "revision_id": revision.revision_id,
                "revision_number": revision.revision_number,
                "payload": revision.payload,
                "payload_hash": revision.payload_hash,
                "verification_state": revision.verification_state,
                "tier_state": revision.tier_state,
                "parent_revision_id": revision.parent_revision_id,
                "trigger_feedback_id": revision.trigger_feedback_id,
                "created_by": revision.created_by,
                "created_at": revision.created_at.isoformat(),
                "summary": revision.summary,
                "metadata": revision.metadata,
            },
            session_id=artifact.session_id,
        )
        await self._project_revision_to_working_memory(artifact, revision)

    async def get_revision(self, revision_id: str) -> ArtifactRevision | None:
        """Fetch a specific revision."""
        query = """
        MATCH (r:ArtifactRevision {revision_id: $revision_id})
        RETURN
            r.revision_id AS revision_id,
            r.artifact_id AS artifact_id,
            r.revision_number AS revision_number,
            r.payload AS payload,
            r.payload_hash AS payload_hash,
            r.verification_state AS verification_state,
            r.tier_state AS tier_state,
            r.parent_revision_id AS parent_revision_id,
            r.trigger_feedback_id AS trigger_feedback_id,
            r.created_by AS created_by,
            r.created_at AS created_at,
            r.summary AS summary,
            r.metadata AS metadata
        """
        results = await self.neo4j.execute_query(query, {"revision_id": revision_id})
        if not results:
            return None
        row = results[0]
        return ArtifactRevision(
            revision_id=row["revision_id"],
            artifact_id=row["artifact_id"],
            revision_number=int(row["revision_number"]),
            payload=row.get("payload") or {},
            payload_hash=row["payload_hash"],
            verification_state=row["verification_state"],
            tier_state=row["tier_state"],
            parent_revision_id=row.get("parent_revision_id"),
            trigger_feedback_id=row.get("trigger_feedback_id"),
            created_by=row.get("created_by"),
            created_at=self._parse_dt(row.get("created_at")) or datetime.now(UTC),
            summary=row.get("summary"),
            metadata=row.get("metadata") or {},
        )

    async def get_next_revision_number(self, artifact_id: str) -> int:
        """Return the next revision number for an artifact."""
        query = """
        MATCH (:Artifact {artifact_id: $artifact_id})-[:HAS_REVISION]->(r:ArtifactRevision)
        RETURN coalesce(max(r.revision_number), 0) + 1 AS next_revision_number
        """
        results = await self.neo4j.execute_query(query, {"artifact_id": artifact_id})
        if not results:
            return 1
        return int(results[0]["next_revision_number"])

    async def update_revision_verification(
        self,
        revision_id: str,
        verification_state: str,
        *,
        tier_state: str | None = None,
        trigger_feedback_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Update verification state for a revision."""
        query = """
        MATCH (r:ArtifactRevision {revision_id: $revision_id})
        SET r.verification_state = $verification_state,
            r.tier_state = coalesce($tier_state, r.tier_state),
            r.trigger_feedback_id = coalesce($trigger_feedback_id, r.trigger_feedback_id)
        RETURN r.revision_id AS revision_id
        """
        await self.neo4j.execute_query(
            query,
            {
                "revision_id": revision_id,
                "verification_state": verification_state,
                "tier_state": tier_state,
                "trigger_feedback_id": trigger_feedback_id,
            },
            session_id=session_id,
        )

    async def store_feedback(self, artifact: Artifact, feedback: ArtifactFeedback) -> None:
        """Store a feedback node, edge, and working-memory projections."""
        query = """
        MATCH (r:ArtifactRevision {revision_id: $revision_id})
        MERGE (f:ArtifactFeedback {feedback_id: $feedback_id})
        SET f.artifact_id = $artifact_id,
            f.revision_id = $revision_id,
            f.feedback_type = $feedback_type,
            f.source_system = $source_system,
            f.content = $content,
            f.structured_payload = $structured_payload,
            f.severity = $severity,
            f.created_at = $created_at,
            f.metadata = $metadata
        MERGE (f)-[:APPLIES_TO]->(r)
        RETURN f.feedback_id AS feedback_id
        """
        await self.neo4j.execute_query(
            query,
            {
                "feedback_id": feedback.feedback_id,
                "artifact_id": feedback.artifact_id,
                "revision_id": feedback.revision_id,
                "feedback_type": feedback.feedback_type,
                "source_system": feedback.source_system,
                "content": feedback.content,
                "structured_payload": feedback.structured_payload,
                "severity": feedback.severity,
                "created_at": feedback.created_at.isoformat(),
                "metadata": feedback.metadata,
            },
            session_id=artifact.session_id,
        )
        await self._project_feedback_to_working_memory(artifact, feedback)

    async def link_revision_to_feedback(
        self, revision_id: str, feedback_id: str, *, session_id: str | None = None
    ) -> None:
        """Create the causal trigger edge from revision to feedback."""
        query = """
        MATCH (r:ArtifactRevision {revision_id: $revision_id})
        MATCH (f:ArtifactFeedback {feedback_id: $feedback_id})
        MERGE (r)-[:TRIGGERED_BY]->(f)
        RETURN r.revision_id AS revision_id
        """
        await self.neo4j.execute_query(
            query,
            {"revision_id": revision_id, "feedback_id": feedback_id},
            session_id=session_id,
        )

    async def store_commit(
        self,
        artifact: Artifact,
        revision: ArtifactRevision,
        commit: ArtifactCommit,
        knowledge: KnowledgeDocument | None = None,
    ) -> None:
        """Store commit node and optional L4 projection link."""
        query = """
        MATCH (r:ArtifactRevision {revision_id: $revision_id})
        MERGE (c:ArtifactCommit {commit_id: $commit_id})
        SET c.artifact_id = $artifact_id,
            c.revision_id = $revision_id,
            c.knowledge_id = $knowledge_id,
            c.commit_reason = $commit_reason,
            c.committed_at = $committed_at,
            c.metadata = $metadata
        MERGE (c)-[:COMMITS]->(r)
        RETURN c.commit_id AS commit_id
        """
        await self.neo4j.execute_query(
            query,
            {
                "commit_id": commit.commit_id,
                "artifact_id": commit.artifact_id,
                "revision_id": commit.revision_id,
                "knowledge_id": commit.knowledge_id,
                "commit_reason": commit.commit_reason,
                "committed_at": commit.committed_at.isoformat(),
                "metadata": commit.metadata,
            },
            session_id=artifact.session_id,
        )
        if knowledge:
            link_query = """
            MATCH (r:ArtifactRevision {revision_id: $revision_id})
            MERGE (k:KnowledgeDocument {knowledge_id: $knowledge_id})
            SET k.title = $title,
                k.content = $content,
                k.knowledge_type = $knowledge_type,
                k.created_at = $created_at
            MERGE (k)-[:DERIVED_FROM_ARTIFACT]->(r)
            RETURN k.knowledge_id AS knowledge_id
            """
            await self.neo4j.execute_query(
                link_query,
                {
                    "revision_id": revision.revision_id,
                    "knowledge_id": knowledge.knowledge_id,
                    "title": knowledge.title,
                    "content": knowledge.content,
                    "knowledge_type": knowledge.knowledge_type,
                    "created_at": knowledge.distilled_at.isoformat(),
                },
                session_id=artifact.session_id,
            )

    async def get_lineage(self, query_model: ArtifactLineageQuery) -> ArtifactLineageResult:
        """Return ordered lineage nodes for an artifact."""
        artifact = await self.get_artifact(query_model.artifact_id)
        current_revision_id = artifact.current_revision_id if artifact else None
        query = """
        MATCH (a:Artifact {artifact_id: $artifact_id})
        OPTIONAL MATCH (a)-[:HAS_REVISION]->(r:ArtifactRevision)
        OPTIONAL MATCH (f:ArtifactFeedback)-[:APPLIES_TO]->(r)
        OPTIONAL MATCH (c:ArtifactCommit)-[:COMMITS]->(r)
        OPTIONAL MATCH (k:KnowledgeDocument)-[:DERIVED_FROM_ARTIFACT]->(r)
        RETURN
            a.artifact_id AS artifact_id,
            a.status AS artifact_status,
            r.revision_id AS revision_id,
            r.revision_number AS revision_number,
            r.parent_revision_id AS parent_revision_id,
            r.verification_state AS verification_state,
            r.summary AS revision_summary,
            r.created_at AS revision_created_at,
            f.feedback_id AS feedback_id,
            f.feedback_type AS feedback_type,
            f.content AS feedback_content,
            f.created_at AS feedback_created_at,
            c.commit_id AS commit_id,
            c.commit_reason AS commit_reason,
            c.committed_at AS committed_at,
            k.knowledge_id AS knowledge_id,
            k.title AS knowledge_title
        ORDER BY r.revision_number ASC, feedback_created_at ASC, committed_at ASC
        """
        rows = await self.neo4j.execute_query(query, {"artifact_id": query_model.artifact_id})
        nodes: list[ArtifactLineageNode] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            if row.get("revision_id"):
                key = ("revision", row["revision_id"])
                if key not in seen:
                    nodes.append(
                        ArtifactLineageNode(
                            node_type="revision",
                            node_id=row["revision_id"],
                            artifact_id=row["artifact_id"],
                            relation="HAS_REVISION",
                            revision_id=row["revision_id"],
                            parent_id=row.get("parent_revision_id"),
                            timestamp=self._parse_dt(row.get("revision_created_at")),
                            content=row.get("revision_summary"),
                            metadata={
                                "revision_number": row.get("revision_number"),
                                "verification_state": row.get("verification_state"),
                                "artifact_status": row.get("artifact_status"),
                            },
                        )
                    )
                    seen.add(key)
            if row.get("feedback_id"):
                key = ("feedback", row["feedback_id"])
                if key not in seen:
                    nodes.append(
                        ArtifactLineageNode(
                            node_type="feedback",
                            node_id=row["feedback_id"],
                            artifact_id=row["artifact_id"],
                            relation="APPLIES_TO",
                            revision_id=row.get("revision_id"),
                            parent_id=row.get("revision_id"),
                            timestamp=self._parse_dt(row.get("feedback_created_at")),
                            content=row.get("feedback_content"),
                            metadata={"feedback_type": row.get("feedback_type")},
                        )
                    )
                    seen.add(key)
            if row.get("commit_id"):
                key = ("commit", row["commit_id"])
                if key not in seen:
                    nodes.append(
                        ArtifactLineageNode(
                            node_type="commit",
                            node_id=row["commit_id"],
                            artifact_id=row["artifact_id"],
                            relation="COMMITS",
                            revision_id=row.get("revision_id"),
                            parent_id=row.get("revision_id"),
                            timestamp=self._parse_dt(row.get("committed_at")),
                            content=row.get("commit_reason"),
                            metadata={},
                        )
                    )
                    seen.add(key)
            if row.get("knowledge_id"):
                key = ("knowledge", row["knowledge_id"])
                if key not in seen:
                    nodes.append(
                        ArtifactLineageNode(
                            node_type="knowledge",
                            node_id=row["knowledge_id"],
                            artifact_id=row["artifact_id"],
                            relation="DERIVED_FROM_ARTIFACT",
                            revision_id=row.get("revision_id"),
                            parent_id=row.get("revision_id"),
                            content=row.get("knowledge_title"),
                            metadata={},
                        )
                    )
                    seen.add(key)
        return ArtifactLineageResult(
            artifact_id=query_model.artifact_id,
            current_revision_id=current_revision_id,
            nodes=nodes,
            metadata={"node_count": len(nodes)},
        )

    async def _project_revision_to_working_memory(
        self, artifact: Artifact, revision: ArtifactRevision
    ) -> None:
        """Project revision to L1 and L2 working memory as search-friendly summaries."""
        await self._append_l1_event(
            artifact.session_id,
            "artifact_revision",
            {
                "artifact_id": artifact.artifact_id,
                "revision_id": revision.revision_id,
                "revision_number": revision.revision_number,
                "artifact_kind": artifact.artifact_kind,
                "verification_state": revision.verification_state,
                "summary": revision.summary,
                "payload": revision.payload,
            },
        )
        if self.l2_tier:
            summary = revision.summary or json.dumps(revision.payload, sort_keys=True, default=str)
            fact = Fact(
                fact_id=f"artifact-revision:{revision.revision_id}",
                session_id=artifact.session_id,
                content=(
                    f"Artifact {artifact.artifact_kind} revision {revision.revision_number} "
                    f"for {artifact.artifact_id}: {summary}"
                ),
                ciar_score=0.95,
                certainty=0.95,
                impact=1.0,
                source_uri=f"artifact:{artifact.artifact_id}:revision:{revision.revision_id}",
                source_type="artifact_projection",
                fact_type=FactType.EVENT,
                fact_category=FactCategory.OPERATIONAL,
                metadata={
                    "artifact_id": artifact.artifact_id,
                    "revision_id": revision.revision_id,
                    "revision_number": revision.revision_number,
                    "artifact_kind": artifact.artifact_kind,
                    "verification_state": revision.verification_state,
                    "artifact_projection": "revision",
                    "payload_hash": revision.payload_hash,
                },
                justification="Artifact revision projected into working memory for retrieval",
            )
            await self.l2_tier.store(fact)

    async def _project_feedback_to_working_memory(
        self, artifact: Artifact, feedback: ArtifactFeedback
    ) -> None:
        """Project feedback into L1 and L2 for prompt retrieval."""
        await self._append_l1_event(
            artifact.session_id,
            "artifact_feedback",
            {
                "artifact_id": artifact.artifact_id,
                "revision_id": feedback.revision_id,
                "feedback_id": feedback.feedback_id,
                "feedback_type": feedback.feedback_type,
                "source_system": feedback.source_system,
                "content": feedback.content,
                "structured_payload": feedback.structured_payload,
            },
        )
        if self.l2_tier:
            fact = Fact(
                fact_id=f"artifact-feedback:{feedback.feedback_id}",
                session_id=artifact.session_id,
                content=(
                    f"Feedback {feedback.feedback_type} from {feedback.source_system} "
                    f"for revision {feedback.revision_id}: {feedback.content}"
                ),
                ciar_score=0.95,
                certainty=0.95,
                impact=1.0,
                source_uri=f"artifact:{artifact.artifact_id}:feedback:{feedback.feedback_id}",
                source_type="artifact_feedback",
                fact_type=FactType.EVENT,
                fact_category=FactCategory.OPERATIONAL,
                metadata={
                    "artifact_id": artifact.artifact_id,
                    "revision_id": feedback.revision_id,
                    "feedback_id": feedback.feedback_id,
                    "feedback_type": feedback.feedback_type,
                    "source_system": feedback.source_system,
                    "artifact_projection": "feedback",
                },
                justification="External feedback projected into working memory for auditability",
            )
            await self.l2_tier.store(fact)

    async def _append_l1_event(
        self, session_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        """Store an artifact event in active context when available."""
        if not self.l1_tier:
            return
        turn = TurnData(
            turn_id=f"{event_type}-{payload.get('revision_id', payload.get('feedback_id', 'evt'))}",
            session_id=session_id,
            role="system",
            content=json.dumps(payload, sort_keys=True, default=str),
            timestamp=datetime.now(UTC),
            metadata={"artifact_event_type": event_type},
        )
        await self.l1_tier.store(turn)

    async def store_final_knowledge_projection(
        self,
        artifact: Artifact,
        revision: ArtifactRevision,
        commit: ArtifactCommit,
    ) -> KnowledgeDocument | None:
        """Store final artifact projection in semantic memory."""
        if not self.l4_tier:
            return None
        knowledge = KnowledgeDocument(
            knowledge_id=commit.knowledge_id or f"artifact-knowledge:{commit.commit_id}",
            session_id=artifact.session_id,
            title=f"Committed {artifact.artifact_kind} artifact {artifact.artifact_id}",
            content=(
                f"Final committed revision {revision.revision_number} for artifact "
                f"{artifact.artifact_id}.\n\n"
                f"Summary: {revision.summary or 'N/A'}\n\n"
                f"Payload:\n{json.dumps(revision.payload, sort_keys=True, default=str)}"
            ),
            knowledge_type="decision_artifact",
            confidence_score=1.0,
            source_episode_ids=[],
            episode_count=0,
            provenance_links=[
                f"artifact:{artifact.artifact_id}",
                f"revision:{revision.revision_id}",
                f"commit:{commit.commit_id}",
            ],
            category="artifact",
            tags=[artifact.artifact_kind, "artifact", "committed", revision.verification_state],
            domain="artifact-centric-memory",
            metadata={
                "artifact_id": artifact.artifact_id,
                "revision_id": revision.revision_id,
                "revision_number": revision.revision_number,
                "commit_id": commit.commit_id,
                "lineage_entrypoint": artifact.artifact_id,
            },
        )
        knowledge_id = await self.l4_tier.store(knowledge)
        knowledge.knowledge_id = knowledge_id
        return knowledge

    def _parse_dt(self, value: Any) -> datetime | None:
        """Parse ISO timestamps returned from the graph layer."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return None
