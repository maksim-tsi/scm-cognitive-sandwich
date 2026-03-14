from unittest.mock import patch, MagicMock
from agents.graph import graph
from agents.state import RoutingParameters, PortAllocation

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
