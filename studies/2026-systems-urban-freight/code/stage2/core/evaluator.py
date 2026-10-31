"""Independent route checker. Recomputes clocks, load, starts, and coverage."""

from __future__ import annotations

from itertools import pairwise
from typing import Any


def evaluate(
    instance: dict[str, Any],
    solution: dict[str, Any],
    expected_instance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    violations: list[str] = []
    n = len(instance["distance_m"])
    orders = {o["node"]: o for o in instance["orders"]}
    vehicle_count = len(instance["vehicle_capacities_kg"])
    starts = instance.get("vehicle_start_nodes", [0] * vehicle_count)
    start_times = instance.get(
        "vehicle_start_times_s", [instance["shift_start_s"]] * vehicle_count
    )
    payload = instance.get("remaining_payload_kg", instance["vehicle_capacities_kg"])
    required = set(instance.get("remaining_order_nodes", range(1, n)))
    if expected_instance is not None:
        exp_orders = {o["node"]: o for o in expected_instance["orders"]}
        for node in sorted(set(orders) | set(exp_orders)):
            if orders.get(node) != exp_orders.get(node):
                violations.append(f"instance_order_mismatch:{node}")
        for key in (
            "distance_m",
            "time_s",
            "vehicle_capacities_kg",
            "vehicle_volumes_l",
            "loading_width_mm",
            "loading_height_mm",
            "remaining_payload_kg",
            "vehicle_start_nodes",
            "vehicle_start_times_s",
            "remaining_order_nodes",
            "shift_start_s",
            "shift_end_s",
        ):
            if instance.get(key) != expected_instance.get(key):
                violations.append(f"instance_parameter_mismatch:{key}")
    if any(start in required for start in starts):
        violations.append("start_anchor_is_remaining_order")
    if solution.get("status") != "FEASIBLE":
        return {
            "valid": False,
            "violations": violations + ["solution_not_feasible"],
            "distance_m": None,
            "travel_seconds": None,
        }
    served = []
    distance = travel = elapsed = 0
    routed_vehicles = set()
    for route in solution.get("routes", []):
        vehicle = route.get("vehicle")
        nodes = route.get("nodes", [])
        if not isinstance(vehicle, int) or not (0 <= vehicle < vehicle_count):
            violations.append("invalid_vehicle")
            continue
        if vehicle in routed_vehicles:
            violations.append(f"duplicate_vehicle_route:{vehicle}")
        routed_vehicles.add(vehicle)
        if len(nodes) < 2 or nodes[0] != starts[vehicle] or nodes[-1] != 0:
            violations.append(f"route_start_or_depot_mismatch:{vehicle}")
            continue
        now = start_times[vehicle]
        load = volume = 0
        for a, b in pairwise(nodes):
            if not (0 <= a < n and 0 <= b < n):
                violations.append(f"invalid_node:{a}:{b}")
                continue
            distance += instance["distance_m"][a][b]
            travel += instance["time_s"][a][b]
            now += instance["time_s"][a][b]
            if b == 0:
                continue
            if b not in orders or b not in required:
                violations.append(f"unexpected_order:{b}")
                continue
            order = orders[b]
            allowed = order.get("allowed_vehicles")
            if allowed is not None and vehicle not in allowed:
                violations.append(f"cargo_owner_violation:{b}:{vehicle}")
            if "upright_dimensions_mm" in order:
                a_dim, b_dim, height = order["upright_dimensions_mm"]
                if min(a_dim, b_dim) > instance["loading_width_mm"][vehicle] or height > instance["loading_height_mm"][vehicle]:
                    violations.append(f"loading_clearance_violation:{b}:{vehicle}")
            volume += order.get("volume_l", 0)
            now = max(now, order["open_s"])
            if now + order["service_s"] > order["close_s"]:
                violations.append(f"finish_after_close:{b}")
            now += order["service_s"]
            load += order["demand_kg"]
            served.append(b)
        if load > payload[vehicle]:
            violations.append(
                f"remaining_payload_exceeded:{vehicle}:{load}>{payload[vehicle]}"
            )
        if "vehicle_volumes_l" in instance and volume > instance["vehicle_volumes_l"][vehicle]:
            violations.append(f"aggregate_volume_exceeded:{vehicle}")
        if now > instance["shift_end_s"]:
            violations.append(f"shift_return_late:{vehicle}:{now}")
        elapsed += now - start_times[vehicle]
    for vehicle, start in enumerate(starts):
        if start != 0 and vehicle not in routed_vehicles:
            violations.append(f"missing_return_route:{vehicle}")
    if sorted(served) != sorted(required):
        violations.append("remaining_orders_not_served_exactly_once")
    return {
        "valid": not violations,
        "violations": violations,
        "distance_m": distance,
        "travel_seconds": travel,
        "elapsed_vehicle_seconds": elapsed,
    }
