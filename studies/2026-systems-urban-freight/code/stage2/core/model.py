"""Small, dependency-light input helpers for the offline Padua VRPTW core."""

from __future__ import annotations

from typing import Any


def validate_instance(x: dict[str, Any]) -> None:
    n = len(x.get("distance_m", []))
    if n < 2 or len(x.get("time_s", [])) != n:
        raise ValueError("distance_m and time_s must be equally sized square matrices")
    for key in ("distance_m", "time_s"):
        matrix = x[key]
        if any(len(row) != n for row in matrix):
            raise ValueError(f"{key} must be square")
        if any(not isinstance(v, int) or v < 0 for row in matrix for v in row):
            raise ValueError(f"{key} values must be nonnegative integers")
    if x.get("depot", 0) != 0:
        raise ValueError("this schema requires depot node 0")
    orders = x.get("orders", [])
    if sorted(o["node"] for o in orders) != list(range(1, n)):
        raise ValueError("every non-depot node must have exactly one mandatory order")
    if not x.get("vehicle_capacities_kg"):
        raise ValueError("at least one vehicle capacity is required")
    if any(not isinstance(c, int) or c < 0 for c in x["vehicle_capacities_kg"]):
        raise ValueError("vehicle capacities must be nonnegative integer kg")
    vehicles = len(x["vehicle_capacities_kg"])
    remaining = x.get("remaining_order_nodes", list(range(1, n)))
    if len(set(remaining)) != len(remaining) or any(
        node not in range(1, n) for node in remaining
    ):
        raise ValueError("remaining_order_nodes must be unique customer node IDs")
    starts = x.get("vehicle_start_nodes", [0] * vehicles)
    start_times = x.get("vehicle_start_times_s", [x["shift_start_s"]] * vehicles)
    payload = x.get("remaining_payload_kg", x["vehicle_capacities_kg"])
    if (
        len(starts) != vehicles
        or len(start_times) != vehicles
        or len(payload) != vehicles
    ):
        raise ValueError(
            "start nodes, start times, and remaining payload must have one value per vehicle"
        )
    if any(node not in range(n) for node in starts):
        raise ValueError("vehicle start node is outside the matrices")
    if any(node in remaining for node in starts):
        raise ValueError(
            "a vehicle cannot start at an unserved order node; finish its committed service first"
        )
    if any(
        not isinstance(t, int) or t < x["shift_start_s"] or t > x["shift_end_s"]
        for t in start_times
    ):
        raise ValueError("vehicle start times must be inside the shift")
    if any(
        not isinstance(p, int) or p < 0 or p > c
        for p, c in zip(payload, x["vehicle_capacities_kg"])
    ):
        raise ValueError("remaining payload must be within each vehicle capacity")
    for key in ("vehicle_volumes_l", "loading_width_mm", "loading_height_mm"):
        if key in x and (len(x[key]) != vehicles or any(type(v) is not int or v <= 0 for v in x[key])):
            raise ValueError(f"{key} requires positive integer bounds per vehicle")
    for o in orders:
        if "volume_l" in o and (type(o["volume_l"]) is not int or o["volume_l"] < 0 or "vehicle_volumes_l" not in x):
            raise ValueError("aggregate volume needs integer litres and vehicle bounds")
        if "upright_dimensions_mm" in o and (len(o["upright_dimensions_mm"]) != 3 or any(type(v) is not int or v <= 0 for v in o["upright_dimensions_mm"]) or "loading_width_mm" not in x or "loading_height_mm" not in x):
            raise ValueError("upright package needs three positive dimensions and aperture bounds")
    for o in orders:
        allowed = o.get("allowed_vehicles")
        if allowed is not None and (
            not allowed or any(v not in range(vehicles) for v in allowed)
        ):
            raise ValueError(f"invalid allowed_vehicles for node {o['node']}")
    for o in orders:
        for k in ("demand_kg", "service_s", "open_s", "close_s"):
            if not isinstance(o.get(k), int):
                raise TypeError(f"order {o.get('node')} needs integer {k}")
        if o["demand_kg"] < 0 or o["service_s"] < 0 or o["open_s"] > o["close_s"]:
            raise ValueError(f"invalid order bounds for node {o['node']}")
    if (
        not isinstance(x.get("shift_start_s"), int)
        or not isinstance(x.get("shift_end_s"), int)
        or x["shift_start_s"] > x["shift_end_s"]
    ):
        raise ValueError("invalid shift bounds")


def order_map(x: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {o["node"]: o for o in x["orders"]}
