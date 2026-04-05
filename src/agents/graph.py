import asyncio
import logging
import os
import threading
from collections.abc import Coroutine
from typing import Any
from typing import Literal
from langgraph.graph import END, START, StateGraph  # type: ignore[attr-defined]
from opentelemetry import context as otel_context

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from agents.state import GraphState, GraphStateUpdate, PortAllocation, RoutingParameters
from agents.prompts import UPSTREAM_SYSTEM_PROMPT, DOWNSTREAM_SYSTEM_PROMPT
from solver.routing_model import ALLOWED_PORTS, evaluate_routing_feasibility, is_terminal_infeasible_log
from clients.port_sandbox import get_port_capacities
from memory.checkpointer import create_checkpointer
from memory.yaam_client import DEFAULT_AGENT_ID, YAAMClient
from memory import yaam_facade

from langchain_mistralai import ChatMistralAI

LOGGER = logging.getLogger(__name__)

DEFAULT_THREAD_ID = "sandwich-local-thread"


def _run_async_from_sync(coro: Coroutine[Any, Any, bool]) -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # If we are already inside an event loop, run the coroutine in a dedicated
    # thread to avoid RuntimeError("asyncio.run() cannot be called...").
    result: dict[str, bool] = {"value": False}
    error: dict[str, BaseException] = {}
    active_context = otel_context.get_current()

    def _target() -> None:
        token = otel_context.attach(active_context)
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive safety net
            error["value"] = exc
        finally:
            otel_context.detach(token)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result["value"]


def _extract_session_id(config: RunnableConfig | None) -> str:
    configurable = (config or {}).get("configurable", {})
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id

    LOGGER.warning(
        "No configurable.thread_id was provided to the graph run. "
        "Using fallback session_id=%s for YAAM consolidation.",
        DEFAULT_THREAD_ID,
    )
    return DEFAULT_THREAD_ID


def _build_final_state(state: GraphState) -> dict[str, Any]:
    routing_parameters = state.get("routing_parameters")
    revisions_count = state.get("revisions_count", 0)

    drafts: list[dict[str, Any]] = []
    if routing_parameters is not None:
        drafts.append(
            {
                "revision": revisions_count,
                "routing_parameters": routing_parameters.model_dump(),
            }
        )

    return {
        "prompt": state.get("alert_text") or None,
        "drafts": drafts,
        "solver_iis_logs": list(state.get("solver_error_logs", [])),
        "final_routing_parameters": routing_parameters.model_dump() if routing_parameters else {},
    }


def _build_metadata(state: GraphState) -> dict[str, Any]:
    solver_result = state.get("solver_result")
    solver_status = (solver_result.status if solver_result else "").upper()

    status = "success"
    if solver_status == "INFEASIBLE":
        status = "infeasible"
    elif solver_status in {"TIMEOUT", "TIMED_OUT"}:
        status = "timeout"

    return {
        "status": status,
        "duration_seconds": 0.0,
        "solver_attempts": max(1, state.get("revisions_count", 0) + 1),
    }


def _consolidate_episode(config: RunnableConfig | None, state: GraphState) -> bool:
    session_id = _extract_session_id(config=config)
    agent_id = state.get("agent_id") or DEFAULT_AGENT_ID
    client = YAAMClient()
    return _run_async_from_sync(
        client.consolidate_episode(
            session_id=session_id,
            final_state=_build_final_state(state),
            metadata=_build_metadata(state),
            agent_id=agent_id,
        )
    )

def _get_llm():
    # Use Gemini by default as specified by user
    if os.environ.get("GOOGLE_API_KEY"):
        return ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview", temperature=0)
    elif os.environ.get("MISTRAL_API_KEY"):
        return ChatMistralAI(model="mistral-medium-2508", temperature=0)
    elif os.environ.get("GROQ_API_KEY"):
        # fallback to Groq
        return ChatGroq(model="openai/gpt-oss-120b", temperature=0)
    else:
        raise ValueError("No active API keys found for Google, Mistral, or Groq in environment.")

def node_ingest_alert(state: GraphState) -> GraphStateUpdate:
    capacities = get_port_capacities()
    return {"port_capacities": capacities}

def node_draft_artifact(state: GraphState) -> GraphStateUpdate:
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
    return {}

def node_run_solver(state: GraphState) -> GraphStateUpdate:
    params = state["routing_parameters"]
    if params is None:
        raise ValueError("routing_parameters must be set before running the solver")
    capacities = state["port_capacities"]
    
    result = evaluate_routing_feasibility(params, capacities)
    if result.status == "INFEASIBLE" and result.iis_log:
        return {"solver_result": result, "solver_error_logs": [result.iis_log]}
    return {"solver_result": result}


