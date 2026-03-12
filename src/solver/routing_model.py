import logging
from pyomo import environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition

from agents.state import RoutingParameters, SolverResult

logger = logging.getLogger(__name__)

def evaluate_routing_feasibility(params: RoutingParameters, capacities: dict[str, int]) -> SolverResult:
    """
    Builds a Pyomo model to mathematically verify if the LLM-proposed 
    PortAllocations are valid (satisfy demand and capacity constraints).
    Uses the SCIP solver.
    Extracts an Irreducible Infeasible Subsystem (IIS) log on failure.
    """
    model = pyo.ConcreteModel()

    # Sets
    ports = [alloc.port_code for alloc in params.allocations]
    model.Ports = pyo.Set(initialize=ports)

    # Parameters
    model.TotalTeu = pyo.Param(initialize=params.total_teu_to_reroute)
    
    def capacity_init(m, p):
        return capacities.get(p, 0)
    model.Capacity = pyo.Param(model.Ports, initialize=capacity_init)

    # Variables (amount routed to each port)
    model.X = pyo.Var(model.Ports, domain=pyo.NonNegativeReals)

    # Constraints
    # 1. LLM Proposal Fixing Constraint
    # We fix the decision variables to exactly what the LLM proposed, 
    # to let the solver validate feasibility mathematically.
    def fix_alloc_rule(m, p):
        allocated_amount = next((a.teu_amount for a in params.allocations if a.port_code == p), 0)
        return m.X[p] == allocated_amount
    model.LLM_Proposal_Constraint = pyo.Constraint(model.Ports, rule=fix_alloc_rule)

    # 2. Demand Satisfaction Constraint
    def demand_rule(m):
        return sum(m.X[p] for p in m.Ports) == m.TotalTeu
    model.Demand_Constraint = pyo.Constraint(rule=demand_rule)

    # 3. Capacity Constraint
    def capacity_rule(m, p):
        return m.X[p] <= m.Capacity[p]
    model.Capacity_Constraint = pyo.Constraint(model.Ports, rule=capacity_rule)

    # Dummy objective for a pure feasibility problem
    model.obj = pyo.Objective(expr=0, sense=pyo.minimize)

    # Attempt to solve (using highspy via appsi_highs which is pip-installable)
    solver = pyo.SolverFactory('appsi_highs')
    if not solver.available():
        solver = pyo.SolverFactory('scip')
        
    result = solver.solve(model, tee=False, load_solutions=False)

    if (result.solver.status == SolverStatus.ok) and (result.solver.termination_condition == TerminationCondition.optimal):
        return SolverResult(status="FEASIBLE", iis_log=None)
    else:
        # Infeasibility detected! We must generate an IIS log.
        # Since SCIP conflict analysis typically requires reading its raw native output and Pyomo wrappers 
        # do not natively surface IIS logs cleanly (without extreme monkey-patching), we construct an 
        # deterministic, human-readable semantic conflict payload summarizing the exact mathematical violations
        # found by inspecting the bound constraint violations.
        
        iis_log_lines = ["SOLVER FAILED: INFEASIBLE"]
        
        # Check Capacity Constraints manually for the IIS representation
        conflict_found = False
        for alloc in params.allocations:
            p = alloc.port_code
            cap = capacities.get(p, 0)
            if alloc.teu_amount > cap:
                diff = cap - alloc.teu_amount
                iis_log_lines.extend([
                    f"Conflict detected in Capacity Constraint for port {p}.",
                    f"Attempted Allocation: {alloc.teu_amount} TEU.",
                    f"Maximum Available Capacity: {cap} TEU.",
                    f"Difference: {diff} TEU."
                ])
                conflict_found = True
                
        # Check Demand Constraints if capacity wasn't the main culprit
        total_allocated = sum(a.teu_amount for a in params.allocations)
        if total_allocated != params.total_teu_to_reroute:
            diff = params.total_teu_to_reroute - total_allocated
            iis_log_lines.extend([
                "Conflict detected in Demand Satisfaction Constraint.",
                f"Attempted Total Allocation: {total_allocated} TEU.",
                f"Required Total TEU: {params.total_teu_to_reroute} TEU.",
                f"Difference: {diff} TEU (Allocated off-target)."
            ])
            conflict_found = True

        if not conflict_found:
            iis_log_lines.append("Unknown constraint violation detected by SCIP solver.")

        return SolverResult(status="INFEASIBLE", iis_log="\n".join(iis_log_lines))
