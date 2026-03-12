import os
from typing import Literal
from langgraph.graph import StateGraph, START, END

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from agents.state import GraphState, RoutingParameters
from agents.prompts import UPSTREAM_SYSTEM_PROMPT, DOWNSTREAM_SYSTEM_PROMPT
from solver.routing_model import evaluate_routing_feasibility
from clients.port_sandbox import get_port_capacities
from memory import yaam_facade

def _get_llm():
    # Use Gemini by default as specified by user
    if os.environ.get("GOOGLE_API_KEY"):
        return ChatGoogleGenerativeAI(model="gemini-3.1-flash", temperature=0)
    elif os.environ.get("GROQ_API_KEY"):
        # fallback to Groq
        return ChatGroq(model="llama3-8b-8192", temperature=0)
    else:
        raise ValueError("No active API keys found for Google or Groq in environment.")

def node_ingest_alert(state: GraphState) -> GraphState:
    capacities = get_port_capacities()
    return {"port_capacities": capacities}

def node_draft_artifact(state: GraphState) -> GraphState:
    if not state.get("routing_parameters"):
        llm = _get_llm().with_structured_output(RoutingParameters)
        
        system_msg = SystemMessage(content=UPSTREAM_SYSTEM_PROMPT)
        human_content = (
            f"Alert Text:\n{state.get('alert_text', 'N/A')}\n\n"
            f"Port Capacities:\n{state.get('port_capacities', {})}\n"
        )
        human_msg = HumanMessage(content=human_content)
        
        params = llm.invoke([system_msg, human_msg])
        
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
    params = state["routing_parameters"]
    iis_log = state["solver_result"].iis_log
    
    # YAAM Integration: Attach Feedback
    yaam_facade.artifact_attach_feedback(artifact_id="draft_id_mock", feedback=iis_log)
    
    llm = _get_llm().with_structured_output(RoutingParameters)
    
    system_msg = SystemMessage(content=DOWNSTREAM_SYSTEM_PROMPT)
    human_content = (
        f"Original Routing Parameters:\n{params.model_dump_json(indent=2)}\n\n"
        f"IIS Log (Solver Feedback):\n{iis_log}\n\n"
        f"Port Capacities:\n{state.get('port_capacities', {})}\n"
    )
    human_msg = HumanMessage(content=human_content)
    
    new_params = llm.invoke([system_msg, human_msg])
    
    yaam_facade.artifact_create_revision(previous_artifact_id="draft_id_mock", new_artifact_data=new_params.model_dump())
    revisions = state.get("revisions_count", 0) + 1
    
    return {"routing_parameters": new_params, "revisions_count": revisions}

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
