from typing import Literal
from langgraph.graph import StateGraph, START, END

from agents.state import GraphState, RoutingParameters, PortAllocation
from solver.routing_model import evaluate_routing_feasibility
from clients.port_sandbox import get_port_capacities
from memory import yaam_facade

def node_ingest_alert(state: GraphState) -> GraphState:
    capacities = get_port_capacities()
    return {"port_capacities": capacities}

def node_draft_artifact(state: GraphState) -> GraphState:
    # In a real LangChain setup, we would invoke the Upstream LLM here using `prompts.UPSTREAM_SYSTEM_PROMPT`
    # and use `with_structured_output(RoutingParameters)`.
    # For testing/mocking, we can generate a statically flawed draft to trigger the solver's INFEASIBLE catch.
    
    # Example Mock Implementation for tests to override:
    if not state.get("routing_parameters"):
        # Initial draft: Route everything to NLRTM, triggering a capacity infeasibility if > 6000.
        params = RoutingParameters(
            original_destination="DEHAM",
            total_teu_to_reroute=10000,
            allocations=[PortAllocation(port_code="NLRTM", teu_amount=10000)]
        )
        # YAAM Integration
        yaam_facade.artifact_save_draft(params.model_dump())
        return {"routing_parameters": params, "revisions_count": 0}
    return state

def node_run_solver(state: GraphState) -> GraphState:
    params = state["routing_parameters"]
    capacities = state["port_capacities"]
    
    result = evaluate_routing_feasibility(params, capacities)
    return {"solver_result": result}

def node_repair_artifact(state: GraphState) -> GraphState:
    # In a real setup, invoke Downstream LLM with `prompts.DOWNSTREAM_SYSTEM_PROMPT`,
    # the original `state["routing_parameters"]`, and `state["solver_result"].iis_log`.
    
    params = state["routing_parameters"]
    iis_log = state["solver_result"].iis_log
    
    # YAAM Integration: Attach Feedback
    yaam_facade.artifact_attach_feedback(artifact_id="draft_id_mock", feedback=iis_log)
    
    # Mock LLM Logic: Read IIS log and adjust. 
    # Here we mock a successful repair for tests.
    if "NLRTM" in iis_log and params:
        new_params = RoutingParameters(
            original_destination="DEHAM",
            total_teu_to_reroute=10000,
            allocations=[
                PortAllocation(port_code="NLRTM", teu_amount=6000),
                PortAllocation(port_code="BEANR", teu_amount=4000)
            ]
        )
        yaam_facade.artifact_create_revision(previous_artifact_id="draft_id_mock", new_artifact_data=new_params.model_dump())
        revisions = state.get("revisions_count", 0) + 1
        return {"routing_parameters": new_params, "revisions_count": revisions}
    
    return state

def node_commit_final(state: GraphState) -> GraphState:
    yaam_facade.artifact_commit_final(artifact_id="revision_id_mock")
    return state

def route_after_solver(state: GraphState) -> Literal["node_commit_final", "node_repair_artifact"]:
    if state["solver_result"].status == "FEASIBLE":
        return "node_commit_final"
    return "node_repair_artifact"

# Build the LangGraph
workflow = StateGraph(GraphState)

workflow.add_node("node_ingest_alert", node_ingest_alert)
workflow.add_node("node_draft_artifact", node_draft_artifact)
workflow.add_node("node_run_solver", node_run_solver)
workflow.add_node("node_repair_artifact", node_repair_artifact)
workflow.add_node("node_commit_final", node_commit_final)

workflow.add_edge(START, "node_ingest_alert")
workflow.add_edge("node_ingest_alert", "node_draft_artifact")
workflow.add_edge("node_draft_artifact", "node_run_solver")

workflow.add_conditional_edges(
    "node_run_solver",
    route_after_solver
)

workflow.add_edge("node_repair_artifact", "node_run_solver")
workflow.add_edge("node_commit_final", END)

graph = workflow.compile()
