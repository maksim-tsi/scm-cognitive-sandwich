from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph  # type: ignore[attr-defined]

from langchain_core.messages import HumanMessage, SystemMessage

from agents.variant_b.state import (
    CandidateScenario,
    CandidateScenarioSet,
    IncidentTrigger,
    JudgeSemanticVerdict,
    ToolLedgerEntry,
    VariantBState,
    VariantBStateUpdate,
)
from llm.call_llm import get_openrouter_chat
from llm.openrouter_embeddings import embed_text
from memory.checkpointer import create_checkpointer
from memory.yaam_facade import get_facade
from schemas.sandbox import (
    CandidateScenario as SandboxCandidateScenario,
    SandboxExecutionOutput,
    SimulationExecutionRequest,
)
from tools.langchain_adapter import build_langchain_tools, resolve_tool_specs_by_name


MAX_RETRIES = 3


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def node_gather_context(state: VariantBState) -> VariantBStateUpdate:
    incident = state["incident"]
    # External ground truth: fetch port capacities from the maritime-port-sandbox client.
    # For WinterSim baseline, treat affected_nodes as closed/forbidden targets.
    from clients.port_sandbox import get_port_capacities  # noqa: WPS433
    from solver.routing_model import ALLOWED_PORTS  # noqa: WPS433

    capacities = get_port_capacities(list(ALLOWED_PORTS))
    context = {
        "incident_id": incident.incident_id,
        "affected_nodes": list(incident.affected_nodes),
        "cargo_demand": incident.cargo_demand,
        "raw_alert_text": incident.raw_alert_text,
        "forbidden_ports": list(incident.affected_nodes),
        "port_capacities": capacities,
    }
    return {"incident_context": context}


def _build_generation_prompt(
    *,
    incident: IncidentTrigger,
    incident_context: dict[str, Any],
    judge_feedback: list[str],
    retry_count: int,
) -> str:
    demo_clarifying = _is_truthy(os.getenv("VARIANT_B_DEMO_CLARIFYING_LOOP")) and retry_count == 0
    demo_instruction = ""
    if demo_clarifying:
        demo_instruction = (
            "\n\nDEMO_MODE:\n"
            "- In Scenario 1 ONLY, intentionally violate mass balance (sum allocations != cargo_demand).\n"
            "- In Scenarios 2 and 3, attempt to comply with all constraints.\n"
        )

    forbidden = incident_context.get("forbidden_ports", [])
    capacities = incident_context.get("port_capacities", {})
    feedback_block = "\n".join(f"- {msg}" for msg in judge_feedback[-3:]) if judge_feedback else "<none>"

    return (
        "You are generating exactly 3 candidate disruption-response scenarios.\n"
        "Output MUST be valid JSON matching the provided schema.\n\n"
        "Hard constraints:\n"
        "1) Mass balance: each scenario's allocations must sum EXACTLY to cargo_demand (TEU).\n"
        "2) Forbidden ports: do NOT allocate any TEU to forbidden ports.\n"
        "3) Capacity: do NOT allocate more than port_capacities[port_code] when provided.\n"
        "4) Tool governance: if you provide any numeric claimed_metrics, you MUST back them with a tool call plan.\n"
        "5) Diversification: the 3 scenarios must be meaningfully different.\n\n"
        f"Incident:\n{incident.model_dump_json(indent=2)}\n\n"
        f"Forbidden ports:\n{json.dumps(forbidden, indent=2)}\n\n"
        f"Port capacities (TEU):\n{json.dumps(capacities, indent=2)}\n\n"
        f"Recent judge feedback (fix these):\n{feedback_block}\n"
        f"{demo_instruction}\n"
        "Return ONLY the JSON for CandidateScenarioSet."
    )


