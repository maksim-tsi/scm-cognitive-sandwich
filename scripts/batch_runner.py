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
def _invoke_graph_with_retry(initial_state: GraphState, config: dict[str, Any]) -> GraphState:
    try:
        return _get_graph().invoke(initial_state, config=config)
    except Exception as exc:
        if _is_retriable_error(exc):
            raise RetriableGraphInvokeError(str(exc)) from exc
        raise


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
    parser = argparse.ArgumentParser(description="Run deterministic IDWL batch experiments.")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for trial runs.")
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
            status = "INFEASIBLE"
            revisions = 0
            token_count = 0
            final_json = "{}"

            try:
                final_state = _invoke_graph_with_retry(initial_state=initial_state, config=config)
                solver_result = final_state.get("solver_result")
                if isinstance(solver_result, SolverResult) and solver_result.status.upper() == "FEASIBLE":
                    status = "FEASIBLE"
                revisions = int(final_state.get("revisions_count", 0))
                token_count = _extract_token_count(final_state)
                final_json = _serialize_final_json(final_state)
            except Exception as exc:
                final_json = json.dumps({"error": str(exc)})

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
