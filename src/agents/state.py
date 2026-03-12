import operator
from typing import Annotated, TypedDict
from pydantic import BaseModel, Field

class PortAllocation(BaseModel):
    port_code: str = Field(..., description="UN/LOCODE of the destination port (e.g., NLRTM, BEANR)")
    teu_amount: int = Field(..., description="Amount of TEU to route to this port")

class RoutingParameters(BaseModel):
    original_destination: str = Field("DEHAM", description="The closed port")
    total_teu_to_reroute: int = Field(..., description="Total cargo volume that must be re-allocated")
    allocations: list[PortAllocation] = Field(..., description="Proposed distribution of TEU")

class SolverResult(BaseModel):
    status: str = Field(..., description="FEASIBLE or INFEASIBLE")
    iis_log: str | None = Field(None, description="Irreducible Infeasible Subsystem log if status is INFEASIBLE")

class GraphState(TypedDict):
    alert_text: str
    port_capacities: dict[str, int]
    routing_parameters: RoutingParameters | None
    solver_result: SolverResult | None
    solver_error_logs: Annotated[list[str], operator.add]
    revisions_count: int


class GraphStateUpdate(TypedDict, total=False):
    alert_text: str
    port_capacities: dict[str, int]
    routing_parameters: RoutingParameters | None
    solver_result: SolverResult | None
    solver_error_logs: Annotated[list[str], operator.add]
    revisions_count: int
