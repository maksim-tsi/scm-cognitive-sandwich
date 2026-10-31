"""OR-Tools shared mandatory-order, directed VRPTW solver."""

from __future__ import annotations

from itertools import product
from typing import Any

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .model import order_map, validate_instance


def _routing_inputs(
    x: dict[str, Any],
) -> tuple[list[int], list[int], list[int], list[int]]:
    v = len(x["vehicle_capacities_kg"])
    starts = x.get("vehicle_start_nodes", [0] * v)
    start_times = x.get("vehicle_start_times_s", [x["shift_start_s"]] * v)
    remaining = x.get("remaining_order_nodes", list(range(1, len(x["distance_m"]))))
    payload = x.get("remaining_payload_kg", x["vehicle_capacities_kg"])
    return starts, start_times, remaining, payload


def _shortest_time_bounds(matrix: list[list[int]]) -> list[list[int]]:
    """All-pairs lower bounds remain sound even for nonmetric supplied matrices."""
    shortest = [row.copy() for row in matrix]
    for k in range(len(shortest)):
        for i in range(len(shortest)):
            via = shortest[i][k]
            for j in range(len(shortest)):
                candidate = via + shortest[k][j]
                shortest[i][j] = min(shortest[i][j], candidate)
    return shortest


def infeasibility_certificate(x: dict[str, Any]) -> dict[str, Any] | None:
    orders = order_map(x)
    starts, start_times, remaining, payload = _routing_inputs(x)
    total = sum(orders[node]["demand_kg"] for node in remaining)
    if total > sum(payload):
        return {
            "kind": "aggregate_remaining_payload",
            "required_kg": total,
            "available_kg": sum(payload),
        }
    lower = _shortest_time_bounds(x["time_s"])
    for node in remaining:
        o = orders[node]
        eligible = o.get("allowed_vehicles", list(range(len(starts))))
        viable = []
        for v in eligible:
            service_start = max(start_times[v] + lower[starts[v]][node], o["open_s"])
            return_time = service_start + o["service_s"] + lower[node][0]
            if (
                service_start + o["service_s"] <= o["close_s"]
                and return_time <= x["shift_end_s"]
            ):
                viable.append(v)
        if not viable:
            return {
                "kind": "single_order_time_window_lower_bound",
                "node": node,
                "eligible_vehicles": eligible,
                "start_nodes": starts,
                "start_times_s": start_times,
                "shortest_travel_bounds_s": {
                    "to_order": min(lower[s][node] for s in starts),
                    "return_to_depot": lower[node][0],
                },
                "close_s": o["close_s"],
                "shift_end_s": x["shift_end_s"],
            }
    if len(remaining) <= 6 and len(payload) <= 2:
        # Finite indivisible-load partition proof; aggregate mass alone is insufficient.
        feasible_partition = any(all(sum(orders[node]["demand_kg"] for node, assigned in zip(remaining, assignment) if assigned == v) <= payload[v] for v in range(len(payload))) and all(v in orders[node].get("allowed_vehicles", range(len(payload))) for node, v in zip(remaining, assignment)) for assignment in product(range(len(payload)), repeat=len(remaining)))
        if not feasible_partition:
            return {"kind": "exhaustive_indivisible_mass_assignment", "assignments_tested": len(payload) ** len(remaining), "loads_kg": [orders[n]["demand_kg"] for n in remaining], "available_kg": payload}
    return None


