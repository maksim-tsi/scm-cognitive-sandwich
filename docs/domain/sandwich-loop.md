# Domain Knowledge: The Sandwich Loop & OR Math 🥪

As an autonomous agent, you must understand the exact payload structures, the mathematical constraints of the Operations Research (OR) model, and the concept of an Irreducible Infeasible Subsystem (IIS). This document is your guide for building `src/solver/routing_model.py` and the LLM prompts.

## 1. The IDWL 2026 Baseline Scenario
**The Event:** A severe storm surge has closed the Port of Hamburg (`DEHAM`). 
**The Problem:** A freight forwarder has a shipment of `10,000 TEU` (Twenty-foot Equivalent Units) currently at sea, destined for Hamburg. 
**The Goal:** Reroute the `10,000 TEU` to alternative Northern European ports (`NLRTM` - Rotterdam, `BEANR` - Antwerp) at the lowest possible penalty cost, without exceeding the physical capacity of those alternative ports.

## 2. The Artifact Schema (Pydantic)
The Upstream LLM must generate, and the Downstream LLM must refine, a specific JSON payload. This is the "Artifact". You must use this strict Pydantic model in your code:

```python
from pydantic import BaseModel, Field

class PortAllocation(BaseModel):
    port_code: str = Field(..., description="UN/LOCODE of the destination port (e.g., NLRTM, BEANR)")
    teu_amount: int = Field(..., description="Amount of TEU to route to this port")

class RoutingParameters(BaseModel):
    original_destination: str = Field("DEHAM", description="The closed port")
    total_teu_to_reroute: int = Field(..., description="Total cargo volume that must be re-allocated")
    allocations: list[PortAllocation] = Field(..., description="Proposed distribution of TEU")

```

## 3. The OR Solver Math (Pyomo Formulation)

The solver (`src/solver/routing_model.py`) takes the `RoutingParameters` and the current port capacities (fetched from `maritime-port-sandbox`) to verify if the LLM's proposal is physically possible.

### Mathematical Constraints to Implement in Pyomo:

1. **Demand Satisfaction Constraint:** The sum of all `teu_amount` in the allocations MUST exactly equal `total_teu_to_reroute`.
2. **Capacity Constraint:** For every port $p$ in the allocations, the `teu_amount` MUST be $\le$ the `availableCapacityTEU` retrieved from the sandbox API for port $p$.

*Agent Note: The LLM does not know the exact numerical capacity of Rotterdam when it generates Artifact v1. It might guess and route all 10,000 TEU to Rotterdam, even if Rotterdam only has 6,000 TEU of capacity left. This is intentional. We want the solver to catch this hallucination.*

## 4. Understanding IIS (Irreducible Infeasible Subsystem)

If the LLM violates the **Capacity Constraint** (e.g., routes 10,000 TEU to NLRTM, but Sandbox API says NLRTM capacity is 6,000), the Pyomo model will be mathematically `INFEASIBLE`.

When using the SCIP solver, you must catch this infeasibility and extract the **IIS log**.
An IIS log is a minimal set of constraints that contradict each other.
Your SCIP extraction logic should return a human-readable (and LLM-readable) string like this:

```text
SOLVER FAILED: INFEASIBLE
Conflict detected in Capacity Constraint for port NLRTM.
Attempted Allocation: 10000 TEU.
Maximum Available Capacity: 6000 TEU.
Difference: -4000 TEU.

```

## 5. The Downstream LLM (Repair Loop)

When the LangGraph state machine detects an `INFEASIBLE` result from the solver, it passes the original `RoutingParameters` (Artifact v1) AND the IIS Log to the Downstream LLM.

**Downstream LLM Logic (System Prompt Directives):**

* Read the IIS log.
* Identify which port's capacity was exceeded (the port is explicitly named in the IIS log).
* Decrease the `teu_amount` for the port mentioned in the IIS log.
* Shift that TEU to another available port (do not drop TEU; reallocate it).
* Output `Artifact v2` using the exact same JSON schema.

**State History (Debugging):**
* The graph retains a cumulative `solver_error_logs: list[str]` in state, appending each IIS log from every `INFEASIBLE` solver run. This prevents overwriting prior failure context across repair iterations.

## 6. YAAM Artifact Tool Integration

* When `Artifact v1` is generated -> Call `artifact_save_draft`.
* When Solver returns IIS -> Call `artifact_attach_feedback` (Attach the IIS log string as feedback to v1).
* When Downstream LLM generates `Artifact v2` -> Call `artifact_create_revision` (Points to v1).
* When Solver returns `FEASIBLE` for v2 -> Call `artifact_commit_final` (Saves to L4).
