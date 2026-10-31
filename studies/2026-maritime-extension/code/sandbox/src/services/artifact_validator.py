"""Deterministic R2 artifact checks with traceable, localized violations."""

from dataclasses import dataclass
from math import isfinite

from src.services.allocation_reference import AllocationRequest, TransferOption

QUANTITY_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ArtifactAllocation:
    lot_id: str
    option_id: str
    allocated_teu: float


@dataclass(frozen=True)
class ArtifactShortfall:
    lot_id: str
    unallocated_teu: float


@dataclass(frozen=True)
class ValidationResult:
    schema_valid: bool
    feasible: bool
    violations: tuple[str, ...]
    semantic_valid: bool = True


def evaluate_artifact(
    lots: list[AllocationRequest],
    options: list[TransferOption],
    allocations: list[ArtifactAllocation],
    shortfalls: list[ArtifactShortfall],
) -> ValidationResult:
    """Check R2-C01 through R2-C05 without determining the cost reference."""
    lots_by_id = {lot.lot_id: lot for lot in lots}
    options_by_id = {option.option_id: option for option in options}
    violations: list[str] = []
    if len(lots_by_id) != len(lots) or len(options_by_id) != len(options):
        return ValidationResult(False, False, ("IDENTITY",))
    shortfall_by_lot = {entry.lot_id: entry.unallocated_teu for entry in shortfalls}
    if len(shortfall_by_lot) != len(shortfalls) or set(shortfall_by_lot) != set(lots_by_id):
        violations.append("IDENTITY")
    allocated_by_lot = {lot_id: 0.0 for lot_id in lots_by_id}
    allocated_by_port: dict[str, float] = {}
    for allocation in allocations:
        option = options_by_id.get(allocation.option_id)
        lot = lots_by_id.get(allocation.lot_id)
        if option is None or lot is None:
            violations.append("IDENTITY")
            continue
        if not isfinite(allocation.allocated_teu) or allocation.allocated_teu < 0:
            violations.append("NONNEGATIVITY")
            continue
        if allocation.option_id not in lot.eligible_option_ids:
            violations.append("ELIGIBILITY")
        allocated_by_lot[allocation.lot_id] += allocation.allocated_teu
        allocated_by_port[option.port_id] = (
            allocated_by_port.get(option.port_id, 0.0) + allocation.allocated_teu
        )
    capacities: dict[str, float] = {}
    for option in options:
        existing = capacities.setdefault(option.port_id, option.available_teu)
        if existing != option.available_teu:
            violations.append("PORT_CAPACITY")
    for port_id, amount in allocated_by_port.items():
        if amount > capacities[port_id] + QUANTITY_TOLERANCE:
            violations.append("PORT_CAPACITY")
    for lot_id, lot in lots_by_id.items():
        shortfall = shortfall_by_lot.get(lot_id)
        if shortfall is None or not isfinite(shortfall) or shortfall < 0:
            violations.append("NONNEGATIVITY")
            continue
        if abs(allocated_by_lot[lot_id] + shortfall - lot.declared_teu) > QUANTITY_TOLERANCE:
            violations.append("CONSERVATION")
        if shortfall > QUANTITY_TOLERANCE:
            violations.append("UNALLOCATED_DEMAND")
    unique = tuple(dict.fromkeys(violations))
    return ValidationResult(not unique, not unique, unique)