def solve(
    instance: dict[str, Any],
    time_limit_s: float = 5.0,
    *,
    vehicle_start_nodes: list[int] | None = None,
    vehicle_start_times_s: list[int] | None = None,
    remaining_order_nodes: list[int] | None = None,
    remaining_payload_kg: list[int] | None = None,
) -> dict[str, Any]:
    if any(
        value is not None
        for value in (
            vehicle_start_nodes,
            vehicle_start_times_s,
            remaining_order_nodes,
            remaining_payload_kg,
        )
    ):
        instance = instance.copy()
        overrides = {
            "vehicle_start_nodes": vehicle_start_nodes,
            "vehicle_start_times_s": vehicle_start_times_s,
            "remaining_order_nodes": remaining_order_nodes,
            "remaining_payload_kg": remaining_payload_kg,
        }
        instance.update(
            {key: value for key, value in overrides.items() if value is not None}
        )
    validate_instance(instance)
    if time_limit_s <= 0:
        raise ValueError("time_limit_s must be positive")
    cert = infeasibility_certificate(instance)
    if cert:
        return {
            "status": "INFEASIBLE_CERTIFIED",
            "certificate": cert,
            "routes": [],
            "travel_seconds": 0,
            "distance_m": 0,
        }
    caps = instance["vehicle_capacities_kg"]
    v = len(caps)
    starts, start_times, remaining, payload = _routing_inputs(instance)
    # Build a compact graph containing only the depot, remaining orders, and
    # current vehicle anchors. Completed sites never enter the routing model.
    selected_nodes = [0] + sorted((set(remaining) | set(starts)) - {0})
    internal = {node: i for i, node in enumerate(selected_nodes)}
    manager = pywrapcp.RoutingIndexManager(
        len(selected_nodes), v, [internal[node] for node in starts], [internal[0]] * v
    )
    routing = pywrapcp.RoutingModel(manager)
    dm, tm, orders = instance["distance_m"], instance["time_s"], order_map(instance)

    def original(index: int) -> int:
        return selected_nodes[manager.IndexToNode(index)]

    def dist_cb(a: int, b: int) -> int:
        return dm[original(a)][original(b)]

    di = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(di)

    def time_cb(a: int, b: int) -> int:
        src = original(a)
        dst = original(b)
        return tm[src][dst] + (orders[src]["service_s"] if src in remaining else 0)

    ti = routing.RegisterTransitCallback(time_cb)
    routing.AddDimension(
        ti,
        max(0, instance["shift_end_s"] - instance["shift_start_s"]),
        instance["shift_end_s"],
        False,
        "Time",
    )
    td = routing.GetDimensionOrDie("Time")
    remaining_set = set(remaining)
    for node in remaining:
        index = manager.NodeToIndex(internal[node])
        order = orders[node]
        td.CumulVar(index).SetRange(
            max(instance["shift_start_s"], order["open_s"]),
            order["close_s"] - order["service_s"],
        )
        allowed = order.get("allowed_vehicles")
        if "upright_dimensions_mm" in order:
            length, width, height = order["upright_dimensions_mm"]
            aperture_allowed = [v for v in range(len(caps)) if min(length, width) <= instance["loading_width_mm"][v] and height <= instance["loading_height_mm"][v]]
            allowed = [v for v in (allowed if allowed is not None else range(len(caps))) if v in aperture_allowed]
        if allowed is not None:
            if not allowed:
                return {"status": "INFEASIBLE_CERTIFIED", "certificate": {"kind": "no_loading_aperture", "node": node}, "routes": []}
            routing.VehicleVar(index).SetValues(allowed)
    for vehicle in range(v):
        td.CumulVar(routing.Start(vehicle)).SetRange(
            start_times[vehicle], start_times[vehicle]
        )
        td.CumulVar(routing.End(vehicle)).SetRange(
            instance["shift_start_s"], instance["shift_end_s"]
        )

    def demand_cb(index: int) -> int:
        node = original(index)
        return orders[node]["demand_kg"] if node in remaining_set else 0

    ci = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(ci, 0, payload, True, "Load")
    if "vehicle_volumes_l" in instance:
        vi = routing.RegisterUnaryTransitCallback(lambda index: orders[original(index)].get("volume_l", 0) if original(index) in remaining_set else 0)
        routing.AddDimensionWithVehicleCapacity(vi, 0, instance["vehicle_volumes_l"], True, "Volume")
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromMilliseconds(max(1, int(time_limit_s * 1000)))
    params.log_search = False
    assignment = routing.SolveWithParameters(params)
    if assignment is None:
        return {
            "status": "NO_SOLUTION_UNKNOWN",
            "certificate": None,
            "routes": [],
            "travel_seconds": 0,
            "distance_m": 0,
        }
    routes = []
    total_d = total_t = total_service = 0
    for vehicle in range(v):
        idx = routing.Start(vehicle)
        start_node = original(idx)
        nodes = [start_node]
        timetable = []
        route_d = route_t = 0
        while not routing.IsEnd(idx):
            node = original(idx)
            nxt = assignment.Value(routing.NextVar(idx))
            dest = original(nxt)
            if node in remaining_set:
                start = assignment.Value(td.CumulVar(idx))
                finish = start + orders[node]["service_s"]
                timetable.append(
                    {"node": node, "service_start_s": start, "service_finish_s": finish}
                )
            route_d += dm[node][dest]
            route_t += tm[node][dest]
            idx = nxt
            if not routing.IsEnd(idx):
                nodes.append(original(idx))
        if len(nodes) > 1 or start_node != 0:
            nodes.append(0)
            routes.append(
                {
                    "vehicle": vehicle,
                    "nodes": nodes,
                    "timetable": timetable,
                    "distance_m": route_d,
                    "travel_seconds": route_t,
                }
            )
            total_d += route_d
            total_t += route_t
            total_service += sum(
                orders[k]["service_s"] for k in nodes if k in remaining_set
            )
    return {
        "status": "FEASIBLE",
        "routes": routes,
        "travel_seconds": total_t,
        "service_seconds": total_service,
        "distance_m": total_d,
        "solver": {"backend": "OR-Tools", "time_limit_s": time_limit_s},
    }