def _execute_tool_calls(
    *,
    tool_specs_by_name: dict[str, Any],
    ledger_start_index: int,
    tool_calls: list[dict[str, Any]],
) -> list[ToolLedgerEntry]:
    ledger: list[ToolLedgerEntry] = []
    for offset, tool_call in enumerate(tool_calls, start=1):
        tool_name = str(tool_call.get("tool_name", "")).strip()
        raw_args = tool_call.get("args")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        entry_id = f"tool-{ledger_start_index + offset}"

        spec = tool_specs_by_name.get(tool_name)
        if spec is None:
            ledger.append(
                ToolLedgerEntry(
                    entry_id=entry_id,
                    tool_name=tool_name,
                    args=args,
                    output=None,
                    error=f"Unknown tool: {tool_name}",
                    status="ERROR",
                )
            )
            continue

        try:
            validated = spec.input_model.model_validate(args)
            result = spec.fn(validated)
            output = result.model_dump() if hasattr(result, "model_dump") else {"result": result}
            ledger.append(
                ToolLedgerEntry(
                    entry_id=entry_id,
                    tool_name=tool_name,
                    args=args,
                    output=output,
                    error=None,
                    status="SUCCESS",
                )
            )
        except Exception as exc:  # noqa: BLE001 (tool errors are part of state)
            ledger.append(
                ToolLedgerEntry(
                    entry_id=entry_id,
                    tool_name=tool_name,
                    args=args,
                    output=None,
                    error=str(exc),
                    status="ERROR",
                )
            )

    return ledger


def node_generate_scenarios(state: VariantBState) -> VariantBStateUpdate:
    incident_id = state["incident"].incident_id
    retry_count = int(state.get("retry_count", 0))
    incident = state["incident"]
    incident_context = state.get("incident_context", {})
    judge_feedback = list(state.get("judge_feedback", []))

    langchain_tools = build_langchain_tools()
    tool_specs_by_name = resolve_tool_specs_by_name()

    model_name = os.getenv("LLM_MODEL_GENERATE") or os.getenv("LLM_MODEL")
    llm = cast(Any, get_openrouter_chat(model=model_name).bind_tools(langchain_tools)).with_structured_output(
        CandidateScenarioSet
    )

    prompt = _build_generation_prompt(
        incident=incident,
        incident_context=incident_context,
        judge_feedback=judge_feedback,
        retry_count=retry_count,
    )

    system_msg = SystemMessage(content="You are a strict JSON generator. Never include prose outside JSON.")
    human_msg = HumanMessage(content=prompt)
    candidate_set = cast(CandidateScenarioSet, llm.invoke([system_msg, human_msg]))

    tool_ledger_existing = list(state.get("tool_ledger", []))
    ledger_start_index = len(tool_ledger_existing)

    scenarios: list[dict[str, Any]] = []
    new_ledger_entries: list[ToolLedgerEntry] = []

    for index, scenario in enumerate(candidate_set.scenarios, start=1):
        scenario_id = f"{incident_id}-S{index}"

        tool_calls = [call.model_dump() for call in scenario.tool_calls]
        executed = _execute_tool_calls(
            tool_specs_by_name=tool_specs_by_name,
            ledger_start_index=ledger_start_index + len(new_ledger_entries),
            tool_calls=tool_calls,
        )
        new_ledger_entries.extend(executed)

        scenarios.append(
            {
                "scenario_id": scenario_id,
                "revision": retry_count,
                "title": scenario.title,
                "rationale": scenario.rationale,
                "allocations": [alloc.model_dump() for alloc in scenario.allocations],
                "tool_calls": tool_calls,
                "claimed_metrics": dict(scenario.claimed_metrics),
                "claimed_metrics_evidence": dict(scenario.claimed_metrics_evidence),
            }
        )

    return {
        "scenarios": scenarios,
        "tool_ledger": [entry.model_dump() for entry in new_ledger_entries],
    }

