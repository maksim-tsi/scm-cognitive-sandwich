"""Deterministic R2 population candidates; no model or DES execution."""

import json
from dataclasses import dataclass
from hashlib import sha256
from random import Random
from typing import Any

from src.services.allocation_reference import (
    AllocationRequest,
    TransferOption,
    strict_reference,
)


@dataclass(frozen=True)
class ScenarioCandidate:
    candidate_id: str
    stratum_id: str
    affected_demand_ratio: float
    eligible_capacity_ratio: float
    accepted: bool
    rejection_reason: str | None


@dataclass(frozen=True)
class PopulationManifest:
    accepted: tuple[ScenarioCandidate, ...]
    rejected: tuple[ScenarioCandidate, ...]


STRATA = {
    "S1-MODERATE-DISRUPTION-LOW-PRESSURE": ((0.10, 0.30), (1.50, 2.00)),
    "S2-MODERATE-DISRUPTION-HIGH-PRESSURE": ((0.10, 0.30), (1.00, 1.20)),
    "S3-HIGH-DISRUPTION-LOW-PRESSURE": ((0.30, 0.50), (1.50, 2.00)),
    "S4-HIGH-DISRUPTION-HIGH-PRESSURE": ((0.30, 0.50), (1.00, 1.20)),
}

INCIDENTS_PER_STRATUM = 15
MAX_CANDIDATES_PER_STRATUM = 150
ELIGIBLE_OPTION_IDS = ("O1", "O2", "O3")


def generation_seed(base: int, incident_id: str, generation_index: int) -> int:
    raw = f"{base}:{incident_id}:{generation_index}".encode()
    return int.from_bytes(sha256(raw).digest()[:8], "big")


def generate_candidate(stratum_id: str, index: int, seed: int = 202601) -> ScenarioCandidate:
    if stratum_id not in STRATA:
        raise ValueError(f"unknown frozen stratum: {stratum_id}")
    if index < 1:
        raise ValueError("candidate index must be positive")
    demand_range, capacity_range = STRATA[stratum_id]
    rng = Random(f"{seed}:{stratum_id}:{index}")
    demand = rng.uniform(*demand_range)
    capacity = rng.uniform(*capacity_range)
    accepted = (
        demand_range[0] <= demand < demand_range[1]
        and capacity_range[0] <= capacity <= capacity_range[1]
    )
    rejection_reason = None if accepted else "OUT_OF_STRATUM"
    return ScenarioCandidate(
        f"{stratum_id}-{index:04d}",
        stratum_id,
        demand,
        capacity,
        accepted,
        rejection_reason,
    )


