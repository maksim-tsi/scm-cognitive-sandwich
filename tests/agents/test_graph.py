import asyncio
from unittest.mock import patch, MagicMock
from agents.graph import _build_final_state, _build_metadata, _run_async_from_sync, graph
from agents.state import PortAllocation, RoutingParameters, SolverResult

@patch('agents.graph.get_port_capacities')
@patch('agents.graph._get_llm')
@patch('agents.graph._consolidate_episode')
def test_graph_execution(mock_consolidate_episode, mock_get_llm, mock_get_capacities):
    mock_get_capacities.return_value = {"NLRTM": 6000, "BEANR": 8000}
    mock_consolidate_episode.return_value = True

    mock_llm = MagicMock()
    mock_chain = MagicMock()
    
    infeasible_params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[PortAllocation(port_code="NLRTM", teu_amount=10000)]
    )
    feasible_params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[
            PortAllocation(port_code="NLRTM", teu_amount=6000),
            PortAllocation(port_code="BEANR", teu_amount=4000)
        ]
    )
    
    mock_chain.invoke.side_effect = [infeasible_params, feasible_params]
    mock_llm.with_structured_output.return_value = mock_chain
    mock_get_llm.return_value = mock_llm

    initial_state = {
        "alert_text": "Storm hit Hamburg, reroute cargo",
        "port_capacities": {},
        "routing_parameters": None,
        "solver_result": None,
        "solver_error_logs": [],
        "revisions_count": 0
    }
    
    result_state = graph.invoke(
        initial_state,
        config={"recursion_limit": 10, "configurable": {"thread_id": "test-session"}},
    )
    
    assert result_state["solver_result"].status == "FEASIBLE"
    assert result_state["revisions_count"] == 1
    assert len(result_state["solver_error_logs"]) == 1
    assert "Conflict detected" in result_state["solver_error_logs"][0]
    assert result_state["routing_parameters"].allocations[0].teu_amount == 6000
    assert result_state["routing_parameters"].allocations[1].teu_amount == 4000


def test_build_final_state_maps_graph_fields_to_yaam_contract():
    params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[PortAllocation(port_code="NLRTM", teu_amount=6000)],
    )
    state = {
        "alert_text": "Port closure alert",
        "port_capacities": {"NLRTM": 6000},
        "routing_parameters": params,
        "solver_result": SolverResult(status="FEASIBLE", iis_log=None),
        "solver_error_logs": ["log-1"],
        "revisions_count": 2,
    }

    final_state = _build_final_state(state)

    assert final_state["prompt"] == "Port closure alert"
    assert final_state["solver_iis_logs"] == ["log-1"]
    assert isinstance(final_state["drafts"], list)
    assert final_state["drafts"][0]["revision"] == 2
    assert final_state["final_routing_parameters"] == params.model_dump()


def test_build_metadata_derives_allowed_status_and_attempts():
    success_state = {
        "alert_text": "a",
        "port_capacities": {},
        "routing_parameters": None,
        "solver_result": SolverResult(status="FEASIBLE", iis_log=None),
        "solver_error_logs": [],
        "revisions_count": 0,
    }
    infeasible_state = {
        "alert_text": "a",
        "port_capacities": {},
        "routing_parameters": None,
        "solver_result": SolverResult(status="INFEASIBLE", iis_log="x"),
        "solver_error_logs": ["x"],
        "revisions_count": 1,
    }
    timeout_state = {
        "alert_text": "a",
        "port_capacities": {},
        "routing_parameters": None,
        "solver_result": SolverResult(status="TIMEOUT", iis_log=None),
        "solver_error_logs": [],
        "revisions_count": 3,
    }

    success_metadata = _build_metadata(success_state)
    infeasible_metadata = _build_metadata(infeasible_state)
    timeout_metadata = _build_metadata(timeout_state)

    assert success_metadata == {
        "status": "success",
        "duration_seconds": 0.0,
        "solver_attempts": 1,
    }
    assert infeasible_metadata["status"] == "infeasible"
    assert infeasible_metadata["solver_attempts"] == 2
    assert timeout_metadata["status"] == "timeout"
    assert timeout_metadata["solver_attempts"] == 4


@patch("agents.graph.otel_context")
def test_run_async_from_sync_propagates_otel_context(mock_otel_context):
    sentinel_context = object()
    sentinel_token = object()
    mock_otel_context.get_current.return_value = sentinel_context
    mock_otel_context.attach.return_value = sentinel_token

    async def _returns_true() -> bool:
        return True

    async def _runner() -> bool:
        return _run_async_from_sync(_returns_true())

    result = asyncio.run(_runner())

    assert result is True
    mock_otel_context.attach.assert_called_once_with(sentinel_context)
    mock_otel_context.detach.assert_called_once_with(sentinel_token)