def _pass1_deterministic_checks(state: VariantBState) -> tuple[bool, list[str], list[str]]:
    incident = state["incident"]
    incident_context = state.get("incident_context", {})
    scenarios = state.get("scenarios", [])
    tool_ledger = state.get("tool_ledger", [])

    forbidden_ports = set(str(p) for p in incident_context.get("forbidden_ports", []) if isinstance(p, str))
    capacities = incident_context.get("port_capacities", {})
    if not isinstance(capacities, dict):
        capacities = {}
    ledger_by_id = {str(entry.get("entry_id")): entry for entry in tool_ledger if isinstance(entry, dict)}

    findings: list[str] = []
    feedback: list[str] = []

    if len(scenarios) != 3:
        findings.append("SYNTAX: scenarios must contain exactly 3 entries.")
        feedback.append("Generate exactly 3 scenarios.")
        return False, findings, feedback

    allowed_tool_names = set(resolve_tool_specs_by_name().keys())

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            findings.append("SYNTAX: scenario must be an object.")
            feedback.append("Each scenario must be a JSON object matching the schema.")
            continue

        scenario_id = str(scenario.get("scenario_id", "unknown"))
        try:
            CandidateScenario.model_validate(
                {
                    "title": scenario.get("title"),
                    "rationale": scenario.get("rationale"),
                    "allocations": scenario.get("allocations"),
                    "tool_calls": scenario.get("tool_calls", []),
                    "claimed_metrics": scenario.get("claimed_metrics", {}),
                    "claimed_metrics_evidence": scenario.get("claimed_metrics_evidence", {}),
                }
            )
        except Exception as exc:  # noqa: BLE001
            findings.append(f"SYNTAX({scenario_id}): {exc}")
            feedback.append(f"Fix schema errors in {scenario_id}; ensure required keys exist and types match.")
            continue

        allocations = scenario.get("allocations", [])
        total = 0
        for alloc in allocations:
            port = str(alloc.get("port_code", "")).strip()
            amount = int(alloc.get("teu_amount", 0))
            total += amount

            if port in forbidden_ports:
                findings.append(f"PHYSICS({scenario_id}): allocation targets forbidden port {port}.")
                feedback.append(f"Remove allocations to forbidden/closed port {port} in {scenario_id}.")

            cap = capacities.get(port)
            if isinstance(cap, (int, float)) and amount > int(cap):
                findings.append(f"PHYSICS({scenario_id}): allocation {amount} exceeds capacity {int(cap)} for {port}.")
                feedback.append(f"Reduce {port} allocation in {scenario_id} to <= {int(cap)} TEU.")

        if total != incident.cargo_demand:
            findings.append(
                f"MASS_BALANCE({scenario_id}): allocations sum {total} != cargo_demand {incident.cargo_demand}."
            )
            feedback.append(f"Ensure allocations sum EXACTLY to {incident.cargo_demand} TEU in {scenario_id}.")

        tool_calls = scenario.get("tool_calls", [])
        for tool_call in tool_calls:
            name = str(tool_call.get("tool_name", "")).strip()
            if name not in allowed_tool_names:
                findings.append(f"SYNTAX({scenario_id}): tool_name {name!r} is not in ACTIVE_TOOLS.")
                feedback.append(f"Use only tools from ACTIVE_TOOLS; {name!r} is not allowed.")

        claimed_metrics = scenario.get("claimed_metrics", {})
        evidence = scenario.get("claimed_metrics_evidence", {})
        if not isinstance(claimed_metrics, dict) or not isinstance(evidence, dict):
            findings.append(f"SYNTAX({scenario_id}): claimed_metrics and evidence must be objects.")
            feedback.append(f"Use objects for claimed_metrics and claimed_metrics_evidence in {scenario_id}.")
            continue

        for metric_key in claimed_metrics.keys():
            entry_id = evidence.get(metric_key)
            if not isinstance(entry_id, str) or not entry_id.strip():
                findings.append(f"EPISTEMIC({scenario_id}): metric {metric_key!r} missing evidence ledger entry.")
                feedback.append(
                    f"For any claimed metric ({metric_key}) in {scenario_id}, include claimed_metrics_evidence."
                )
                continue
            ledger = ledger_by_id.get(entry_id)
            if ledger is None or ledger.get("status") != "SUCCESS":
                findings.append(
                    f"EPISTEMIC({scenario_id}): evidence entry {entry_id!r} missing or not SUCCESS."
                )
                feedback.append(
                    f"Only claim {metric_key} when backed by a successful deterministic tool execution."
                )

    ok = not findings
    return ok, findings, feedback


