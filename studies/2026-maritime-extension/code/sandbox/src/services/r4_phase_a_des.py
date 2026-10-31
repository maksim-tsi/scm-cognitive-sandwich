"""Contract-conformant provider-free cargo-lot DES for R4 Phase-A V&V.

This is a terminating literature-parameterized stochastic testbed, not a
calibrated digital twin.  Scientific execution is outside this module's Phase-A
authority; every returned row is labelled ``offline_fixture`` unless a later
caller supplies another explicit mode under separate authority.
"""
from __future__ import annotations

import hashlib
import heapq
import math
import random
from dataclasses import asdict, dataclass
from typing import Any

HORIZON_HOURS = 168.0
CRN_COMPONENTS = ("transfer_delay", "port_service", "cargo_dwell")
VARIANTS = {
    "base": (0.20, 0.25, 1.0),
    "transfer_cv_low": (0.10, 0.25, 1.0),
    "transfer_cv_high": (0.40, 0.25, 1.0),
    "service_cv_low": (0.20, 0.10, 1.0),
    "service_cv_high": (0.20, 0.50, 1.0),
    "dwell_scale_low": (0.20, 0.25, 0.80),
    "dwell_scale_high": (0.20, 0.25, 1.20),
}


@dataclass(frozen=True)
class CRNKey:
    incident_id: str
    generation_id: int
    replication_id: int
    stochastic_component: str

    def seed(self) -> int:
        if self.stochastic_component not in CRN_COMPONENTS:
            raise ValueError("unknown frozen CRN component")
        raw = (
            f"{self.incident_id}:{self.generation_id}:{self.replication_id}:"
            f"{self.stochastic_component}"
        ).encode()
        return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


@dataclass(frozen=True)
class DESResult:
    status: str
    mode: str
    variant_id: str
    incident_id: str
    generation_id: int
    replication_id: int
    total_generalized_operational_cost: float
    mean_cargo_delay_hours: float
    max_cargo_delay_hours: float
    mean_queue_wait_hours: float
    max_queue_wait_hours: float
    mean_yard_occupancy_teu: float
    max_yard_occupancy_teu: float
    completed_teu: float
    incomplete_teu: float
    conservation_ok: bool
    resource_bounds_ok: bool
    event_order_ok: bool
    horizon_hours: float
    event_count: int
    stochastic_draws_sha256: str
    # Compatibility aliases for earlier provider-free fixture consumers.
    total_cost: float
    total_time_hours: float
    stochastic_component: str


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def validate_artifact_for_des(
    incident: dict[str, Any], artifact: dict[str, Any]
) -> tuple[bool, str | None]:
    if artifact.get("incident_id") != incident.get("incident_id"):
        return False, "INCIDENT_ID_MISMATCH"
    if artifact.get("condition") not in {"gate_only", "structured_repair"}:
        return False, "CONDITION_OUT_OF_SCOPE"
    lots = {lot["lot_id"]: float(lot["declared_teu"]) for lot in incident.get("cargo_lots", [])}
    options = {row["option_id"] for row in incident.get("transfer_options", [])}
    allocated_by_lot = {lot_id: 0.0 for lot_id in lots}
    for allocation in artifact.get("allocations", []):
        lot_id = allocation.get("lot_id")
        option_id = allocation.get("option_id")
        amount = allocation.get("allocated_teu")
        if lot_id not in lots or option_id not in options or not _finite_nonnegative(amount):
            return False, "ALLOCATION_DOMAIN"
        allocated_by_lot[lot_id] += float(amount)
    shortfall = {
        row.get("lot_id"): row.get("unallocated_teu")
        for row in artifact.get("unallocated_by_lot", [])
    }
    if set(shortfall) != set(lots) or any(
        not _finite_nonnegative(value) for value in shortfall.values()
    ):
        return False, "SHORTFALL_DOMAIN"
    if any(
        abs(allocated_by_lot[lot_id] + float(shortfall[lot_id]) - declared) > 1e-6
        or float(shortfall[lot_id]) > 1e-6
        for lot_id, declared in lots.items()
    ):
        return False, "DEMAND_CONSERVATION"
    return True, None


def _gamma_mean_one(rng: random.Random, cv: float) -> float:
    shape = 1.0 / (cv * cv)
    return rng.gammavariate(shape, 1.0 / shape)


def _lognormal_mean_one(rng: random.Random, cv: float) -> float:
    sigma2 = math.log1p(cv * cv)
    return rng.lognormvariate(-0.5 * sigma2, math.sqrt(sigma2))


def _excluded(
    incident: dict[str, Any],
    artifact: dict[str, Any],
    replication_id: int,
    mode: str,
    variant_id: str,
) -> DESResult:
    declared = sum(float(lot.get("declared_teu", 0)) for lot in incident.get("cargo_lots", []))
    return DESResult(
        "EXCLUDED", mode, variant_id, str(incident.get("incident_id", "")),
        int(artifact.get("generation_id", 0)), replication_id, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, declared, False, False, False,
        HORIZON_HOURS, 0, "", 0.0, 0.0, "all"
    )


