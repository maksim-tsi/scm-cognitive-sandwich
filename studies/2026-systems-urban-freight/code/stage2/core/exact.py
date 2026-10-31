"""Tiny independent exhaustive reference for at most six mandatory customers."""

from __future__ import annotations

from itertools import permutations, product
from typing import Any


def exact_solve(x: dict[str, Any]) -> dict[str, Any]:
    if any(
        k in x
        for k in (
            "vehicle_start_nodes",
            "vehicle_start_times_s",
            "remaining_order_nodes",
            "remaining_payload_kg",
        )
    ):
        raise ValueError("exact reference supports initial depot-start instances only")
    n = len(x["distance_m"])
    m = n - 1
    v = len(x["vehicle_capacities_kg"])
    if m > 6 or v > 2:
        raise ValueError("exact reference is limited to <=6 customers and <=2 vehicles")
    best: dict[str, Any] | None = None
    nodes = tuple(range(1, n))
    orders = {o["node"]: o for o in x["orders"]}
    # Assign each customer to a vehicle, then permute each vehicle's subsequence.
    for assignment in product(range(v), repeat=m):
        groups = [
            [nodes[i] for i, a in enumerate(assignment) if a == veh] for veh in range(v)
        ]
        candidates = [list(permutations(g)) for g in groups]
        for seqs in product(*candidates):
            routes = []
            feasible = True
            cost = 0
            for veh, seq in enumerate(seqs):
                if not seq:
                    continue
                if any(veh not in orders[k].get("allowed_vehicles", range(v)) for k in seq):
                    feasible = False
                    break
                if "vehicle_volumes_l" in x and sum(orders[k].get("volume_l", 0) for k in seq) > x["vehicle_volumes_l"][veh]:
                    feasible = False
                    break
                clearance_ok = True
                for k in seq:
                    dims = orders[k].get("upright_dimensions_mm")
                    if dims is not None and not ((dims[0] <= x["loading_width_mm"][veh] or dims[1] <= x["loading_width_mm"][veh]) and dims[2] <= x["loading_height_mm"][veh]):
                        clearance_ok = False
                if not clearance_ok:
                    feasible = False
                    break
                load = sum(orders[k]["demand_kg"] for k in seq)
                if load > x["vehicle_capacities_kg"][veh]:
                    feasible = False
                    break
                now = x["shift_start_s"]
                prev = 0
                route = [0]
                tt = []
                for node in seq:
                    now += x["time_s"][prev][node]
                    now = max(now, orders[node]["open_s"])
                    o = orders[node]
                    if now + o["service_s"] > o["close_s"]:
                        feasible = False
                        break
                    tt.append(
                        {
                            "node": node,
                            "service_start_s": now,
                            "service_finish_s": now + o["service_s"],
                        }
                    )
                    now += o["service_s"]
                    cost += x["distance_m"][prev][node]
                    prev = node
                    route.append(node)
                if not feasible:
                    break
                now += x["time_s"][prev][0]
                cost += x["distance_m"][prev][0]
                if now > x["shift_end_s"]:
                    feasible = False
                    break
                route.append(0)
                routes.append({"vehicle": veh, "nodes": route, "timetable": tt})
            if feasible and (best is None or cost < best["distance_m"]):
                best = {"status": "FEASIBLE", "routes": routes, "distance_m": cost}
    return best or {"status": "NO_FEASIBLE_SOLUTION", "routes": [], "distance_m": None}
