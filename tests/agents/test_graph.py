from agents.graph import graph

def test_graph_execution():
    # Test that graph executes from start to end without infinite looping
    # In our mocked setup, node_draft_artifact routes to NLRTM=10000, which causes infeasible,
    # then node_repair_artifact fixes it to NLRTM=6000 and BEANR=4000 which is feasible,
    # then routes to end.
    
    initial_state = {
        "alert_text": "Storm hit Hamburg, reroute cargo",
        "port_capacities": {},
        "routing_parameters": None,
        "solver_result": None,
        "revisions_count": 0
    }
    
    result_state = graph.invoke(initial_state)
    
    assert result_state["solver_result"].status == "FEASIBLE"
    assert result_state["revisions_count"] == 1
    assert result_state["routing_parameters"].allocations[0].teu_amount == 6000
    assert result_state["routing_parameters"].allocations[1].teu_amount == 4000
