import asyncio
from unittest.mock import patch, MagicMock
from agents.graph import (
    _build_final_state,
    _build_metadata,
    _run_async_from_sync,
    graph,
    node_repair_artifact,
    node_run_solver,
    route_after_solver,
)
from agents.state import PortAllocation, RoutingParameters, SolverResult


UNKNOWN_PORT_ERROR = (
    "SOLVER ERROR: Port FRLEH is not recognized in the current network topology. "
    "Allowed ports are: NLRTM, BEANR, DEHAM, DEBRV."
)

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
        "revisions_count": 0,
        "agent_id": "scm-sandwich-experiment-v1",
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
    mock_consolidate_episode.assert_called_once()
    _, call_kwargs = mock_consolidate_episode.call_args
    assert call_kwargs["state"]["agent_id"] == "scm-sandwich-experiment-v1"


def test_node_run_solver_records_unknown_port_error_for_repair_feedback():
    params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[PortAllocation(port_code="FRLEH", teu_amount=10000)],
    )
    state = {
        "alert_text": "Port closure alert",
        "port_capacities": {"NLRTM": 6000, "BEANR": 8000, "DEHAM": 9000, "DEBRV": 7000},
        "routing_parameters": params,
        "solver_result": None,
        "solver_error_logs": [],
        "revisions_count": 0,
    }

    update = node_run_solver(state)

    assert update["solver_result"].status == "INFEASIBLE"
    assert update["solver_result"].iis_log == UNKNOWN_PORT_ERROR
    assert update["solver_error_logs"] == [UNKNOWN_PORT_ERROR]


def test_route_after_solver_commits_terminal_infeasible_result():
    state = {
        "alert_text": "a",
        "port_capacities": {},
        "routing_parameters": None,
        "solver_result": SolverResult(
            status="INFEASIBLE",
            iis_log=(
                "SOLVER TERMINAL: MATHEMATICALLY INFEASIBLE. Total required TEU is 20000, "
                "but combined available capacity across allowed ports is 10000 TEU (deficit: 10000 TEU). "
                "Allowed ports are: NLRTM, BEANR, DEHAM, DEBRV."
            ),
        ),
        "solver_error_logs": [],
        "revisions_count": 0,
    }

    next_node = route_after_solver(state)

    assert next_node == "node_commit_final"


@patch("agents.graph.yaam_facade.artifact_create_revision")
@patch("agents.graph.yaam_facade.artifact_attach_feedback")
@patch("agents.graph._get_llm")
def test_node_repair_artifact_strips_zero_capacity_allocations_and_injects_capacity_context(
    mock_get_llm,
    _mock_attach_feedback,
    _mock_create_revision,
):
    repaired = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[
            PortAllocation(port_code="NLRTM", teu_amount=4000),
            PortAllocation(port_code="BEANR", teu_amount=2000),
            PortAllocation(port_code="DEHAM", teu_amount=3000),
            PortAllocation(port_code="DEBRV", teu_amount=1000),
        ],
    )

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = repaired
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_get_llm.return_value = mock_llm

    state = {
        "alert_text": "Port closure alert",
        "port_capacities": {"NLRTM": 6000, "BEANR": 0, "DEHAM": 5000, "DEBRV": 0},
        "routing_parameters": RoutingParameters(
            original_destination="DEHAM",
            total_teu_to_reroute=10000,
            allocations=[PortAllocation(port_code="NLRTM", teu_amount=10000)],
        ),
        "solver_result": SolverResult(
            status="INFEASIBLE",
            iis_log="Conflict detected in Capacity Constraint for port NLRTM.",
        ),
        "solver_error_logs": ["Conflict detected in Capacity Constraint for port NLRTM."],
        "revisions_count": 0,
    }

    update = node_repair_artifact(state)

    sanitized_allocations = {
        alloc.port_code: alloc.teu_amount
        for alloc in update["routing_parameters"].allocations
    }
    assert sanitized_allocations == {"NLRTM": 4000, "DEHAM": 3000}
    assert update["revisions_count"] == 1

    invoke_messages = mock_chain.invoke.call_args.args[0]
    system_content = invoke_messages[0].content
    human_content = invoke_messages[1].content

    assert "Do NOT allocate ANY TEUs to ports with 0 capacity" in system_content
    assert "Allowed ports: NLRTM, BEANR, DEHAM, DEBRV" in human_content
    assert "Zero-capacity ports: BEANR, DEBRV" in human_content


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
