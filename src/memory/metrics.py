from __future__ import annotations

from types import TracebackType
from typing import Any


class MetricsCollector:
    """Minimal metrics collector for the memory subsystem.

    The original upstream implementation depends on `src.storage.*`, which is
    intentionally excluded from this repository per RFC-005. This no-op
    implementation preserves the public surface area needed by the memory tiers
    without introducing additional infrastructure dependencies.
    """

    async def get_metrics(self) -> dict[str, Any]:
        return {}


class OperationTimer:
    """No-op async context manager used by tiers to record timing."""

    def __init__(self, metrics: MetricsCollector, operation: str):  # noqa: ARG002
        self._metrics = metrics
        self._operation = operation

    async def __aenter__(self) -> "OperationTimer":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return False