def node_judge_validation(state: VariantBState) -> VariantBStateUpdate:
    retry_count = int(state.get("retry_count", 0))
    ok, findings, feedback = _pass1_deterministic_checks(state)

    if not ok:
        next_retry = retry_count + 1
        combined = " | ".join(feedback) if feedback else "Deterministic validation failed."
        update: VariantBStateUpdate = {
            "judge_verdict": "REJECT",
            "retry_count": next_retry,
            "judge_feedback": [combined],
            "judge_findings": findings,
        }
        if next_retry >= MAX_RETRIES:
            update["fatal_status"] = "FATAL_VALIDATION_ERROR"
        return update

    # Pass 2: LLM semantic judging (SLA, APICS compliance, diversification).
    incident = state["incident"]
    incident_context = state.get("incident_context", {})
    scenarios = state.get("scenarios", [])

    model_name = os.getenv("LLM_MODEL_JUDGE") or os.getenv("LLM_MODEL")
    llm = cast(Any, get_openrouter_chat(model=model_name)).with_structured_output(JudgeSemanticVerdict)

    system = SystemMessage(
        content=(
            "You are an LLM-as-a-Judge gatekeeper. You must output a strict JSON verdict.\n"
            "Rules:\n"
            "- If ANY scenario violates SLA/contract constraints from incident_context, REJECT.\n"
            "- If scenarios are not diversified/orthogonal, REJECT.\n"
            "- If reasoning is not APICS-compliant or is nonsensical, REJECT.\n"
            "- Feedback must be actionable and concise.\n"
            "Output status must be exactly 'ACCEPT' or 'REJECT'."
        )
    )
    human = HumanMessage(
        content=(
            "Evaluate the 3 scenarios and incident context.\n\n"
            f"incident:\n{incident.model_dump_json(indent=2)}\n\n"
            f"incident_context:\n{json.dumps(incident_context, indent=2)}\n\n"
            f"scenarios:\n{json.dumps(scenarios, indent=2)}\n"
        )
    )

    verdict_raw = cast(Any, llm.invoke([system, human]))
    verdict = (
        verdict_raw
        if isinstance(verdict_raw, JudgeSemanticVerdict)
        else JudgeSemanticVerdict.model_validate(verdict_raw)
    )
    status = verdict.status.strip().upper()

    if status != "ACCEPT":
        next_retry = retry_count + 1
        update2: VariantBStateUpdate = {
            "judge_verdict": "REJECT",
            "retry_count": next_retry,
            "judge_feedback": [verdict.feedback],
            "judge_findings": verdict.violations,
        }
        if next_retry >= MAX_RETRIES:
            update2["fatal_status"] = "FATAL_VALIDATION_ERROR"
        return update2

    return {"judge_verdict": "ACCEPT", "judge_findings": verdict.violations}