def _incident_inputs(
    candidate: ScenarioCandidate,
) -> tuple[list[AllocationRequest], list[TransferOption]]:
    """Build a bounded, fixed-alternative incident with enough aggregate capacity."""
    rng = Random(f"incident:{candidate.candidate_id}")
    affected_teu = 100 + int(candidate.affected_demand_ratio * 900)
    parts = [affected_teu // 4] * 4
    for index in range(affected_teu % 4):
        parts[index] += 1
    lots = [
        AllocationRequest(
            f"{candidate.candidate_id}-L{index + 1}",
            part,
            ELIGIBLE_OPTION_IDS,
        )
        for index, part in enumerate(parts)
    ]
    capacity = candidate.eligible_capacity_ratio * affected_teu
    port_capacity = capacity / 3
    options = [
        TransferOption("O1", "P1", port_capacity, rng.uniform(1.0, 10.0)),
        TransferOption("O2", "P2", port_capacity, rng.uniform(1.0, 10.0)),
        TransferOption("O3", "P3", port_capacity, rng.uniform(1.0, 10.0)),
    ]
    return lots, options


def build_population_manifest(seed: int = 202601) -> PopulationManifest:
    """Retain exactly 15 strict-feasible incidents per frozen stratum.

    Candidate order is stratum order then index.  Rejections are retained in
    the manifest result rather than being retried silently. Candidate search
    fails closed at a fixed implementation safety cap instead of running
    indefinitely when a stratum cannot produce a feasible incident.
    """
    accepted: list[ScenarioCandidate] = []
    rejected: list[ScenarioCandidate] = []
    for stratum_id in STRATA:
        retained = 0
        for index in range(1, MAX_CANDIDATES_PER_STRATUM + 1):
            candidate = generate_candidate(stratum_id, index, seed)
            lots, options = _incident_inputs(candidate)
            if strict_reference(lots, options).status == "OPTIMAL":
                accepted.append(candidate)
                retained += 1
                if retained == INCIDENTS_PER_STRATUM:
                    break
            else:
                rejected.append(
                    ScenarioCandidate(
                        candidate.candidate_id,
                        candidate.stratum_id,
                        candidate.affected_demand_ratio,
                        candidate.eligible_capacity_ratio,
                        False,
                        "STRICT_REFERENCE_INFEASIBLE",
                    )
                )
        else:
            raise RuntimeError(
                f"candidate cap exhausted for {stratum_id}: retained {retained} "
                f"of {INCIDENTS_PER_STRATUM} after {MAX_CANDIDATES_PER_STRATUM} candidates"
            )
    return PopulationManifest(tuple(accepted), tuple(rejected))


def manifest_sha256(manifest: PopulationManifest) -> str:
    """Return a stable hash over bounded candidate metadata, not full payloads."""
    payload = {
        "accepted": [candidate.__dict__ for candidate in manifest.accepted],
        "rejected": [candidate.__dict__ for candidate in manifest.rejected],
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def manifest_export(manifest: PopulationManifest) -> dict[str, Any]:
    """Export bounded population provenance without retaining incident payloads."""
    def record(candidate: ScenarioCandidate) -> dict[str, Any]:
        return {
            "incident_id": candidate.candidate_id,
            "stratum_id": candidate.stratum_id,
            "candidate_sha256": sha256(
                json.dumps(candidate.__dict__, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "rejection_reason": candidate.rejection_reason,
        }

    return {
        "manifest_sha256": manifest_sha256(manifest),
        "accepted_count": len(manifest.accepted),
        "rejected_count": len(manifest.rejected),
        "accepted": [record(candidate) for candidate in manifest.accepted],
        "rejected": [record(candidate) for candidate in manifest.rejected],
    }


def complete_incident_payload(
    candidate: ScenarioCandidate, generation_id: int = 1
) -> dict[str, Any]:
    """Materialize the full R2 incident interface, including nested identities.

    The legacy manifest export intentionally keeps only bounded metadata.  This
    Phase-A helper is the canonical non-sensitive payload materializer used by
    the research repository; it never contacts a provider or execution service.
    """
    lots, options = _incident_inputs(candidate)
    rng = Random(generation_seed(202602, candidate.candidate_id, generation_id))
    ports = [
        {
            "port_id": f"{candidate.candidate_id}-PORT-{index}",
            "available_teu": round(option.available_teu, 6),
            "nominal_service_teu_per_hour": 40.0,
            "yard_capacity_teu": 600.0,
        }
        for index, option in enumerate(options, start=1)
    ]
    port_by_legacy = {
        option.option_id: ports[index]["port_id"]
        for index, option in enumerate(options)
    }
    transfer_options = [
        {
            "option_id": f"{candidate.candidate_id}-OPTION-{index}",
            "port_id": port_by_legacy[option.option_id],
            "transfer_cost_per_teu": round(1.0 + rng.random() * 8.0, 6),
            "transfer_time_hours": round(2.0 + rng.random() * 18.0, 6),
        }
        for index, option in enumerate(options, start=1)
    ]
    option_ids = [item["option_id"] for item in transfer_options]
    cargo_lots = [
        {
            "lot_id": f"{candidate.candidate_id}-LOT-{index + 1}",
            "declared_teu": float(lot.declared_teu),
            "eligible_option_ids": option_ids[:],
        }
        for index, lot in enumerate(lots)
    ]
    return {
        "incident_id": candidate.candidate_id,
        "decision_epoch": "2026-08-24T00:00:00Z",
        "planning_horizon_hours": 168.0,
        "cargo_lots": cargo_lots,
        "alternative_ports": ports,
        "transfer_options": transfer_options,
        "generalized_cost_weights": {"cost_weight": 1.0, "time_weight": 1.0},
        "stratum_id": candidate.stratum_id,
        "population_seed": 202601,
        "generation_seed": generation_seed(202602, candidate.candidate_id, generation_id),
    }


def complete_population_inputs(seed: int = 202601) -> dict[str, Any]:
    """Return exactly 60 incidents and three generation identities each."""
    manifest = build_population_manifest(seed)
    incidents = [complete_incident_payload(candidate) for candidate in manifest.accepted]
    units = [
        {
            "unit_id": f"{incident['incident_id']}-GEN-{generation_id:03d}",
            "incident_id": incident["incident_id"],
            "generation_id": generation_id,
            "input": incident,
            "generation_seed": generation_seed(202602, incident["incident_id"], generation_id),
        }
        for incident in incidents
        for generation_id in range(1, 4)
    ]
    return {
        "schema_version": "1.0",
        "status": "PHASE_A_PROVIDER_FREE_MATERIALIZED",
        "population_seed": seed,
        "incidents": incidents,
        "units": units,
        "rejected_candidates": [record.__dict__ for record in manifest.rejected],
    }
