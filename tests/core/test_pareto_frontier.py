from core.pareto_frontier import pareto_frontier


def test_pareto_frontier_returns_non_dominated_sorted() -> None:
    points = [
        {"scenario_id": "A", "time": 10, "cost": 100, "risk": 5},
        {"scenario_id": "B", "time": 12, "cost": 90, "risk": 5},
        {"scenario_id": "C", "time": 10, "cost": 100, "risk": 6},  # dominated by A
        {"scenario_id": "D", "time": 9, "cost": 130, "risk": 4},
    ]

    # A dominates C; others are non-dominated.
    assert pareto_frontier(points) == ["A", "B", "D"]


def test_pareto_frontier_is_deterministic() -> None:
    points1 = [
        {"scenario_id": "B", "time": 12, "cost": 90, "risk": 5},
        {"scenario_id": "A", "time": 10, "cost": 100, "risk": 5},
    ]
    points2 = list(reversed(points1))

    assert pareto_frontier(points1) == pareto_frontier(points2) == ["A", "B"]