def node_execute_sandbox(state: VariantBState) -> VariantBStateUpdate:
    from opentelemetry import trace  # noqa: WPS433

    from core.sandbox_client import execute_simulation  # noqa: WPS433

    tracer = trace.get_tracer(__name__)

    scenarios = state.get("scenarios", [])
    run_id = str(state.get("run_id", "unknown"))
    thread_id = str(state.get("thread_id", "unknown"))

    base_url = (os.getenv("SANDBOX_API_URL") or "").strip()
    if not base_url:
        return {"fatal_status": "FATAL_SANDBOX_ERROR", "sandbox_results": [{"error": "SANDBOX_API_URL missing"}]}

    timeout_s = 30.0
    raw_timeout = os.getenv("SANDBOX_TIMEOUT_S")
    if raw_timeout and raw_timeout.strip():
        try:
            timeout_s = float(raw_timeout)
        except ValueError:
            timeout_s = 30.0

    sandbox_scenarios: list[SandboxCandidateScenario] = []
    for scenario in scenarios:
        scenario_id = str(scenario.get("scenario_id", "unknown"))
        allocations = scenario.get("allocations", [])
        ports: list[tuple[str, int]] = []
        if isinstance(allocations, list):
            for alloc in allocations:
                if not isinstance(alloc, dict):
                    continue
                port = str(alloc.get("port_code", "")).strip().upper()
                amount = alloc.get("teu_amount")
                if not port or not isinstance(amount, int):
                    continue
                ports.append((port, amount))

        ordered_ports = [port for port, _ in sorted(ports, key=lambda item: (-item[1], item[0]))]
        sandbox_scenarios.append(
            SandboxCandidateScenario(
                scenario_id=scenario_id,
                target_ports=ordered_ports,
            )
        )

    request = SimulationExecutionRequest(run_id=run_id, scenarios=sandbox_scenarios)

    with tracer.start_as_current_span("node_execute_sandbox") as span:
        span.set_attribute("metadata.run_id", run_id)
        span.set_attribute("metadata.thread_id", thread_id)
        span.set_attribute("scenario_count", len(sandbox_scenarios))

        try:
            output: SandboxExecutionOutput = execute_simulation(
                base_url=base_url,
                request=request,
                timeout_s=timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 (network/schema errors are part of state)
            span.set_attribute("status", "ERROR")
            span.set_attribute("error", str(exc)[:500])
            return {
                "fatal_status": "FATAL_SANDBOX_ERROR",
                "sandbox_results": [{"error": str(exc), "run_id": run_id}],
            }

        results: list[dict[str, Any]] = []
        for executed in output.simulated_scenarios:
            row: dict[str, Any] = {
                "scenario_id": executed.scenario_id,
                "execution_status": executed.execution_status,
                "failure_reason": executed.failure_reason,
                "critical_events_count": len(executed.critical_events),
                "raw": executed.model_dump(),
            }
            if executed.execution_status == "SUCCESS" and executed.metrics is not None:
                row.update(
                    {
                        "time": float(executed.metrics.total_lead_time_hours),
                        "cost": float(executed.metrics.total_cost_usd),
                        "risk": float(executed.metrics.bottleneck_severity),
                        "metrics": executed.metrics.model_dump(),
                    }
                )
            results.append(row)

        span.set_attribute("status", "OK")
        span.set_attribute("sandbox_results_count", len(results))
        return {"sandbox_results": results}


def node_synthesize_report(state: VariantBState) -> VariantBStateUpdate:
    from opentelemetry import trace  # noqa: WPS433

    from core.pareto_frontier import pareto_frontier  # noqa: WPS433
    from memory.models import Episode, KnowledgeDocument  # noqa: WPS433

    tracer = trace.get_tracer(__name__)

    incident = state["incident"]
    verdict = state.get("judge_verdict") or "UNKNOWN"
    fatal = state.get("fatal_status")
    retry_count = int(state.get("retry_count", 0))
    run_id = str(state.get("run_id", incident.incident_id))
    thread_id = str(state.get("thread_id", "unknown"))

    sandbox_results = state.get("sandbox_results", [])
    success_rows = [
        row
        for row in sandbox_results
        if isinstance(row, dict)
        and row.get("execution_status") == "SUCCESS"
        and all(isinstance(row.get(k), (int, float)) for k in ("time", "cost", "risk"))
    ]

    pareto_ids: list[str] = []
    if success_rows:
        pareto_ids = pareto_frontier(success_rows, id_key="scenario_id", minimize=("time", "cost", "risk"))

    metrics_lines: list[str] = []
    metrics_lines.append("| scenario_id | status | time(h) | cost($) | risk |")
    metrics_lines.append("|---|---:|---:|---:|---:|")
    for row in sandbox_results:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("scenario_id", "unknown"))
        status = str(row.get("execution_status", row.get("status", "UNKNOWN")))
        time_v = row.get("time")
        cost_v = row.get("cost")
        risk_v = row.get("risk")
        metrics_lines.append(
            f"| `{sid}` | `{status}` | {time_v if time_v is not None else ''} | "
            f"{cost_v if cost_v is not None else ''} | {risk_v if risk_v is not None else ''} |"
        )

    base_report = "\n".join(
        [
            "# Variant B Report",
            "",
            f"- run_id: `{run_id}`",
            f"- thread_id: `{thread_id}`",
            f"- incident_id: `{incident.incident_id}`",
            f"- verdict: `{verdict}`",
            f"- retry_count: `{retry_count}`",
            f"- fatal_status: `{fatal}`" if fatal else "- fatal_status: `<none>`",
            "",
            "## Sandbox Metrics",
            "",
            *metrics_lines,
            "",
            f"## Pareto Frontier (minimize time, cost, risk)\n\n- frontier_ids: {pareto_ids}",
            "",
        ]
    )

    update: VariantBStateUpdate = {
        "pareto_frontier_ids": pareto_ids,
    }

    with tracer.start_as_current_span("node_synthesize_report") as span:
        span.set_attribute("metadata.run_id", run_id)
        span.set_attribute("metadata.thread_id", thread_id)
        span.set_attribute("pareto_frontier_size", len(pareto_ids))

        if fatal:
            span.set_attribute("status", "FATAL")
            update["final_report_md"] = base_report + "\n\n(Fatal status present; skipping YAAM persistence.)\n"
            return update

        # Ask the LLM to narrate trade-offs (Python decides frontier).
        narrative_md = ""
        try:
            model_name = os.getenv("LLM_MODEL_SYNTH") or os.getenv("LLM_MODEL")
            llm = cast(Any, get_openrouter_chat(model=model_name))
            system = SystemMessage(
                content=(
                    "Write a concise Markdown analysis of the sandbox metrics and Pareto frontier.\n"
                    "Rules:\n"
                    "- Do NOT change the Pareto frontier ids provided; treat them as ground truth.\n"
                    "- Do NOT invent metrics; only reference the table provided.\n"
                    "- Recommend a scenario id and justify with time/cost/risk trade-offs.\n"
                )
            )
            human = HumanMessage(
                content=(
                    "Incident context and results:\n\n"
                    f"incident:\n{incident.model_dump_json(indent=2)}\n\n"
                    f"metrics_table:\n{chr(10).join(metrics_lines)}\n\n"
                    f"pareto_frontier_ids: {pareto_ids}\n"
                )
            )
            resp = llm.invoke([system, human])
            narrative_md = str(getattr(resp, "content", resp) or "").strip()
        except Exception as exc:  # noqa: BLE001
            narrative_md = f"_LLM narrative failed: {exc}_"

        # Embed a successful episode summary (Qwen3).
        embedding_model = "qwen/qwen3-embedding-8b"
        embedding_latency_ms: float | None = None
        embedding: list[float] | None = None
        episode_text = (
            f"run_id={run_id}\n"
            f"incident_id={incident.incident_id}\n"
            f"frontier_ids={pareto_ids}\n"
            f"verdict={verdict}\n"
            f"metrics_table:\n{chr(10).join(metrics_lines)}\n"
        )

        with tracer.start_as_current_span("openrouter.embed") as embed_span:
            embed_span.set_attribute("metadata.run_id", run_id)
            embed_span.set_attribute("metadata.thread_id", thread_id)
            embed_span.set_attribute("embedding_model", embedding_model)
            try:
                embedding, embedding_latency_ms = embed_text(episode_text, model=embedding_model)
                embed_span.set_attribute("embedding_latency_ms", float(embedding_latency_ms))
                embed_span.set_attribute("status", "OK")
            except Exception as exc:  # noqa: BLE001
                embed_span.set_attribute("status", "ERROR")
                embed_span.set_attribute("error", str(exc)[:500])
                update["fatal_status"] = "FATAL_YAAM_ERROR"
                update["final_report_md"] = base_report + "\n\n" + narrative_md + "\n"
                update["embedding_model"] = embedding_model
                update["embedding_latency_ms"] = embedding_latency_ms
                update["yaam_l3_status"] = f"ERROR: {exc}"
                update["yaam_l4_status"] = "SKIPPED"
                return update

        update["embedding_model"] = embedding_model
        update["embedding_latency_ms"] = float(embedding_latency_ms or 0.0)
        span.set_attribute("embedding_latency_ms", float(embedding_latency_ms or 0.0))

        report = base_report + "\n\n## Trade-off Analysis\n\n" + (narrative_md or "_No narrative generated._") + "\n"
        update["final_report_md"] = report

        facade = get_facade()
        qdrant_collection = (os.getenv("QDRANT_COLLECTION") or "").strip().strip("'").strip('"')
        typesense_collection = (os.getenv("TYPESENSE_COLLECTION") or "").strip().strip("'").strip('"')

        now = datetime.now(tz=UTC)
        episode = Episode(
            episode_id=str(uuid4()),
            session_id=thread_id,
            summary=f"Variant B successful run {run_id} (Pareto frontier size={len(pareto_ids)})",
            narrative=None,
            source_fact_ids=[],
            fact_count=0,
            time_window_start=now,
            time_window_end=now,
            duration_seconds=0.0,
            fact_valid_from=now,
            fact_valid_to=None,
            source_observation_timestamp=now,
            embedding_model=embedding_model,
            vector_id=None,
            graph_node_id=None,
            entities=[],
            relationships=[],
            topics=["winsim", "variant_b"],
            importance_score=0.5,
            consolidated_at=now,
            consolidation_method="orchestrator_variant_b",
            metadata={
                "run_id": run_id,
                "incident_id": incident.incident_id,
                "pareto_frontier_ids": pareto_ids,
                "embedding_latency_ms": float(embedding_latency_ms or 0.0),
            },
        )

        yaam_l3_status = "SKIPPED"
        yaam_l4_status = "SKIPPED"

        with tracer.start_as_current_span("yaam.l3_upsert_episode") as l3_span:
            l3_span.set_attribute("metadata.run_id", run_id)
            l3_span.set_attribute("metadata.thread_id", thread_id)
            l3_span.set_attribute("collection", qdrant_collection)
            try:
                if not qdrant_collection:
                    raise ValueError("QDRANT_COLLECTION is not set")
                if embedding is None:
                    raise ValueError("Embedding missing")
                facade.l3_upsert_episode(episode=episode, embedding=embedding, collection=qdrant_collection)
                yaam_l3_status = "SUCCESS"
                l3_span.set_attribute("status", "OK")
            except Exception as exc:  # noqa: BLE001
                yaam_l3_status = f"ERROR: {exc}"
                l3_span.set_attribute("status", "ERROR")
                l3_span.set_attribute("error", str(exc)[:500])

        doc = KnowledgeDocument(
            knowledge_id=f"report-{run_id}",
            session_id=thread_id,
            title=f"Variant B Report {run_id}",
            content=report,
            knowledge_type="final_report",
            confidence_score=0.7,
            source_episode_ids=[episode.episode_id],
            episode_count=1,
            provenance_links=[],
            category="winsim",
            tags=["variant_b", "report"],
            domain="scm",
            metadata={"run_id": run_id, "thread_id": thread_id},
        )

        with tracer.start_as_current_span("yaam.l4_upsert_document") as l4_span:
            l4_span.set_attribute("metadata.run_id", run_id)
            l4_span.set_attribute("metadata.thread_id", thread_id)
            l4_span.set_attribute("collection", typesense_collection)
            try:
                if not typesense_collection:
                    raise ValueError("TYPESENSE_COLLECTION is not set")
                facade.l4_upsert_document(doc=doc, collection=typesense_collection)
                yaam_l4_status = "SUCCESS"
                l4_span.set_attribute("status", "OK")
            except Exception as exc:  # noqa: BLE001
                yaam_l4_status = f"ERROR: {exc}"
                l4_span.set_attribute("status", "ERROR")
                l4_span.set_attribute("error", str(exc)[:500])

        update["yaam_l3_status"] = yaam_l3_status
        update["yaam_l4_status"] = yaam_l4_status
        span.set_attribute("yaam_l3_status", yaam_l3_status)
        span.set_attribute("yaam_l4_status", yaam_l4_status)

        if yaam_l3_status != "SUCCESS" or yaam_l4_status != "SUCCESS":
            update["fatal_status"] = "FATAL_YAAM_ERROR"
            span.set_attribute("status", "ERROR")
        else:
            span.set_attribute("status", "OK")

        return update


