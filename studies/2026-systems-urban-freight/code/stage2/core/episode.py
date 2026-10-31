"""Small deterministic event episode with committed-stop completion before replans."""

from __future__ import annotations

from copy import deepcopy
from math import ceil, isfinite
from typing import Any

from .solver import solve


def run_event_episode(
    instance: dict[str, Any], events: list[dict[str, Any]], time_limit_s: float = 5.0
) -> dict[str, Any]:
    """Run routes and replan at event snapshots without moving vehicles instantly.

    Events may set `traffic_factor` for future legs and/or contain `order_updates`
    entries with an order `node` and changed public parameters. An in-progress leg
    and its destination service are completed before applying an event. Cargo stays
    with its initial vehicle assignment. On a failed replan, all vehicles hold at
    their actual positions and unresolved mandatory orders remain recorded.
    """
    x = deepcopy(instance)
    v = len(x["vehicle_capacities_kg"])
    n = len(x["distance_m"])
    events = sorted((deepcopy(e) for e in events), key=lambda e: e["at_s"])
    if any(
        not isinstance(e.get("at_s"), int) or e["at_s"] < x["shift_start_s"]
        for e in events
    ):
        raise ValueError("event times must be integer seconds at or after shift start")
    positions = [0] * v
    clocks = [x["shift_start_s"]] * v
    served: set[int] = set()
    owner: dict[int, int] = {}
    trace = []
    factor = 1.0

    def with_factor(base: dict[str, Any], f: float) -> dict[str, Any]:
        y = deepcopy(base)
        y["time_s"] = [[ceil(t * f) for t in row] for row in base["time_s"]]
        return y

    def assign_routes(plan: dict[str, Any]) -> dict[int, list[int]]:
        result: dict[int, list[int]] = {vehicle: [] for vehicle in range(v)}
        for route in plan.get("routes", []):
            vehicle = route["vehicle"]
            seq = route["nodes"]
            result[vehicle] = seq[1:-1]
            for node in result[vehicle]:
                owner[node] = vehicle
        return result

    def solve_remaining() -> tuple[dict[str, Any], dict[int, list[int]]]:
        remaining = sorted(set(range(1, n)) - served)
        payload = [
            sum(
                o["demand_kg"]
                for o in x["orders"]
                if o["node"] in remaining and owner.get(o["node"]) == vehicle
            )
            for vehicle in range(v)
        ]
        replanning = with_factor(x, factor)
        replanning.update(
            remaining_order_nodes=remaining,
            vehicle_start_nodes=positions,
            vehicle_start_times_s=clocks,
            remaining_payload_kg=payload,
        )
        for order in replanning["orders"]:
            if order["node"] in remaining and order["node"] in owner:
                order["allowed_vehicles"] = [owner[order["node"]]]
        plan = solve(replanning, time_limit_s)
        if plan["status"] != "FEASIBLE":
            return plan, {vehicle: [] for vehicle in range(v)}
        return plan, assign_routes(plan)

    plan = solve(with_factor(x, factor), time_limit_s)
    if plan["status"] != "FEASIBLE":
        return {
            "status": plan["status"],
            "served": [],
            "vehicles": [
                {"position_node": 0, "time_s": x["shift_start_s"], "load_kg": 0}
                for _ in range(v)
            ],
            "unresolved_orders": list(range(1, n)),
            "trace": [],
            "held": True,
        }
    routes = assign_routes(plan)
    cargo = [
        sum(o["demand_kg"] for o in x["orders"] if owner.get(o["node"]) == vehicle)
        for vehicle in range(v)
    ]
    for vehicle in range(v):
        if cargo[vehicle] > x["vehicle_capacities_kg"][vehicle]:
            raise ValueError("initial plan exceeds vehicle payload")

    def finish_one(vehicle: int, route: list[int]) -> bool:
        """Complete the next committed leg and service. Return False when idle."""
        if not route:
            return False
        node = route.pop(0)
        source = positions[vehicle]
        arrival = clocks[vehicle] + ceil(x["time_s"][source][node] * factor)
        now = arrival
        order = next(o for o in x["orders"] if o["node"] == node)
        service_start = max(now, order["open_s"])
        now = service_start + order["service_s"]
        positions[vehicle] = node
        clocks[vehicle] = now
        served.add(node)
        cargo[vehicle] -= order["demand_kg"]
        trace.append(
            {
                "kind": "delivery",
                "vehicle": vehicle,
                "node": node,
                "arrival_s": arrival,
                "service_start_s": service_start,
                "service_finish_s": now,
                "position_node": node,
                "remaining_load_kg": cargo[vehicle],
                "traffic_factor": factor,
            }
        )
        return True

    def advance_until(event_time: int | None) -> None:
        # Vehicles execute one committed stop at a time. If an event arrives during
        # a leg/service, that stop finishes first; then routes are reconsidered.
        progressed = True
        while progressed:
            progressed = False
            for vehicle in range(v):
                if routes[vehicle] and (
                    event_time is None or clocks[vehicle] < event_time
                ):
                    finish_one(vehicle, routes[vehicle])
                    progressed = True

    held = False
    for event in events:
        advance_until(event["at_s"])
        decision_time = max([event["at_s"], *clocks])
        clocks = [decision_time] * v
        for update in event.get("order_updates", []):
            node = update["node"]
            if node not in served:
                changed = set(update) - {"node", "open_s", "close_s", "service_s"}
                if changed:
                    raise ValueError(
                        f"event cannot alter physical cargo or unsupported fields: {sorted(changed)}"
                    )
                target = next((o for o in x["orders"] if o["node"] == node), None)
                if target is None:
                    raise ValueError(f"event refers to unknown order node {node}")
                target.update({k: value for k, value in update.items() if k != "node"})
        factor = float(event.get("traffic_factor", factor))
        if not isfinite(factor) or factor <= 0:
            raise ValueError("traffic_factor must be finite and positive")
        try:
            plan, routes = solve_remaining()
        except ValueError as error:
            plan = {"status": "INVALID_UPDATED_INSTANCE", "detail": str(error)}
            routes = {vehicle: [] for vehicle in range(v)}
        trace.append(
            {
                "kind": "replan",
                "requested_at_s": event["at_s"],
                "effective_at_s": decision_time,
                "status": plan["status"],
                "remaining_orders": sorted(set(range(1, n)) - served),
                "positions": positions.copy(),
                "cargo_owners": {str(k): v for k, v in owner.items()},
                "traffic_factor": factor,
            }
        )
        if plan["status"] != "FEASIBLE":
            held = True
            break
    if not held:
        advance_until(None)
    # Return vehicles to depot after customer routes, respecting current travel factor.
    if not held:
        for vehicle in range(v):
            if positions[vehicle] != 0:
                source = positions[vehicle]
                clocks[vehicle] += ceil(x["time_s"][source][0] * factor)
                positions[vehicle] = 0
    unresolved = sorted(set(range(1, n)) - served)
    return {
        "status": "HELD_NO_PLAN" if held else "COMPLETED",
        "served": sorted(served),
        "vehicles": [
            {
                "vehicle": i,
                "position_node": positions[i],
                "time_s": clocks[i],
                "load_kg": cargo[i],
            }
            for i in range(v)
        ],
        "unresolved_orders": unresolved,
        "trace": trace,
        "held": held,
    }
