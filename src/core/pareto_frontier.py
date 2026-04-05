from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


def _dominates(a: dict[str, float], b: dict[str, float], keys: Sequence[str]) -> bool:
    """Return True if point a dominates point b (minimization)."""
    a_le_all = all(a[k] <= b[k] for k in keys)
    a_lt_any = any(a[k] < b[k] for k in keys)
    return a_le_all and a_lt_any


def pareto_frontier(
    points: Iterable[dict[str, Any]],
    *,
    id_key: str = "scenario_id",
    minimize: Sequence[str] = ("time", "cost", "risk"),
) -> list[str]:
    """Compute the deterministic Pareto frontier (non-dominated ids) for minimization objectives.

    Input points are dict-like rows containing:
      - `id_key` (default: scenario_id)
      - objective metrics in `minimize` (floats/ints)
    """
    keys = tuple(minimize)
    rows: list[dict[str, Any]] = list(points)

    normalized: list[tuple[str, dict[str, float]]] = []
    for row in rows:
        if id_key not in row:
            raise ValueError(f"Point missing {id_key!r}: {row!r}")
        scenario_id = str(row[id_key])
        metrics: dict[str, float] = {}
        for k in keys:
            if k not in row:
                raise ValueError(f"Point {scenario_id!r} missing metric {k!r}.")
            value = row[k]
            if not isinstance(value, (int, float)):
                raise TypeError(f"Metric {k!r} for {scenario_id!r} must be numeric, got {type(value)}.")
            metrics[k] = float(value)
        normalized.append((scenario_id, metrics))

    frontier: list[str] = []
    for i, (sid_i, metrics_i) in enumerate(normalized):
        dominated = False
        for j, (sid_j, metrics_j) in enumerate(normalized):
            if i == j:
                continue
            if _dominates(metrics_j, metrics_i, keys):
                dominated = True
                break
        if not dominated:
            frontier.append(sid_i)

    return sorted(set(frontier))