def _build_capacity_breakdown(
    params: RoutingParameters,
    capacities: dict[str, int],
) -> tuple[str, list[str]]:
    allocated_by_port: dict[str, int] = {port: 0 for port in ALLOWED_PORTS}
    for alloc in params.allocations:
        allocated_by_port[alloc.port_code] = allocated_by_port.get(alloc.port_code, 0) + alloc.teu_amount

    zero_capacity_ports = [port for port in ALLOWED_PORTS if capacities.get(port, 0) <= 0]
    total_available_capacity = sum(max(capacities.get(port, 0), 0) for port in ALLOWED_PORTS)
    demand = params.total_teu_to_reroute
    deficit = demand - total_available_capacity

    lines = ["Per-port capacity and current allocation:"]
    for port in ALLOWED_PORTS:
        capacity = capacities.get(port, 0)
        allocated = allocated_by_port.get(port, 0)
        headroom = capacity - allocated
        lines.append(
            f"- {port}: capacity={capacity} TEU, allocated={allocated} TEU, headroom={headroom} TEU"
        )

    lines.append(f"Total available capacity across allowed ports: {total_available_capacity} TEU")
    lines.append(f"Total TEU demand: {demand} TEU")
    lines.append(f"Demand minus total available capacity: {deficit} TEU")
    lines.append(
        f"Zero-capacity ports: {', '.join(zero_capacity_ports) if zero_capacity_ports else 'none'}"
    )

    return "\n".join(lines), zero_capacity_ports


def _format_recent_solver_history(error_logs: list[str], limit: int = 3) -> str:
    if not error_logs:
        return "No prior solver errors recorded."

    recent_logs = error_logs[-limit:]
    formatted: list[str] = []
    for index, log in enumerate(recent_logs, start=1):
        formatted.append(f"Attempt -{len(recent_logs) - index + 1}: {log}")
    return "\n---\n".join(formatted)


def _sanitize_allocations_for_capacity(
    params: RoutingParameters,
    capacities: dict[str, int],
) -> tuple[RoutingParameters, list[str]]:
    aggregated: dict[str, int] = {}
    removed_ports: list[str] = []

    for alloc in params.allocations:
        if capacities.get(alloc.port_code, 0) <= 0:
            if alloc.port_code not in removed_ports:
                removed_ports.append(alloc.port_code)
            continue
        aggregated[alloc.port_code] = aggregated.get(alloc.port_code, 0) + alloc.teu_amount

    sanitized_allocations = [
        PortAllocation(port_code=port, teu_amount=amount)
        for port, amount in aggregated.items()
    ]

    sanitized_params = RoutingParameters(
        original_destination=params.original_destination,
        total_teu_to_reroute=params.total_teu_to_reroute,
        allocations=sanitized_allocations,
    )
    return sanitized_params, removed_ports

def node_repair_artifact(state: GraphState) -> GraphStateUpdate:
    params = state["routing_parameters"]
    if params is None:
        raise ValueError("routing_parameters must be set before repair")
    solver_result = state["solver_result"]
    if solver_result is None:
        raise ValueError("solver_result must be set before repair")
    iis_log = solver_result.iis_log
    latest_log = (
        state["solver_error_logs"][-1]
        if state.get("solver_error_logs")
        else (iis_log or "")
    )
    capacities = state.get("port_capacities", {})
    capacity_breakdown, _ = _build_capacity_breakdown(params, capacities)
    recent_error_history = _format_recent_solver_history(state.get("solver_error_logs", []))
    
    # YAAM Integration: Attach Feedback
    yaam_facade.artifact_attach_feedback(artifact_id="draft_id_mock", feedback=latest_log)
    
    llm = _get_llm().with_structured_output(RoutingParameters)
    
    system_msg = SystemMessage(
        content=DOWNSTREAM_SYSTEM_PROMPT.format(
            error_logs=latest_log,
            total_teu_to_reroute=params.total_teu_to_reroute,
            allowed_ports=", ".join(ALLOWED_PORTS),
            capacity_breakdown=capacity_breakdown,
            recent_error_history=recent_error_history,
        )
    )
    human_content = (
        f"Original Routing Parameters:\n{params.model_dump_json(indent=2)}\n\n"
        f"IIS Log (Solver Feedback):\n{latest_log}\n\n"
        f"Allowed ports: {', '.join(ALLOWED_PORTS)}\n"
        f"Port capacities (raw):\n{capacities}\n\n"
        f"Capacity analysis for repair:\n{capacity_breakdown}\n\n"
        f"Recent solver errors:\n{recent_error_history}\n"
    )
    human_msg = HumanMessage(content=human_content)
    
    new_params = llm.invoke([system_msg, human_msg])
    sanitized_params, removed_ports = _sanitize_allocations_for_capacity(new_params, capacities)
    if removed_ports:
        LOGGER.info(
            "Removed allocations to zero-capacity ports in repair output: %s",
            ", ".join(removed_ports),
        )
    
    yaam_facade.artifact_create_revision(
        previous_artifact_id="draft_id_mock",
        new_artifact_data=sanitized_params.model_dump(),
    )
    revisions = state.get("revisions_count", 0) + 1
    
    return {"routing_parameters": sanitized_params, "revisions_count": revisions}

def node_commit_final(state: GraphState, config: RunnableConfig | None = None) -> GraphStateUpdate:
    yaam_facade.artifact_commit_final(artifact_id="revision_id_mock")
    if not _consolidate_episode(config=config, state=state):
        LOGGER.warning("Episode consolidation to YAAM failed.")
    return {}

def route_after_solver(state: GraphState) -> Literal["node_commit_final", "node_repair_artifact"]:
    solver_result = state["solver_result"]
    if solver_result is None:
        raise ValueError("solver_result must be set before routing")
    if solver_result.status == "FEASIBLE":
        return "node_commit_final"
    if solver_result.status == "INFEASIBLE" and is_terminal_infeasible_log(solver_result.iis_log):
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


def compile_graph_with_adaptive_checkpointer():
    checkpointer = create_checkpointer()
    return workflow.compile(checkpointer=checkpointer)


graph = compile_graph_with_adaptive_checkpointer()
