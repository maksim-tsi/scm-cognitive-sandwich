from __future__ import annotations

from typing import Any, TypeVar

import pytest

from agents.variant_b.graph import get_variant_b_graph
from agents.variant_b.state import (
    CandidateScenario,
    CandidateScenarioSet,
    IncidentTrigger,
    JudgeSemanticVerdict,
    VariantBState,
)

T = TypeVar("T")


class _FakeLLM:
    def __init__(self, *, default_output: Any, outputs_by_model: dict[type[Any], Any] | None = None):
        self._default_output = default_output
        self._outputs_by_model = outputs_by_model or {}
        self._structured: type[Any] | None = None

    def bind_tools(self, tools: list[Any]) -> "_FakeLLM":  # noqa: ARG002
        return self

    def with_structured_output(self, model: type[T]) -> "_FakeLLM":
        self._structured = model
        return self

    def invoke(self, messages: list[Any]) -> Any:  # noqa: ARG002
        if self._structured is None:
            return self._default_output
        output = self._outputs_by_model.get(self._structured, self._default_output)
        if isinstance(output, self._structured):
            return output
        return self._structured.model_validate(output)


def _initial_state(incident: IncidentTrigger) -> VariantBState:
    return {
        "incident": incident,
        "run_id": incident.incident_id,
        "retry_count": 0,
        "incident_context": {},
        "scenarios": [],
        "judge_verdict": None,
        "judge_feedback": [],
        "judge_findings": [],
        "tool_ledger": [],
        "sandbox_results": [],
        "final_report_md": None,
        "fatal_status": None,
        "agent_id": "scm-sandwich-variantb-test",
    }


def test_variant_b_accept_path_runs_to_synthesize(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    incident = IncidentTrigger(
        incident_id="inc-1",
        affected_nodes=["DEHAM"],
        cargo_demand=10000,
        raw_alert_text="Port closure alert",
    )

    generator_payload = CandidateScenarioSet(
        scenarios=[
            CandidateScenario(
                title="Balanced split",
                rationale="Split demand across two ports.",
                allocations=[{"port_code": "NLRTM", "teu_amount": 5000}, {"port_code": "BEANR", "teu_amount": 5000}],
                tool_calls=[],
            ),
            CandidateScenario(
                title="Cost focus",
                rationale="Prefer cheaper port mix.",
                allocations=[{"port_code": "NLRTM", "teu_amount": 6000}, {"port_code": "BEANR", "teu_amount": 4000}],
                tool_calls=[],
            ),
            CandidateScenario(
                title="Risk focus",
                rationale="Prefer operational resilience.",
                allocations=[{"port_code": "NLRTM", "teu_amount": 4000}, {"port_code": "BEANR", "teu_amount": 6000}],
                tool_calls=[],
            ),
        ]
    ).model_dump()

    judge_payload = JudgeSemanticVerdict(status="ACCEPT", violations=[], feedback="").model_dump()

    def _fake_openrouter_chat(*args: Any, **kwargs: Any) -> _FakeLLM:  # noqa: ARG001
        return _FakeLLM(
            default_output={},
            outputs_by_model={
                CandidateScenarioSet: generator_payload,
                JudgeSemanticVerdict: judge_payload,
            },
        )

    # Patch generator and judge separately by intercepting in module under test.
    import agents.variant_b.graph as graph_mod  # noqa: WPS433

    monkeypatch.setattr(graph_mod, "get_openrouter_chat", _fake_openrouter_chat)
    monkeypatch.setattr(graph_mod, "build_langchain_tools", lambda: [])
    monkeypatch.setattr(graph_mod, "resolve_tool_specs_by_name", lambda: {})
    monkeypatch.setattr(graph_mod, "_pass1_deterministic_checks", lambda s: (True, [], []))

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

    incident = IncidentTrigger(
        incident_id="inc-2",
        affected_nodes=["DEHAM"],
        cargo_demand=10000,
        raw_alert_text="Port closure alert",
    )

    flawed_payload = {
        "scenarios": [
            {
                "title": "Flawed",
                "rationale": "Intentionally wrong mass balance.",
                "allocations": [{"port_code": "NLRTM", "teu_amount": 1}],
                "tool_calls": [],
                "claimed_metrics": {},
                "claimed_metrics_evidence": {},
            },
            {
                "title": "Flawed2",
                "rationale": "Also wrong.",
                "allocations": [{"port_code": "BEANR", "teu_amount": 1}],
                "tool_calls": [],
                "claimed_metrics": {},
                "claimed_metrics_evidence": {},
            },
            {
                "title": "Flawed3",
                "rationale": "Also wrong.",
                "allocations": [{"port_code": "DEBRV", "teu_amount": 1}],
                "tool_calls": [],
                "claimed_metrics": {},
                "claimed_metrics_evidence": {},
            },
        ]
    }

    def _fake_openrouter_chat(*args: Any, **kwargs: Any) -> _FakeLLM:  # noqa: ARG001
        return _FakeLLM(
            default_output={},
            outputs_by_model={
                CandidateScenarioSet: flawed_payload,
            },
        )

    import agents.variant_b.graph as graph_mod  # noqa: WPS433

    monkeypatch.setattr(graph_mod, "get_openrouter_chat", _fake_openrouter_chat)
    monkeypatch.setattr(graph_mod, "build_langchain_tools", lambda: [])
    monkeypatch.setattr(graph_mod, "resolve_tool_specs_by_name", lambda: {})

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


@pytest.mark.skip(reason="Variant B graph now requires real OpenRouter in production runs; unit tests patch it.")
def test_placeholder() -> None:
    assert True
