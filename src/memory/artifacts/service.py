"""
Artifact-centric memory orchestration service.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from src.memory.artifacts.models import (
    Artifact,
    ArtifactCommit,
    ArtifactFeedback,
    ArtifactLineageQuery,
    ArtifactLineageResult,
    ArtifactRevision,
)
from src.memory.artifacts.repository import ArtifactRepository

logger = logging.getLogger(__name__)


class ArtifactService:
    """High-level API for managing versioned artifacts and causal feedback."""

    INFEASIBLE_FEEDBACK_TYPES: ClassVar[set[str]] = {
        "solver_iis",
        "solver_failure",
        "infeasible",
        "capacity_iis",
    }
    FEASIBLE_FEEDBACK_TYPES: ClassVar[set[str]] = {
        "solver_success",
        "solver_feasible",
        "feasible",
        "validated",
    }

    def __init__(self, repository: ArtifactRepository):
        self.repository = repository

    async def create_draft(
        self,
        *,
        artifact_kind: str,
        payload: dict[str, Any],
        session_id: str,
        artifact_id: str | None = None,
        workspace_id: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> ArtifactRevision:
        """Create the first or next draft revision for an artifact."""
        now = datetime.now(UTC)
        resolved_artifact_id = artifact_id or f"artifact-{uuid4().hex}"
        artifact = await self.repository.get_artifact(resolved_artifact_id)
        if artifact is None:
            artifact = Artifact(
                artifact_id=resolved_artifact_id,
                artifact_kind=artifact_kind,
                session_id=session_id,
                workspace_id=workspace_id,
                status="draft",
                created_at=now,
                updated_at=now,
                metadata=metadata or {},
            )
            next_revision = 1
        else:
            if artifact.artifact_kind != artifact_kind:
                raise ValueError(
                    f"Artifact {resolved_artifact_id} has kind {artifact.artifact_kind}, "
                    f"not {artifact_kind}"
                )
            next_revision = await self.repository.get_next_revision_number(resolved_artifact_id)
            artifact.updated_at = now
            artifact.status = "draft"
            artifact.metadata = {**artifact.metadata, **(metadata or {})}

        revision = ArtifactRevision(
            revision_id=f"rev-{uuid4().hex}",
            artifact_id=resolved_artifact_id,
            revision_number=next_revision,
            payload=payload,
            payload_hash=ArtifactRevision.hash_payload(payload),
            verification_state="unverified",
            tier_state="working",
            parent_revision_id=artifact.current_revision_id,
            created_by=created_by,
            created_at=now,
            summary=summary,
            metadata=metadata or {},
        )
        artifact.current_revision_id = revision.revision_id
        await self.repository.create_artifact(artifact)
        await self.repository.store_revision(artifact, revision)
        await self.repository.update_artifact(
            resolved_artifact_id,
            status="draft",
            current_revision_id=revision.revision_id,
            session_id=session_id,
            metadata=artifact.metadata,
        )
        return revision

    async def attach_feedback(
        self,
        *,
        artifact_id: str,
        revision_id: str,
        feedback_type: str,
        source_system: str,
        content: str,
        structured_payload: dict[str, Any] | None = None,
        severity: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactFeedback:
        """Attach external feedback to a revision and update verification state."""
        artifact = await self._require_artifact(artifact_id)
        revision = await self._require_revision(revision_id)
        if revision.artifact_id != artifact_id:
            raise ValueError(
                f"Revision {revision_id} does not belong to artifact {artifact_id}"
            )
        feedback = ArtifactFeedback(
            feedback_id=f"feedback-{uuid4().hex}",
            artifact_id=artifact_id,
            revision_id=revision_id,
            feedback_type=feedback_type,
            source_system=source_system,
            content=content,
            structured_payload=structured_payload,
            severity=severity,
            metadata=metadata or {},
        )
        await self.repository.store_feedback(artifact, feedback)

        normalized = feedback_type.lower()
        if normalized in self.INFEASIBLE_FEEDBACK_TYPES:
            await self.repository.update_revision_verification(
                revision_id,
                "infeasible",
                trigger_feedback_id=feedback.feedback_id,
                session_id=artifact.session_id,
            )
            await self.repository.update_artifact(
                artifact_id,
                status="failed",
                current_revision_id=artifact.current_revision_id,
                session_id=artifact.session_id,
                metadata=artifact.metadata,
            )
        elif normalized in self.FEASIBLE_FEEDBACK_TYPES:
            await self.repository.update_revision_verification(
                revision_id,
                "feasible",
                trigger_feedback_id=feedback.feedback_id,
                session_id=artifact.session_id,
            )
            await self.repository.update_artifact(
                artifact_id,
                status="validated",
                current_revision_id=artifact.current_revision_id,
                session_id=artifact.session_id,
                metadata=artifact.metadata,
            )

        return feedback

    async def create_revision(
        self,
        *,
        artifact_id: str,
        parent_revision_id: str,
        payload: dict[str, Any],
        trigger_feedback_id: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> ArtifactRevision:
        """Create a new revision linked to its parent and optional triggering feedback."""
        artifact = await self._require_artifact(artifact_id)
        parent = await self._require_revision(parent_revision_id)
        if parent.artifact_id != artifact_id:
            raise ValueError(
                f"Parent revision {parent_revision_id} does not belong to artifact {artifact_id}"
            )
        next_revision = await self.repository.get_next_revision_number(artifact_id)
        revision = ArtifactRevision(
            revision_id=f"rev-{uuid4().hex}",
            artifact_id=artifact_id,
            revision_number=next_revision,
            payload=payload,
            payload_hash=ArtifactRevision.hash_payload(payload),
            verification_state="unverified",
            tier_state="working",
            parent_revision_id=parent_revision_id,
            trigger_feedback_id=trigger_feedback_id,
            created_by=created_by,
            summary=summary,
            metadata=metadata or {},
        )
        await self.repository.store_revision(artifact, revision)
        if trigger_feedback_id:
            await self.repository.link_revision_to_feedback(
                revision.revision_id, trigger_feedback_id, session_id=artifact.session_id
            )
            await self.repository.update_revision_verification(
                revision.revision_id,
                "unverified",
                trigger_feedback_id=trigger_feedback_id,
                session_id=artifact.session_id,
            )
        artifact.current_revision_id = revision.revision_id
        artifact.status = "draft"
        artifact.updated_at = datetime.now(UTC)
        await self.repository.update_artifact(
            artifact_id,
            status="draft",
            current_revision_id=revision.revision_id,
            session_id=artifact.session_id,
            metadata={**artifact.metadata, **(metadata or {})},
        )
        if parent.revision_id != revision.revision_id:
            await self.repository.update_revision_verification(
                parent.revision_id,
                parent.verification_state,
                session_id=artifact.session_id,
            )
        return revision

    async def commit_final(
        self,
        *,
        artifact_id: str,
        revision_id: str,
        commit_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactCommit:
        """Commit a feasible artifact revision into semantic memory."""
        artifact = await self._require_artifact(artifact_id)
        revision = await self._require_revision(revision_id)
        if revision.artifact_id != artifact_id:
            raise ValueError(
                f"Revision {revision_id} does not belong to artifact {artifact_id}"
            )
        if revision.verification_state != "feasible":
            raise ValueError(
                f"Revision {revision_id} is not feasible and cannot be committed"
            )
        commit = ArtifactCommit(
            commit_id=f"commit-{uuid4().hex}",
            artifact_id=artifact_id,
            revision_id=revision_id,
            commit_reason=commit_reason,
            metadata=metadata or {},
        )
        knowledge = await self.repository.store_final_knowledge_projection(artifact, revision, commit)
        commit.knowledge_id = knowledge.knowledge_id if knowledge else None
        await self.repository.store_commit(artifact, revision, commit, knowledge)
        await self.repository.update_revision_verification(
            revision_id,
            "feasible",
            tier_state="committed",
            session_id=artifact.session_id,
        )
        await self.repository.update_artifact(
            artifact_id,
            status="committed",
            current_revision_id=revision_id,
            session_id=artifact.session_id,
            metadata={**artifact.metadata, **(metadata or {})},
        )
        return commit

    async def get_lineage(
        self, *, artifact_id: str, revision_id: str | None = None
    ) -> ArtifactLineageResult:
        """Return ordered lineage for an artifact."""
        return await self.repository.get_lineage(
            ArtifactLineageQuery(artifact_id=artifact_id, revision_id=revision_id)
        )

    async def get_artifact_context(self, *, artifact_id: str) -> dict[str, Any]:
        """Return a compact artifact context payload for prompts or audit views."""
        artifact = await self._require_artifact(artifact_id)
        lineage = await self.get_lineage(artifact_id=artifact_id)
        current_revision = None
        if artifact.current_revision_id:
            current_revision = await self.repository.get_revision(artifact.current_revision_id)
        return {
            "artifact": artifact.model_dump(mode="json"),
            "current_revision": current_revision.model_dump(mode="json")
            if current_revision
            else None,
            "lineage": lineage.model_dump(mode="json"),
        }

    async def _require_artifact(self, artifact_id: str) -> Artifact:
        artifact = await self.repository.get_artifact(artifact_id)
        if artifact is None:
            raise KeyError(f"Artifact not found: {artifact_id}")
        return artifact

    async def _require_revision(self, revision_id: str) -> ArtifactRevision:
        revision = await self.repository.get_revision(revision_id)
        if revision is None:
            raise KeyError(f"Artifact revision not found: {revision_id}")
        return revision
