"""Generate a candidate corpus from public geography and dated visual records only."""

from __future__ import annotations
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent / "data"
OUT = ROOT / "research/eval-op-v2"
# Manually specified novel case mechanisms; site indexes reference the original register.
DESIGNS = [
    (
        "Customer barrier versus booked service lane",
        (2, 0, 7),
        "supported",
        "ALDI customer parking barrier is not the booked freight route.",
    ),
    (
        "Lidl candidate door versus booking channel",
        (3, 4, 9),
        "ask",
        "A side opening is not automatically a receiving door; the run has a synthetic dispatch-owned service-time release.",
    ),
    (
        "Unresolved Komok identity blocks a named booking",
        (5, 2, 10),
        "unknown",
        "The business named by the booking is not identified by the available visual evidence; the synthetic run-specific service-time release is unavailable; the numeric contract models this as an indispensable missing slot rather than independently verifying identity.",
    ),
    (
        "Curb visibility versus dispatch permission",
        (6, 0, 8),
        "tool",
        "A visible curb is not a permit; use only the synthetic dispatch service-time record.",
    ),
    (
        "Separated consignments and vehicle aperture",
        (1, 10, 11),
        "aperture",
        "An issuer-owned synthetic equipment inventory, not an image, fixes package and vehicle aperture values.",
    ),
    (
        "Combined load exceeds dispatch fleet",
        (9, 4, 7),
        "mass_short",
        "Synthetic gross consignment mass exceeds synthetic residual fleet payload.",
    ),
    (
        "Service duration beyond synthetic dispatch cutoff",
        (11, 8, 1),
        "time_short",
        "Synthetic loading and receiving records set a hard finish window.",
    ),
    (
        "Conflicting booking-specific service releases",
        (0, 3, 6),
        "conflict",
        "Two same-authority active synthetic records disagree and neither supersedes the other.",
    ),
    (
        "Customer park and freight vehicle assignment",
        (2, 10, 1),
        "restriction",
        "The pictured customer barrier does not govern the separately synthetic service lane and vehicle assignment.",
    ),
    (
        "Named site unresolved with expired identity record",
        (5, 8, 4),
        "expired",
        "Vaillant signage does not authenticate Komok; the only synthetic service-time record is expired.",
    ),
    (
        "Operator-released turnaround after incomplete estimate",
        (7, 11, 9),
        "estimate",
        "An approximate service estimate is not a confirmed operational allowance.",
    ),
    (
        "Two distinct vehicle capabilities and secured order",
        (4, 6, 0),
        "capabilities",
        "A synthetic carrier instruction restricts one order to a specified vehicle.",
    ),
    (
        "Released warehouse mass forces split beyond fleet",
        (8, 3, 2),
        "mass_indivisible",
        "The three indivisible synthetic consignments cannot be allocated to the two specified vehicles.",
    ),
    (
        "Matching targets with no receiver authority",
        (6, 5, 11),
        "unsigned",
        "Neither visible shutters nor a target coordinate supply delivery permission.",
    ),
    (
        "Known planning allowance and later synthetic booking window",
        (10, 7, 3),
        "window",
        "Synthetic dispatch-owned planning opening and service inputs are separated from the visual record.",
    ),
    (
        "Freight appointment and contradictory old image",
        (1, 2, 9),
        "replacement",
        "A superseding synthetic run-specific service record changes the service allowance; visual history does not decide its authority.",
    ),
]