def _route_after_judge(
    state: VariantBState,
) -> Literal["node_execute_sandbox", "node_generate_scenarios", "__end__"]:
    if state.get("fatal_status") == "FATAL_VALIDATION_ERROR":
        return "__end__"

    verdict = (state.get("judge_verdict") or "").upper()
    if verdict == "ACCEPT":
        return "node_execute_sandbox"
    return "node_generate_scenarios"


def compile_variant_b_graph():
    workflow: StateGraph = StateGraph(VariantBState)

    workflow.add_node("node_gather_context", node_gather_context)
    workflow.add_node("node_generate_scenarios", node_generate_scenarios)
    workflow.add_node("node_judge_validation", node_judge_validation)
    workflow.add_node("node_execute_sandbox", node_execute_sandbox)
    workflow.add_node("node_synthesize_report", node_synthesize_report)

    workflow.add_edge(START, "node_gather_context")
    workflow.add_edge("node_gather_context", "node_generate_scenarios")
    workflow.add_edge("node_generate_scenarios", "node_judge_validation")

    workflow.add_conditional_edges(
        "node_judge_validation",
        _route_after_judge,
        {
            "node_execute_sandbox": "node_execute_sandbox",
            "node_generate_scenarios": "node_generate_scenarios",
            "__end__": END,
        },
    )

    workflow.add_edge("node_execute_sandbox", "node_synthesize_report")
    workflow.add_edge("node_synthesize_report", END)

    raw_prefix = os.getenv("REDIS_PREFIX")
    prefix = raw_prefix.strip().strip("'").strip('"') if isinstance(raw_prefix, str) else ""
    key_prefix = f"{prefix}checkpoint:" if prefix else "sandwich:checkpoint:"
    checkpointer = create_checkpointer(key_prefix=key_prefix)
    return workflow.compile(checkpointer=checkpointer)

_CACHED_VARIANT_B_GRAPH: Any | None = None


def get_variant_b_graph():
    global _CACHED_VARIANT_B_GRAPH
    if _CACHED_VARIANT_B_GRAPH is None:
        _CACHED_VARIANT_B_GRAPH = compile_variant_b_graph()
    return _CACHED_VARIANT_B_GRAPH
