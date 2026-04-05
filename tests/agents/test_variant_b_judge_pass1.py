from __future__ import annotations

from agents.variant_b.graph import node_judge_validation
from agents.variant_b.state import IncidentTrigger, VariantBState


def _state_with_scenarios(*, incident: IncidentTrigger, scenarios: list[dict]) -> VariantBState:
    return {
        "incident": incident,
        "run_id": incident.incident_id,
        "retry_count": 0,
        "incident_context": {"forbidden_ports": ["DEHAM"], "port_capacities": {"NLRTM": 10000, "BEANR": 10000}},
        "scenarios": scenarios,
        "judge_verdict": None,
        "judge_feedback": [],
        "judge_findings": [],
        "tool_ledger": [],
        "sandbox_results": [],
        "final_report_md": None,
        "fatal_status": None,
        "agent_id": "scm-sandwich-variantb-test",
    }


def test_judge_pass1_rejects_mass_balance_violation() -> None:
    incident = IncidentTrigger(
        incident_id="inc-mass",
        affected_nodes=["DEHAM"],
        cargo_demand=100,
        raw_alert_text="demo",
    )

    update = node_judge_validation(
        _state_with_scenarios(
            incident=incident,
            scenarios=[
                {
                    "scenario_id": "inc-mass-S1",
                    "revision": 0,
                    "title": "bad",
                    "rationale": "bad",
                    "allocations": [{"port_code": "NLRTM", "teu_amount": 1}],
                    "tool_calls": [],
                    "claimed_metrics": {},
                    "claimed_metrics_evidence": {},
                },
                {
                    "scenario_id": "inc-mass-S2",
                    "revision": 0,
                    "title": "bad2",
                    "rationale": "bad2",
                    "allocations": [{"port_code": "BEANR", "teu_amount": 1}],
                    "tool_calls": [],
                    "claimed_metrics": {},
                    "claimed_metrics_evidence": {},
                },
                {
                    "scenario_id": "inc-mass-S3",
                    "revision": 0,
                    "title": "bad3",
                    "rationale": "bad3",
                    "allocations": [{"port_code": "BEANR", "teu_amount": 1}],
                    "tool_calls": [],
                    "claimed_metrics": {},
                    "claimed_metrics_evidence": {},
                },
            ],
        )
    )

    assert update["judge_verdict"] == "REJECT"
    assert update["retry_count"] == 1
    assert update.get("fatal_status") is None
    assert update["judge_feedback"]
    assert any("MASS_BALANCE" in f for f in update.get("judge_findings", []))


def test_judge_pass1_rejects_epistemic_claim_without_ledger() -> None:
    incident = IncidentTrigger(
        incident_id="inc-epi",
        affected_nodes=["DEHAM"],
        cargo_demand=10,
        raw_alert_text="demo",
    )

    update = node_judge_validation(
        _state_with_scenarios(
            incident=incident,
            scenarios=[
                {
                    "scenario_id": "inc-epi-S1",
                    "revision": 0,
                    "title": "ok-mass",
                    "rationale": "ok-mass",
                    "allocations": [{"port_code": "NLRTM", "teu_amount": 10}],
                    "tool_calls": [],
                    "claimed_metrics": {"cost": 123.0},
                    "claimed_metrics_evidence": {},
                },
                {
                    "scenario_id": "inc-epi-S2",
                    "revision": 0,
                    "title": "ok-mass2",
                    "rationale": "ok-mass2",
                    "allocations": [{"port_code": "BEANR", "teu_amount": 10}],
                    "tool_calls": [],
                    "claimed_metrics": {},
                    "claimed_metrics_evidence": {},
                },
                {
                    "scenario_id": "inc-epi-S3",
                    "revision": 0,
                    "title": "ok-mass3",
                    "rationale": "ok-mass3",
                    "allocations": [{"port_code": "BEANR", "teu_amount": 10}],
                    "tool_calls": [],
                    "claimed_metrics": {},
                    "claimed_metrics_evidence": {},
                },
            ],
        )
    )

    assert update["judge_verdict"] == "REJECT"
    assert update["retry_count"] == 1
    assert any("EPISTEMIC" in f for f in update.get("judge_findings", []))

