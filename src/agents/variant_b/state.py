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


class ScenarioPortAllocation(BaseModel):
    model_config = ConfigDict(strict=True)

    port_code: str = Field(..., description="UN/LOCODE of the destination port (e.g., NLRTM, BEANR).")
    teu_amount: int = Field(..., ge=0, description="Amount of TEU allocated to this port.")


class ToolCallSpec(BaseModel):
    model_config = ConfigDict(strict=True)

    tool_name: str = Field(..., description="Stable tool alias from tools.__all__ (e.g. ocean_freight_costing__...).")
    args: dict[str, Any] = Field(default_factory=dict, description="Keyword args for the tool's Pydantic input schema.")


class CandidateScenario(BaseModel):
    """Strict scenario contract produced by the generator LLM (Exec Plan 2)."""

    model_config = ConfigDict(strict=True)

    title: str = Field(..., description="Short scenario name.")
    rationale: str = Field(..., description="1-3 sentences explaining why this is distinct.")
    allocations: list[ScenarioPortAllocation] = Field(..., min_length=1)
    tool_calls: list[ToolCallSpec] = Field(default_factory=list, description="Deterministic tool executions required.")

    # Any numeric claims must be backed by the tool ledger (RFC-003).
    claimed_metrics: dict[str, float] = Field(default_factory=dict, description="Numeric claims (e.g., time/cost/risk).")
    claimed_metrics_evidence: dict[str, str] = Field(
        default_factory=dict,
        description="metric_key -> tool_ledger_entry_id (must exist if metric is present).",
    )


class CandidateScenarioSet(BaseModel):
    model_config = ConfigDict(strict=True)

    scenarios: list[CandidateScenario] = Field(..., min_length=3, max_length=3)


class ToolLedgerEntry(BaseModel):
    model_config = ConfigDict(strict=True)

    entry_id: str = Field(..., description="Stable identifier for cross-referencing evidence.")
    tool_name: str = Field(..., description="Curated tool alias executed.")
    args: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error: str | None = None
    status: str = Field(..., description="SUCCESS or ERROR")


class JudgeSemanticVerdict(BaseModel):
    model_config = ConfigDict(strict=True)

    status: str = Field(..., description="ACCEPT or REJECT")
    violations: list[str] = Field(default_factory=list, description="Short rule violations.")
    feedback: str = Field(..., description="Actionable feedback to fix issues on retry.")


class VariantBState(TypedDict):
    incident: IncidentTrigger
    run_id: str
    retry_count: int

    incident_context: dict[str, Any]
    scenarios: list[dict[str, Any]]
    judge_verdict: str | None
    judge_feedback: Annotated[list[str], operator.add]
    judge_findings: Annotated[list[str], operator.add]

    tool_ledger: Annotated[list[dict[str, Any]], operator.add]

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
    judge_findings: Annotated[list[str], operator.add]

    tool_ledger: Annotated[list[dict[str, Any]], operator.add]

    sandbox_results: list[dict[str, Any]]
    final_report_md: str | None
    fatal_status: str | None

    agent_id: str