def build():
    sites = list(
        csv.DictReader((ROOT / "evidence/stage1/geography/selected-sites.csv").open())
    )
    edges = {
        (r["origin"], r["destination"]): r
        for r in csv.DictReader(
            (ROOT / "evidence/stage2/geography/distance-matrix.csv").open()
        )
    }
    visuals = json.loads(
        (ROOT / "research/streetview/second-pass-observations.json").read_text()
    )
    worlds = []
    for num, (title, indexes, kind, note) in enumerate(DESIGNS, 1):
        wid = f"OPV2-{num:02}"
        ids = [sites[i]["id"] for i in indexes]
        nodes = ["depot", *ids]

        def matrix(field):
            return [
                [0 if a == b else round(float(edges[a, b][field])) for b in nodes]
                for a in nodes
            ]

        visual = []
        for label, pid in zip("ABC", ids):
            records = [r for r in visuals if r["candidate_poi_uuid"] == pid]
            chosen = records[0]
            visual.append(
                {
                    "site": label,
                    "poi_uuid": pid,
                    "source_kind": "historical_ai_assisted_visual_observation",
                    "source_file": chosen["filename"],
                    "source_sha256": chosen["sha256"],
                    "panorama_date": chosen["panorama_date"],
                    "observation": chosen["visible_observation"],
                    "qualification": "Map target is not camera or confirmed receiving entrance; current identity and permission are unverified.",
                }
            )
        orders = [
            {"node": n, "demand_kg": 30, "service_s": 300, "open_s": 0, "close_s": 7200}
            for n in (1, 2, 3)
        ]
        routing = {
            "depot": 0,
            "distance_m": matrix("distance_m"),
            "time_s": matrix("time_20kmh_s"),
            "vehicle_capacities_kg": [100, 80],
            "shift_start_s": 0,
            "shift_end_s": 10800,
            "orders": orders,
        }
        public = {
            "entity": wid + "-BOOKING",
            "scope": wid + "-RUN",
            "presentation": "normalized-facts-v1",
            "site_mapping": dict(zip(["DEPOT", "A", "B", "C"], nodes)),
            "clock": "routing seconds after 08:00 Europe/Rome; source validity uses logical epochs",
            "current_parameters": {},
            "current_routes": [
                {"vehicle": 0, "nodes": [0, 1, 2, 0]},
                {"vehicle": 1, "nodes": [0, 3, 0]},
            ],
            "source_discovery": "consult_released_candidate_updates",
            "bindings": {},
            "required_slots": [],
            "optional_slots": ["driver_preference"],
            "channels": {},
            "authority_policy": {
                "dispatcher": "the simulated dispatch office owns run-specific planning allowances, not receiver permissions",
                "receiver": "no receiver-issued source is asserted in these synthetic cases",
            },
            "snapshot_provenance": "ALL operational bookings, vehicles, fleet access, loads, service, permissions, depot and windows are synthetic scenario premises; archived OSM-derived distances and 20 km/h travel proxy do not prove truck access.",
            "site_evidence": visual,
            "site_evidence_note": note,
            "evidence_boundary": "Photos establish only described historical visible features. Customer entrances are not freight entrances; a sidewalk or curb is not loading permission. Site identification and actual legal access remain unknown. The scenario explicitly stipulates hypothetical site-specific conditions where disclosed; these are not real-world verified facts.",
        }
        d = {
            "id": wid,
            "title": title,
            "interface": "operational-v1",
            "instruction": "Plan all mandatory indivisible deliveries for the hypothetical run. A run-specific dispatch-owned service-time release is indispensable for site A. Apply only the disclosed scenario assumptions and scoped records; do not treat imagery as freight permission.",
            "epoch": 200,
            "effective_time": 220,
            "presentation": "normalized-facts-v1",
            "public": public,
            "routing": routing,
            "records": [],
            "authoring": {
                "review_status": "candidate_not_researcher_approved_or_frozen",
                "mechanism_family": kind,
                "provenance": "synthetic scenario records; public audited visuals; no prior capture inputs",
                "scenario_assumption_note": note,
            },
        }

        def bind(slot, path, unit="seconds", user="unavailable", tool="unavailable"):
            target = routing
            for x in path:
                target = target[x]
            public["required_slots"].append(slot)
            public["current_parameters"][slot] = target
            public["bindings"][slot] = {
                "path": path,
                "owner": "dispatcher",
                "unit": unit,
                "permitted_issuer_roles": ["dispatcher"],
                "required_assertion_kind": "certified_fact",
            }
            public["channels"][slot] = {"user": user, "tool": tool}

        def record(slot, value, suffix, **kw):
            rid = f"{wid}-{suffix}"
            r = {
                "id": rid,
                "slot": slot,
                "value": value,
                "owner": "dispatcher",
                "verified": True,
                "authority": "confirmed",
                "precision": "confirmed",
                "entity": public["entity"],
                "scope": public["scope"],
                "available_at": 180,
                "effective_from": 210,
                "effective_to": 260,
                "channel": "public",
                "issuer_role": "dispatcher",
                "assertion_kind": "certified_fact",
                "source_document": rid,
                "supersedes": [],
                "text": f"Synthetic issuer-owned run-specific release: service or planning allowance for {slot} is {value} seconds. This is a hypothetical scenario document, not a real receiver statement.",
            }
            r.update(kw)
            d["records"].append(r)
            return rid

        bind(
            "service_A_s",
            ["orders", 0, "service_s"],
            user="unknown" if kind in ("ask", "estimate") else "unavailable",
            tool="unknown" if kind in ("tool", "replacement") else "unavailable",
        )
        if kind in ("unknown", "unsigned", "expired"):
            if kind == "unsigned":
                record("service_A_s", 300, "UNSIGNED", verified=False)
            if kind == "expired":
                record("service_A_s", 300, "EXPIRED", effective_to=219)
        elif kind == "conflict":
            record("service_A_s", 300, "RELEASE1")
            record("service_A_s", 540, "RELEASE2")
        elif kind == "ask":
            record("service_A_s", 420, "RELEASE", channel="user")
        elif kind == "tool":
            record("service_A_s", 480, "RELEASE", channel="tool")
        elif kind == "estimate":
            record("service_A_s", 600, "ESTIMATE", precision="approximate")
            record("service_A_s", 480, "RELEASE", channel="user")
        elif kind == "replacement":
            old = record("service_A_s", 300, "OLD", available_at=150)
            record("service_A_s", 480, "REPLACEMENT", channel="tool", supersedes=[old])
        else:
            record("service_A_s", 300, "RELEASE")
        if kind == "aperture":
            routing["loading_width_mm"] = [900, 1200]
            routing["loading_height_mm"] = [1500, 2000]
            orders[0]["upright_dimensions_mm"] = [1100, 1000, 1800]
            public["synthetic_physical_inventory"] = (
                "Synthetic: rigid A package is 1100 x 1000 x 1800 mm; vehicle 0 aperture 900 x 1500 mm and vehicle 1 aperture 1200 x 2000 mm. The upright package can rotate in its footprint."
            )
        if kind in ("restriction", "capabilities"):
            orders[0]["allowed_vehicles"] = [1]
            public["synthetic_vehicle_assignment"] = (
                "For this hypothetical run, issuer-owned policy restricts site A to vehicle 1; it is not derived from the image."
            )
        if kind == "mass_short":
            orders[0]["demand_kg"] = 150
            orders[1]["demand_kg"] = 80
        if kind == "mass_indivisible":
            routing["vehicle_capacities_kg"] = [100, 100]
            for o in orders:
                o["demand_kg"] = 60
        if kind == "time_short":
            orders[0]["close_s"] = 240
        if kind == "window":
            orders[0]["open_s"] = 1800
            orders[0]["close_s"] = 5400
        # Numeric physical and schedule inputs are separately source-bound; the
        # qualifying record is hypothetical and never an external site fact.
        if kind in ("mass_short", "mass_indivisible"):
            bind("load_A_kg", ["orders", 0, "demand_kg"], unit="kg")
            record(
                "load_A_kg",
                orders[0]["demand_kg"],
                "MASS",
                text=f"Synthetic dispatch manifest: certified gross mass is {orders[0]['demand_kg']} kg, including packaging.",
            )
        if kind == "time_short":
            bind("close_A_s", ["orders", 0, "close_s"])
            record(
                "close_A_s",
                240,
                "CUTOFF",
                text="Synthetic dispatch planning instruction: complete service by 08:04 for this run.",
            )
        if kind == "window":
            bind("open_A_s", ["orders", 0, "open_s"])
            record(
                "open_A_s",
                1800,
                "OPEN",
                text="Synthetic dispatch planning instruction: do not begin service before 08:30 for this run.",
            )
        if kind == "aperture":
            bind("width_A_mm", ["orders", 0, "upright_dimensions_mm", 1], unit="mm")
            record(
                "width_A_mm",
                1000,
                "PACKAGE",
                text="Synthetic carrier record: upright package dimensions are 1100 x 1000 x 1800 mm.",
            )
        if kind == "supported":
            # Stipulated prior plan; references still accept any feasible alternative.
            public["current_routes"] = [{"vehicle": 0, "nodes": [0, 3, 2, 1, 0]}]
        public["synthetic_routing_scope"] = (
            "All unbound routing data, delivery-route authorization, actual node positions, fleet and operating conditions are hypothetical inputs, not externally verified premises. If an indispensable planning record is absent or contradictory, do not commit the modeled plan."
        )
        worlds.append(d)
    return worlds


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT / "scenarios.json").write_text(
        json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    )


if __name__ == "__main__":
    main()