def run_replication(
    incident: dict[str, Any],
    artifact: dict[str, Any],
    *,
    replication_id: int,
    mode: str = "offline_fixture",
    variant_id: str = "base",
    stochastic_component: str = "all",
) -> DESResult:
    """Run one finite-horizon replication using three independent CRN streams.

    ``variant_id`` changes distribution parameters only.  It is deliberately
    absent from every seed, so base and OAT variants reuse identical uniforms.
    """
    valid, _ = validate_artifact_for_des(incident, artifact)
    if not valid or variant_id not in VARIANTS or replication_id < 1:
        return _excluded(incident, artifact, replication_id, mode, variant_id)
    generation_id = int(artifact.get("generation_id", 0))
    streams = {
        component: random.Random(
            CRNKey(incident["incident_id"], generation_id, replication_id, component).seed()
        )
        for component in CRN_COMPONENTS
    }
    transfer_cv, service_cv, dwell_scale = VARIANTS[variant_id]
    options = {row["option_id"]: row for row in incident["transfer_options"]}
    ports = {row["port_id"]: row for row in incident["alternative_ports"]}
    port_available = {port_id: 0.0 for port_id in ports}
    yard_releases: dict[str, list[tuple[float, float]]] = {port_id: [] for port_id in ports}
    yard_occupancy = {port_id: 0.0 for port_id in ports}
    max_yard = {port_id: 0.0 for port_id in ports}
    completed = 0.0
    delays: list[float] = []
    waits: list[float] = []
    occupancy_samples: list[float] = []
    total_cost = 0.0
    event_count = 1  # artifact admission
    event_order_ok = True
    resource_bounds_ok = True
    draw_log: list[tuple[str, float]] = []

    movements: list[tuple[float, dict[str, Any], dict[str, Any], float]] = []
    for allocation in artifact["allocations"]:
        amount = float(allocation["allocated_teu"])
        option = options[allocation["option_id"]]
        transfer_multiplier = _gamma_mean_one(streams["transfer_delay"], transfer_cv)
        arrival = float(option["transfer_time_hours"]) * transfer_multiplier
        movements.append((arrival, allocation, option, amount))
        draw_log.append(("transfer_delay", transfer_multiplier))
        event_count += 2  # departure and arrival

    for arrival, _allocation, option, amount in sorted(
        movements, key=lambda row: (row[0], row[1]["lot_id"], row[1]["option_id"])
    ):
        port_id = option["port_id"]
        port = ports[port_id]
        service_multiplier = _lognormal_mean_one(streams["port_service"], service_cv)
        service_duration = amount / float(port["nominal_service_teu_per_hour"]) * service_multiplier
        service_start = max(arrival, port_available[port_id])
        wait = service_start - arrival
        service_end = service_start + service_duration
        port_available[port_id] = service_end
        waits.append(wait)
        draw_log.append(("port_service", service_multiplier))
        event_count += 3  # queue entry, service start, service completion

        releases = yard_releases[port_id]
        while releases and releases[0][0] <= service_end:
            _, released = heapq.heappop(releases)
            yard_occupancy[port_id] -= released
        yard_admit = service_end
        while (
            yard_occupancy[port_id] + amount > float(port["yard_capacity_teu"]) + 1e-9
            and releases
        ):
            yard_admit, released = heapq.heappop(releases)
            yard_occupancy[port_id] -= released
            while releases and releases[0][0] <= yard_admit:
                _, released = heapq.heappop(releases)
                yard_occupancy[port_id] -= released
        if yard_occupancy[port_id] + amount > float(port["yard_capacity_teu"]) + 1e-6:
            resource_bounds_ok = False
            continue
        dwell_hours = streams["cargo_dwell"].triangular(24.0, 168.0, 96.0) * dwell_scale
        draw_log.append(("cargo_dwell", dwell_hours))
        completion = yard_admit + dwell_hours
        yard_occupancy[port_id] += amount
        max_yard[port_id] = max(max_yard[port_id], yard_occupancy[port_id])
        occupancy_samples.append(yard_occupancy[port_id])
        heapq.heappush(releases, (completion, amount))
        event_count += 1  # dwell completion is scheduled even beyond horizon
        event_order_ok = event_order_ok and (
            0.0 <= arrival <= service_start <= service_end <= yard_admit <= completion
        )
        delay = completion
        delays.append(delay)
        total_cost += amount * float(option["transfer_cost_per_teu"]) + amount * delay
        if completion <= HORIZON_HOURS:
            completed += amount

    event_count += 1  # horizon termination
    declared = sum(float(lot["declared_teu"]) for lot in incident["cargo_lots"])
    incomplete = max(0.0, declared - completed)
    conservation_ok = abs(completed + incomplete - declared) <= 1e-6
    draws_sha = hashlib.sha256(
        repr([(name, round(value, 12)) for name, value in draw_log]).encode()
    ).hexdigest()
    mean_delay = sum(delays) / len(delays) if delays else 0.0
    mean_wait = sum(waits) / len(waits) if waits else 0.0
    mean_yard = sum(occupancy_samples) / len(occupancy_samples) if occupancy_samples else 0.0
    status = "COMPLETED" if incomplete <= 1e-6 else "INCOMPLETE_HORIZON"
    return DESResult(
        status, mode, variant_id, incident["incident_id"], generation_id,
        replication_id, total_cost, mean_delay, max(delays, default=0.0),
        mean_wait, max(waits, default=0.0), mean_yard,
        max(max_yard.values(), default=0.0), completed, incomplete,
        conservation_ok, resource_bounds_ok, event_order_ok, HORIZON_HOURS,
        event_count, draws_sha, total_cost, mean_delay, stochastic_component,
    )


def run_fixture(
    incident: dict[str, Any],
    artifact: dict[str, Any],
    replications: int = 10,
    variant_id: str = "base",
) -> list[dict[str, Any]]:
    if replications < 1 or replications > 5000:
        raise ValueError("offline fixture replication bound exceeded")
    return [
        asdict(
            run_replication(
                incident, artifact, replication_id=index, variant_id=variant_id
            )
        )
        for index in range(1, replications + 1)
    ]
