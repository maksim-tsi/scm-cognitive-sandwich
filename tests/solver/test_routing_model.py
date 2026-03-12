from agents.state import RoutingParameters, PortAllocation
from solver.routing_model import evaluate_routing_feasibility

def test_routing_model_feasible():
    params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[
            PortAllocation(port_code="NLRTM", teu_amount=6000),
            PortAllocation(port_code="BEANR", teu_amount=4000)
        ]
    )
    capacities = {"NLRTM": 6000, "BEANR": 8000}
    result = evaluate_routing_feasibility(params, capacities)
    assert result.status == "FEASIBLE"
    assert result.iis_log is None

def test_routing_model_infeasible_capacity():
    params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[
            PortAllocation(port_code="NLRTM", teu_amount=10000)
        ]
    )
    capacities = {"NLRTM": 6000, "BEANR": 8000}
    result = evaluate_routing_feasibility(params, capacities)
    assert result.status == "INFEASIBLE"
    assert "Conflict detected in Capacity Constraint for port NLRTM" in result.iis_log
    assert "Difference: -4000 TEU" in result.iis_log

def test_routing_model_infeasible_demand():
    params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[
            PortAllocation(port_code="NLRTM", teu_amount=5000)
        ]
    )
    capacities = {"NLRTM": 6000, "BEANR": 8000}
    result = evaluate_routing_feasibility(params, capacities)
    assert result.status == "INFEASIBLE"
    assert "Conflict detected in Demand Satisfaction Constraint" in result.iis_log
    assert "Difference: 5000 TEU" in result.iis_log
