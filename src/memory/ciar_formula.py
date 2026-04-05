"""Shared CIAR formula helpers.

This module centralizes the ADR-004 CIAR defaults and deterministic score
calculation helpers so the scorer, data models, and tier logic do not drift.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

DEFAULT_CIAR_THRESHOLD = 0.6
DEFAULT_AGE_DECAY_LAMBDA = 0.0231
DEFAULT_RECENCY_ALPHA = 0.1


def clamp_unit_interval(value: float) -> float:
    """Clamp a numeric value into the inclusive [0.0, 1.0] interval."""
    return max(0.0, min(1.0, float(value)))


def normalize_timestamp(value: Any) -> datetime | None:
    """Normalize a timestamp input to a timezone-aware UTC datetime."""
    if value is None:
        return None

    timestamp = value
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    if not isinstance(timestamp, datetime):
        raise TypeError(f"Unsupported timestamp type: {type(value)!r}")

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return timestamp


def resolve_created_at(data: dict[str, Any]) -> datetime | None:
    """Resolve the preferred CIAR timestamp from a fact-like mapping."""
    return normalize_timestamp(data.get("created_at") or data.get("extracted_at"))


def calculate_age_decay(
    created_at: Any,
    *,
    decay_lambda: float = DEFAULT_AGE_DECAY_LAMBDA,
    max_age_days: float | None = None,
    min_score: float = 0.0,
    now: datetime | None = None,
) -> float:
    """Calculate the ADR-004 exponential time-decay factor."""
    normalized = normalize_timestamp(created_at)
    if normalized is None:
        return 1.0

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)

    age_days = max(0.0, (current_time - normalized).total_seconds() / 86400)
    if max_age_days is not None:
        age_days = min(age_days, max_age_days)

    decay = math.exp(-float(decay_lambda) * age_days)
    return max(float(min_score), decay)


def calculate_recency_boost(
    access_count: Any,
    *,
    alpha: float = DEFAULT_RECENCY_ALPHA,
    max_boost: float | None = None,
) -> float:
    """Calculate the ADR-004 linear reinforcement factor."""
    try:
        count = int(access_count)
    except (TypeError, ValueError):
        count = 0

    if count <= 0:
        return 1.0

    boost = 1.0 + (float(alpha) * count)
    if max_boost is not None:
        boost = min(boost, 1.0 + float(max_boost))

    return boost


def calculate_ciar_score(
    certainty: float,
    impact: float,
    age_decay: float,
    recency_boost: float,
) -> float:
    """Calculate the final ADR-004 CIAR score with unit-interval clamping."""
    return clamp_unit_interval(
        float(certainty) * float(impact) * float(age_decay) * float(recency_boost)
    )
