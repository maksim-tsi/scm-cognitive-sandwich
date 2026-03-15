import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# Ensure src directory is in path for script execution from workspace root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)

from agents.state import GraphState, RoutingParameters, SolverResult  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.errors import GraphRecursionError  # noqa: E402

ALL_PORTS = ["NLRTM", "BEANR", "DEHAM", "DEBRV"]
BASE_CAPACITY = 15000
EVENT_TOTAL_CLOSURE = "TOTAL_CLOSURE"
EVENT_SEVERE_CONGESTION = "SEVERE_CONGESTION"
EVENT_OPERATIONAL_RESTRICTION = "OPERATIONAL_RESTRICTION"
DISRUPTION_EVENTS = {
    EVENT_TOTAL_CLOSURE,
    EVENT_SEVERE_CONGESTION,
    EVENT_OPERATIONAL_RESTRICTION,
}

SCENARIO_COLUMNS = [
    "run_id",
    "total_teu",
    "primary_port",
    "primary_event",
    "secondary_port",
    "secondary_event",
    "capacity_multiplier",
    "alert_text",
]
RESULT_COLUMNS = [
    "run_id",
    "primary_event",
    "secondary_event",
    "final_status",
    "revisions_count",
    "total_time_sec",
    "llm_token_count",
    "final_json",
]


class RetriableGraphInvokeError(Exception):
    pass


