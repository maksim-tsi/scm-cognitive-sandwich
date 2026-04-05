"""
Artifact-centric memory models.

Defines the generic data contracts for versioned artifacts, external feedback,
commit records, and lineage retrieval.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ArtifactStatus = Literal["draft", "failed", "validated", "committed", "superseded"]
VerificationState = Literal["unverified", "infeasible", "feasible"]
TierState = Literal["working", "committed"]


class Artifact(BaseModel):
    """Top-level artifact tracked across multiple revisions."""

    artifact_id: str = Field(..., min_length=1, max_length=200)
    artifact_kind: str = Field(..., min_length=1, max_length=200)
    session_id: str = Field(..., min_length=1, max_length=200)
    workspace_id: str | None = Field(default=None, max_length=200)
    status: ArtifactStatus = "draft"
    current_revision_id: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRevision(BaseModel):
    """A concrete version of an artifact payload."""

    revision_id: str = Field(..., min_length=1, max_length=200)
    artifact_id: str = Field(..., min_length=1, max_length=200)
    revision_number: int = Field(..., ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = Field(..., min_length=1, max_length=128)
    verification_state: VerificationState = "unverified"
    tier_state: TierState = "working"
    parent_revision_id: str | None = Field(default=None, max_length=200)
    trigger_feedback_id: str | None = Field(default=None, max_length=200)
    created_by: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def hash_payload(cls, payload: dict[str, Any]) -> str:
        """Return a deterministic hash for an opaque structured payload."""
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @field_validator("payload_hash")
    @classmethod
    def validate_payload_hash(cls, value: str) -> str:
        """Ensure hashes are non-empty hex strings."""
        if not value.strip():
            raise ValueError("payload_hash cannot be empty")
        return value


class ArtifactFeedback(BaseModel):
    """External feedback linked to a specific artifact revision."""

    feedback_id: str = Field(..., min_length=1, max_length=200)
    artifact_id: str = Field(..., min_length=1, max_length=200)
    revision_id: str = Field(..., min_length=1, max_length=200)
    feedback_type: str = Field(..., min_length=1, max_length=200)
    source_system: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=50000)
    structured_payload: dict[str, Any] | None = None
    severity: str | None = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactCommit(BaseModel):
    """Commit record for the final validated artifact revision."""

    commit_id: str = Field(..., min_length=1, max_length=200)
    artifact_id: str = Field(..., min_length=1, max_length=200)
    revision_id: str = Field(..., min_length=1, max_length=200)
    knowledge_id: str | None = Field(default=None, max_length=200)
    commit_reason: str | None = Field(default=None, max_length=5000)
    committed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactLineageQuery(BaseModel):
    """Query parameters for retrieving artifact lineage."""

    artifact_id: str = Field(..., min_length=1, max_length=200)
    revision_id: str | None = Field(default=None, max_length=200)


class ArtifactLineageNode(BaseModel):
    """Single node in an ordered artifact lineage view."""

    node_type: Literal["artifact", "revision", "feedback", "commit", "knowledge"]
    node_id: str = Field(..., min_length=1, max_length=200)
    artifact_id: str = Field(..., min_length=1, max_length=200)
    relation: str | None = Field(default=None, max_length=200)
    revision_id: str | None = Field(default=None, max_length=200)
    parent_id: str | None = Field(default=None, max_length=200)
    timestamp: datetime | None = None
    content: str | None = Field(default=None, max_length=50000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactLineageResult(BaseModel):
    """Ordered lineage result for an artifact."""

    artifact_id: str = Field(..., min_length=1, max_length=200)
    current_revision_id: str | None = Field(default=None, max_length=200)
    nodes: list[ArtifactLineageNode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
