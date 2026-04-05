
from pydantic import BaseModel, Field


class CandidateScenario(BaseModel):
    scenario_id: str = Field(..., description="Unique identifier for the proposed scenario")
    target_ports: list[str] = Field(
        default_factory=list, description="Ordered list of ports to visit"
    )
    # This input schema can be expanded further with vessels, arrival windows, etc.


class SimulationExecutionRequest(BaseModel):
    run_id: str = Field(
        ..., description="Unique ID for the simulation run, provided by the Orchestrator"
    )
    scenarios: list[CandidateScenario] = Field(
        ..., min_length=1, description="List of proposed routing scenarios to evaluate"
    )


class ScenarioMetrics(BaseModel):
    # Axis 1: Time and SLA (Minimization)
    total_lead_time_hours: float = Field(..., description="Total transit and processing time")
    average_queue_time_hours: float = Field(
        ..., description="Average vessel waiting time in queue"
    )
    sla_breach_probability: float = Field(
        ..., description="Probability of contract violation (0.0 - 1.0)"
    )

    # Axis 2: Financial Cost (Minimization)
    total_cost_usd: float = Field(..., description="Total logistic costs")
    penalty_cost_usd: float = Field(
        ..., description="Penalties accrued for delays or SLA breaches"
    )

    # Axis 3: Risk and Utilization (Minimization)
    max_yard_utilization_pct: float = Field(..., description="Peak terminal yard utilization (%)")
    bottleneck_severity: float = Field(..., description="Bottleneck severity index (0.0 - 1.0)")


class SimulationEvent(BaseModel):
    timestamp: float
    event_type: str  # e.g., "VESSEL_ARRIVED", "CRANE_FAILED", "QUEUE_OVERFLOW"
    details: str


class ScenarioExecutionResult(BaseModel):
    scenario_id: str = Field(..., description="Identifier matching the Orchestrator's candidate ID")
    execution_status: str = Field(
        ..., description="Allowed: 'SUCCESS', 'INFEASIBLE_DURING_SIMULATION', 'ERROR'"
    )
    metrics: ScenarioMetrics | None = Field(
        None, description="Populated only if execution_status is SUCCESS"
    )
    critical_events: list[SimulationEvent] = Field(
        ..., description="Timeline of events for explainability"
    )
    failure_reason: str | None = Field(
        None, description="Solver/DES logs if the scenario failed dynamically"
    )


class SandboxExecutionOutput(BaseModel):
    run_id: str
    simulated_scenarios: list[ScenarioExecutionResult]
