"""Frozen R2 strict-reference and diagnostic allocation models for R3.

The strict model deliberately has no shortfall variable.  The separate
diagnostic model may expose per-lot shortfall, but it never returns a cost
reference and cannot support DES admission.
"""

from dataclasses import dataclass
from typing import Any

import pyomo.environ as pyo


@dataclass(frozen=True)
class AllocationRequest:
    lot_id: str
    declared_teu: float
    eligible_option_ids: tuple[str, ...]


@dataclass(frozen=True)
class TransferOption:
    option_id: str
    port_id: str
    available_teu: float
    generalized_cost_per_teu: float


@dataclass(frozen=True)
class ReferenceResult:
    status: str
    allocations: dict[tuple[str, str], float]
    total_cost: float | None
    shortfall_by_lot: dict[str, float]


def _validate_inputs(
    lots: list[AllocationRequest], options: list[TransferOption]
) -> tuple[dict[str, AllocationRequest], dict[str, TransferOption]]:
    """Fail closed before building a reference model from malformed identities."""
    lots_by_id = {lot.lot_id: lot for lot in lots}
    options_by_id = {option.option_id: option for option in options}
    if len(lots_by_id) != len(lots) or len(options_by_id) != len(options):
        raise ValueError("lot and option identifiers must be unique")
    for lot in lots:
        if lot.declared_teu <= 0:
            raise ValueError("declared TEU must be positive")
        if not lot.eligible_option_ids:
            raise ValueError("every lot must declare an eligible option")
        if not set(lot.eligible_option_ids) <= options_by_id.keys():
            raise ValueError("lot references an unknown eligible option")
    for option in options:
        if option.available_teu < 0 or option.generalized_cost_per_teu < 0:
            raise ValueError("capacity and generalized cost must be nonnegative")
    return lots_by_id, options_by_id


def _port_capacities(options: list[TransferOption]) -> dict[str, float]:
    """Require one capacity value per port; transfer options cannot multiply it."""
    capacities: dict[str, float] = {}
    for option in options:
        existing = capacities.setdefault(option.port_id, option.available_teu)
        if existing != option.available_teu:
            raise ValueError("all transfer options for a port must share available TEU")
    return capacities


def _status(results: Any) -> str:
    termination = results.solver.termination_condition
    if termination == pyo.TerminationCondition.optimal:
        return "OPTIMAL"
    if termination == pyo.TerminationCondition.infeasible:
        return "INFEASIBLE"
    if termination == pyo.TerminationCondition.unbounded:
        return "UNBOUNDED"
    return "UNKNOWN"


def _solve(model: pyo.ConcreteModel) -> str:
    """Inspect infeasibility without loading nonexistent solutions."""
    solver = pyo.SolverFactory("appsi_highs")
    results = solver.solve(model, tee=False, load_solutions=False)
    status = _status(results)
    if status == "OPTIMAL":
        solver.solve(model, tee=False)
    return status


def _strict_model(
    lots: list[AllocationRequest], options: list[TransferOption]
) -> tuple[pyo.ConcreteModel, list[tuple[str, str]]]:
    lots_by_id, options_by_id = _validate_inputs(lots, options)
    capacities = _port_capacities(options)
    pairs = [
        (lot.lot_id, option_id)
        for lot in lots
        for option_id in lot.eligible_option_ids
    ]
    model = pyo.ConcreteModel()
    model.pairs = pyo.Set(initialize=pairs, dimen=2)
    model.x = pyo.Var(model.pairs, within=pyo.NonNegativeReals)
    model.lot_ids = pyo.Set(initialize=list(lots_by_id))
    model.port_ids = pyo.Set(initialize=list(capacities))
    model.conservation = pyo.Constraint(
        model.lot_ids,
        rule=lambda _m, lot_id: sum(
            _m.x[lot_id, option_id] for lot, option_id in pairs if lot == lot_id
        )
        == lots_by_id[lot_id].declared_teu,
    )
    def capacity_rule(_m: pyo.ConcreteModel, port_id: str) -> Any:
        port_pairs = [
            (lot_id, option_id)
            for lot_id, option_id in pairs
            if options_by_id[option_id].port_id == port_id
        ]
        if not port_pairs:
            return pyo.Constraint.Skip
        return (
            sum(_m.x[lot_id, option_id] for lot_id, option_id in port_pairs)
            <= capacities[port_id]
        )

    model.capacity = pyo.Constraint(model.port_ids, rule=capacity_rule)
    model.cost = pyo.Objective(
        expr=sum(
            model.x[lot_id, option_id]
            * options_by_id[option_id].generalized_cost_per_teu
            for lot_id, option_id in pairs
        ),
        sense=pyo.minimize,
    )
    return model, pairs


def strict_reference(
    lots: list[AllocationRequest], options: list[TransferOption]
) -> ReferenceResult:
    """Solve the authoritative strict minimum-cost LP/MILP reference."""
    model, pairs = _strict_model(lots, options)
    status = _solve(model)
    if status != "OPTIMAL":
        return ReferenceResult(status, {}, None, {})
    allocations = {
        (lot_id, option_id): value
        for lot_id, option_id in pairs
        if (value := pyo.value(model.x[lot_id, option_id])) > 1e-6
    }
    return ReferenceResult("OPTIMAL", allocations, pyo.value(model.cost), {})


def diagnostic_shortfall(
    lots: list[AllocationRequest], options: list[TransferOption]
) -> ReferenceResult:
    """Diagnostic-only shortfall allocation; never a cost reference or DES admission."""
    strict = strict_reference(lots, options)
    if strict.status == "OPTIMAL":
        return strict
    lots_by_id, options_by_id = _validate_inputs(lots, options)
    capacities = _port_capacities(options)
    pairs = [
        (lot.lot_id, option_id)
        for lot in lots
        for option_id in lot.eligible_option_ids
    ]
    model = pyo.ConcreteModel()
    model.pairs = pyo.Set(initialize=pairs, dimen=2)
    model.lot_ids = pyo.Set(initialize=list(lots_by_id))
    model.x = pyo.Var(model.pairs, within=pyo.NonNegativeReals)
    model.u = pyo.Var(model.lot_ids, within=pyo.NonNegativeReals)
    model.conservation = pyo.Constraint(
        model.lot_ids,
        rule=lambda _m, lot_id: sum(
            _m.x[lot_id, option_id] for lot, option_id in pairs if lot == lot_id
        )
        + _m.u[lot_id]
        == lots_by_id[lot_id].declared_teu,
    )
    def capacity_rule(_m: pyo.ConcreteModel, port_id: str) -> Any:
        port_pairs = [
            (lot_id, option_id)
            for lot_id, option_id in pairs
            if options_by_id[option_id].port_id == port_id
        ]
        if not port_pairs:
            return pyo.Constraint.Skip
        return (
            sum(_m.x[lot_id, option_id] for lot_id, option_id in port_pairs)
            <= capacities[port_id]
        )

    model.capacity = pyo.Constraint(list(capacities), rule=capacity_rule)
    model.shortfall = pyo.Objective(
        expr=sum(model.u[lot_id] for lot_id in lots_by_id), sense=pyo.minimize
    )
    if _solve(model) != "OPTIMAL":
        return ReferenceResult("UNKNOWN", {}, None, {})
    allocations = {
        (lot_id, option_id): value
        for lot_id, option_id in pairs
        if (value := pyo.value(model.x[lot_id, option_id])) > 1e-6
    }
    shortfall = {lot_id: pyo.value(model.u[lot_id]) for lot_id in lots_by_id}
    return ReferenceResult("DIAGNOSTIC_SHORTFALL", allocations, None, shortfall)
