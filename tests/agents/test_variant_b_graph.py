from agents.variant_b.graph import get_variant_b_graph
from agents.variant_b.state import IncidentTrigger, VariantBState


def _initial_state(incident: IncidentTrigger) -> VariantBState:
    return {
        "incident": incident,
        "run_id": incident.incident_id,
        "retry_count": 0,
        "incident_context": {},
        "scenarios": [],
        "judge_verdict": None,
        "judge_feedback": [],
        "sandbox_results": [],
        "final_report_md": None,
        "fatal_status": None,
        "agent_id": "scm-sandwich-variantb-test",
    }


def test_variant_b_accept_path_runs_to_synthesize(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("VARIANT_B_FORCE_REJECT", raising=False)

    incident = IncidentTrigger(
        incident_id="inc-1",
        affected_nodes=["DEHAM"],
        cargo_demand=10000,
        raw_alert_text="Port closure alert",
    )

    graph = get_variant_b_graph()
    final_state = graph.invoke(
        _initial_state(incident),
        config={"recursion_limit": 50, "configurable": {"thread_id": "test-variantb-accept"}},
    )

    assert final_state["fatal_status"] is None
    assert final_state["judge_verdict"] == "ACCEPT"
    assert isinstance(final_state["final_report_md"], str)
    assert "Variant B Report (Stub)" in final_state["final_report_md"]


def test_variant_b_reject_path_triggers_fatal_circuit_breaker(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("VARIANT_B_FORCE_REJECT", "true")

    incident = IncidentTrigger(
        incident_id="inc-2",
        affected_nodes=["DEHAM"],
        cargo_demand=10000,
        raw_alert_text="Port closure alert",
    )

    graph = get_variant_b_graph()
    final_state = graph.invoke(
        _initial_state(incident),
        config={"recursion_limit": 50, "configurable": {"thread_id": "test-variantb-reject"}},
    )

    assert final_state["fatal_status"] == "FATAL_VALIDATION_ERROR"
    assert final_state["retry_count"] == 3
    assert final_state["judge_verdict"] == "REJECT"
    assert isinstance(final_state["judge_feedback"], list)
    assert len(final_state["judge_feedback"]) == 3
    assert final_state["sandbox_results"] == []
    assert final_state["final_report_md"] is None

