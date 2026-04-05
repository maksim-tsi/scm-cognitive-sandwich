from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class IncidentTrigger(BaseModel):
    """Variant B pipeline entry contract.

    Note: `cargo_demand` is expressed as total TEU for the incident in the baseline Variant B scope.
    """

    model_config = ConfigDict(strict=True)

    incident_id: str = Field(..., description="Unique incident identifier for traceability/run grouping.")
    affected_nodes: list[str] = Field(
        default_factory=list,
        description="Logical/physical nodes affected by the incident (ports, terminals, network nodes).",
    )
    cargo_demand: int = Field(..., ge=0, description="Total TEU demand impacted by the incident.")
    raw_alert_text: str = Field(..., description="Original alert text that triggered the run.")


class VariantBState(TypedDict):
    incident: IncidentTrigger
    run_id: str
    retry_count: int

    incident_context: dict[str, Any]
    scenarios: list[dict[str, Any]]
    judge_verdict: str | None
    judge_feedback: Annotated[list[str], operator.add]

    sandbox_results: list[dict[str, Any]]
    final_report_md: str | None
    fatal_status: str | None

    agent_id: NotRequired[str]


class VariantBStateUpdate(TypedDict, total=False):
    incident: IncidentTrigger
    run_id: str
    retry_count: int

    incident_context: dict[str, Any]
    scenarios: list[dict[str, Any]]
    judge_verdict: str | None
    judge_feedback: Annotated[list[str], operator.add]

    sandbox_results: list[dict[str, Any]]
    final_report_md: str | None
    fatal_status: str | None

    agent_id: str