def _normalize_run_id(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("run_id values must not be empty")
    if not candidate.isdigit():
        raise ValueError(f"run_id must be numeric, got: {value}")
    return candidate.zfill(3)


def _parse_run_ids_argument(raw_run_ids: str) -> list[str]:
    parsed = [_normalize_run_id(part) for part in raw_run_ids.split(",")]
    if not parsed:
        raise ValueError("--run-ids must contain at least one run id")
    return parsed


def _filter_scenarios_by_run_ids(
    scenarios: list[dict[str, str]],
    run_ids: list[str],
) -> list[dict[str, str]]:
    scenarios_by_run_id = {
        _normalize_run_id(str(row["run_id"])): row
        for row in scenarios
    }
    missing_run_ids = [run_id for run_id in run_ids if run_id not in scenarios_by_run_id]
    if missing_run_ids:
        raise ValueError(f"run_ids not found in scenarios dataset: {missing_run_ids}")

    return [scenarios_by_run_id[run_id] for run_id in run_ids]


def _initialize_observability() -> None:
    from core.observability import setup_observability  # noqa: WPS433

    print("Tracing environment before setup:")
    print(f"  OTEL_RESOURCE_ATTRIBUTES={os.environ.get('OTEL_RESOURCE_ATTRIBUTES')}")
    print(f"  OTEL_SERVICE_NAME={os.environ.get('OTEL_SERVICE_NAME')}")
    print(f"  PHOENIX_PROJECT_NAME={os.environ.get('PHOENIX_PROJECT_NAME')}")
    print(f"  PHOENIX_COLLECTOR_ENDPOINT={os.environ.get('PHOENIX_COLLECTOR_ENDPOINT')}")
    setup_observability()


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None:
        chain.append(current)
        next_exc: BaseException | None = None
        if current.__cause__ is not None:
            next_exc = current.__cause__
        elif current.__context__ is not None:
            next_exc = current.__context__
        current = next_exc
    return chain


def _is_retriable_error(exc: BaseException) -> bool:
    for current in _iter_exception_chain(exc):
        if isinstance(current, httpx.TransportError):
            return True
        if isinstance(current, httpx.HTTPStatusError) and current.response.status_code == 429:
            return True
        message = str(current).lower()
        if "429" in message or "rate limit" in message:
            return True
    return False


def _get_graph():
    # Import lazily so helper tests can run without LangGraph dependency installed.
    from agents.graph import graph  # noqa: WPS433

    return graph


@retry(
    retry=retry_if_exception(_is_retriable_error),
    wait=wait_exponential(min=2, max=20),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _stream_graph_with_retry(
    initial_state: GraphState,
    config: dict[str, Any],
    run_id: str,
) -> GraphState:
    running_state: dict[str, Any] = dict(initial_state)

    try:
        for output in _get_graph().stream(initial_state, config=config, stream_mode="updates"):
            if not isinstance(output, dict):
                continue

            for node_name, state_update in output.items():
                print(f"[STREAM run={run_id}] node={node_name}")

                if state_update is None:
                    state_update = {}
                if not isinstance(state_update, dict):
                    continue

                _merge_graph_state(running_state, state_update)

                if node_name in {"node_run_solver", "node_repair_artifact"}:
                    solver_result = running_state.get("solver_result")
                    solver_status = (
                        solver_result.status
                        if isinstance(solver_result, SolverResult)
                        else "UNKNOWN"
                    )
                    latest_error_log = _latest_solver_error_log(running_state) or "<none>"
                    print(
                        "  "
                        f"solver_status={solver_status} "
                        f"latest_solver_error={latest_error_log}"
                    )

        # Running state now reflects the updates from the final streamed chunk.
        return running_state
    except Exception as exc:
        setattr(exc, "running_state", running_state)
        if _is_retriable_error(exc):
            raise RetriableGraphInvokeError(str(exc)) from exc
        raise


def _merge_graph_state(current_state: dict[str, Any], state_update: dict[str, Any]) -> None:
    for key, value in state_update.items():
        if key == "solver_error_logs" and isinstance(value, list):
            existing_value = current_state.get(key)
            if isinstance(existing_value, list):
                current_state[key] = [*existing_value, *value]
            else:
                current_state[key] = list(value)
            continue
        current_state[key] = value


def _latest_solver_error_log(state: GraphState | dict[str, Any]) -> str | None:
    logs = state.get("solver_error_logs")
    if isinstance(logs, list) and logs:
        return str(logs[-1])
    return None


def _derive_final_status(state: GraphState | dict[str, Any]) -> str:
    solver_result = state.get("solver_result")
    if isinstance(solver_result, SolverResult):
        if solver_result.status.upper() == "FEASIBLE":
            return "FEASIBLE"
        if solver_result.status.upper() == "INFEASIBLE":
            return "INFEASIBLE"
    return "ERROR"


def _recover_state_from_exception(
    exc: BaseException,
    fallback_state: GraphState | dict[str, Any],
) -> GraphState | dict[str, Any]:
    candidate_attributes = ["last_state", "state", "running_state", "graph_state", "values"]
    for attr in candidate_attributes:
        candidate = getattr(exc, attr, None)
        if isinstance(candidate, dict):
            return candidate

    for arg in exc.args:
        if isinstance(arg, dict):
            return arg

    return fallback_state


def _serialize_error_json(
    exc: BaseException,
    state: GraphState | dict[str, Any],
    error_type: str,
) -> str:
    solver_result = state.get("solver_result")
    payload: dict[str, Any] = {
        "error_type": error_type,
        "error": str(exc),
    }
    if isinstance(solver_result, SolverResult):
        payload["solver_status"] = solver_result.status

    latest_error_log = _latest_solver_error_log(state)
    if latest_error_log:
        payload["latest_solver_error_log"] = latest_error_log

    return json.dumps(payload, sort_keys=True)


def _load_scenarios(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        rows = [row for row in reader]

    missing_columns = [col for col in SCENARIO_COLUMNS if col not in (reader.fieldnames or [])]
    if missing_columns:
        raise ValueError(f"Scenario CSV missing required columns: {missing_columns}")

    return rows


def _compute_world_state(
    primary_port: str,
    primary_event: str,
    secondary_port: str,
    secondary_event: str,
    capacity_multiplier: float,
) -> tuple[list[str], dict[str, int]]:
    capacities = {port: int(BASE_CAPACITY * capacity_multiplier) for port in ALL_PORTS}
    closed_ports: list[str] = []

    disruptions = [
        (primary_port.strip().upper(), primary_event.strip().upper()),
        (secondary_port.strip().upper(), secondary_event.strip().upper()),
    ]
    for port, event in disruptions:
        if not port or not event:
            continue
        if port not in ALL_PORTS:
            raise ValueError(f"Unsupported port code in scenario: {port}")
        if event not in DISRUPTION_EVENTS:
            raise ValueError(f"Unsupported disruption event in scenario: {event}")

        if event == EVENT_TOTAL_CLOSURE:
            if port not in closed_ports:
                closed_ports.append(port)
            capacities[port] = 0
            continue
        if event == EVENT_SEVERE_CONGESTION:
            capacities[port] = int(BASE_CAPACITY * 0.2)
            continue
        if event == EVENT_OPERATIONAL_RESTRICTION:
            capacities[port] = int(BASE_CAPACITY * 0.5)

    return closed_ports, capacities


def _set_world_state(
    client: httpx.Client,
    base_url: str,
    closed_ports: list[str],
    capacities: dict[str, int],
) -> None:
    url = f"{base_url}/api/v1/admin/set-state"
    payload = {
        "closed_ports": closed_ports,
        "capacities": capacities,
    }
    response = client.post(url, json=payload, timeout=15.0)
    response.raise_for_status()


def _extract_token_count(final_state: GraphState | dict[str, Any]) -> int:
    total = 0

    def consume_usage(message: AIMessage) -> None:
        nonlocal total
        usage = message.usage_metadata or {}
        if not isinstance(usage, dict):
            return
        if isinstance(usage.get("total_tokens"), int):
            total += int(usage["total_tokens"])
            return
        for value in usage.values():
            if isinstance(value, int):
                total += value

    def visit(value: Any) -> None:
        if isinstance(value, AIMessage):
            consume_usage(value)
            return
        if isinstance(value, dict):
            for nested in value.values():
                visit(nested)
            return
        if isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(final_state)
    return total


def _serialize_final_json(final_state: GraphState | dict[str, Any]) -> str:
    routing = final_state.get("routing_parameters")
    if isinstance(routing, RoutingParameters):
        return json.dumps(routing.model_dump(), sort_keys=True)
    if isinstance(routing, dict):
        return json.dumps(routing, sort_keys=True)
    return "{}"


def _append_result_row(results_path: Path, row: dict[str, Any]) -> None:
    file_exists = results_path.exists()
    with results_path.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=RESULT_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def _format_teu_short(total_teu: int) -> str:
    return f"{round(total_teu / 1000)}k"


def main() -> None:
    _initialize_observability()

    parser = argparse.ArgumentParser(description="Run deterministic IDWL batch experiments.")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for trial runs.")
    parser.add_argument(
        "--run-ids",
        type=str,
        default=None,
        help="Comma-separated run_ids to execute (e.g. 007,020,041).",
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[1]
    data_dir = root_dir / "data"
    scenarios_path = data_dir / "scenarios_idwl_v1.csv"
    results_path = data_dir / "results_idwl_v1.csv"

    if not scenarios_path.exists():
        raise FileNotFoundError(
            f"Missing scenarios file at {scenarios_path}. Run scripts/generate_dataset.py first."
        )

    scenarios = _load_scenarios(scenarios_path)
    if args.run_ids is not None:
        if args.limit is not None:
            raise ValueError("--limit and --run-ids are mutually exclusive")
        selected_run_ids = _parse_run_ids_argument(args.run_ids)
        scenarios = _filter_scenarios_by_run_ids(scenarios, selected_run_ids)

    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")
        scenarios = scenarios[: min(args.limit, len(scenarios))]

    if not scenarios:
        print("No scenarios found to execute.")
        return

    data_dir.mkdir(parents=True, exist_ok=True)

    sandbox_api_url = os.getenv("SANDBOX_API_URL", "http://localhost:8001").rstrip("/")

    with httpx.Client() as client:
        total_runs = len(scenarios)
        for index, scenario in enumerate(scenarios, start=1):
            run_id = str(scenario["run_id"]).zfill(3)
            total_teu = int(scenario["total_teu"])
            primary_port = str(scenario["primary_port"])
            primary_event = str(scenario["primary_event"])
            secondary_port = str(scenario.get("secondary_port", ""))
            secondary_event = str(scenario.get("secondary_event", ""))
            capacity_multiplier = float(scenario["capacity_multiplier"])
            alert_text = str(scenario["alert_text"])

            closed_ports, capacities = _compute_world_state(
                primary_port=primary_port,
                primary_event=primary_event,
                secondary_port=secondary_port,
                secondary_event=secondary_event,
                capacity_multiplier=capacity_multiplier,
            )
            _set_world_state(
                client=client,
                base_url=sandbox_api_url,
                closed_ports=closed_ports,
                capacities=capacities,
            )

            initial_state: GraphState = {
                "alert_text": alert_text,
                "routing_parameters": None,
                "solver_result": None,
                "solver_error_logs": [],
                "revisions_count": 0,
                "port_capacities": {},
                "agent_id": "scm-sandwich-experiment-v1",
            }
            config = {
                "recursion_limit": 10,
                "configurable": {"thread_id": f"idwl_exp_v1_run_{run_id}"},
            }

            started_at = time.perf_counter()
            status = "ERROR"
            revisions = 0
            token_count = 0
            final_json = "{}"
            running_state: GraphState | dict[str, Any] = dict(initial_state)

            try:
                final_state = _stream_graph_with_retry(
                    initial_state=initial_state,
                    config=config,
                    run_id=run_id,
                )
                running_state = final_state
                status = _derive_final_status(final_state)
                revisions = int(final_state.get("revisions_count", 0))
                token_count = _extract_token_count(final_state)
                final_json = _serialize_final_json(final_state)
            except GraphRecursionError as exc:
                recovered_state = _recover_state_from_exception(exc, running_state)
                revisions = int(recovered_state.get("revisions_count", 0))
                token_count = _extract_token_count(recovered_state)
                status = "ERROR_RECURSION"
                final_json = _serialize_error_json(
                    exc=exc,
                    state=recovered_state,
                    error_type="ERROR_RECURSION",
                )
            except Exception as exc:
                recovered_state = _recover_state_from_exception(exc, running_state)
                revisions = int(recovered_state.get("revisions_count", 0))
                token_count = _extract_token_count(recovered_state)
                status = "ERROR"
                final_json = _serialize_error_json(
                    exc=exc,
                    state=recovered_state,
                    error_type="ERROR",
                )

            elapsed = time.perf_counter() - started_at
            result_row = {
                "run_id": run_id,
                "primary_event": primary_event,
                "secondary_event": secondary_event,
                "final_status": status,
                "revisions_count": revisions,
                "total_time_sec": f"{elapsed:.4f}",
                "llm_token_count": token_count,
                "final_json": final_json,
            }
            _append_result_row(results_path=results_path, row=result_row)

            print(
                f"[RUN {index:03d}/{total_runs:03d}] {primary_port} {primary_event} | "
                f"{_format_teu_short(total_teu)} TEU | Time: {elapsed:.1f}s | "
                f"Result: {status} | Revisions: {revisions}"
            )

            if index < total_runs:
                time.sleep(2)


if __name__ == "__main__":
    main()
