import argparse
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Ensure src directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Load .env before any internal imports that read env vars.
_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


def main():
    from core.observability import setup_observability
    from agents.graph import graph
    from agents.state import GraphState, RoutingParameters, SolverResult
    from langgraph.errors import GraphRecursionError

    print("Tracing environment before setup:")
    print(f"  OTEL_RESOURCE_ATTRIBUTES={os.environ.get('OTEL_RESOURCE_ATTRIBUTES')}")
    print(f"  OTEL_SERVICE_NAME={os.environ.get('OTEL_SERVICE_NAME')}")
    print(f"  PHOENIX_PROJECT_NAME={os.environ.get('PHOENIX_PROJECT_NAME')}")
    print(f"  PHOENIX_COLLECTOR_ENDPOINT={os.environ.get('PHOENIX_COLLECTOR_ENDPOINT')}")

    setup_observability()

    parser = argparse.ArgumentParser(description="Run the Baseline Cognitive Sandwich Graph.")
    parser.add_argument(
        "--invoke",
        action="store_true",
        help="Run graph.invoke() instead of graph.stream() (still enforces recursion_limit).",
    )
    parser.add_argument(
        "--thread-id",
        default="baseline-session",
        help="LangGraph thread id used for checkpoint and YAAM session continuity.",
    )
    args = parser.parse_args()

    print("Initializing state and running Baseline Cognitive Sandwich Graph...")

    # Mock alert text for testing
    initial_state: GraphState = {
        "alert_text": "Port of DEHAM is closed. 10000 TEU must be rerouted to NLRTM and BEANR.",
        "routing_parameters": None,
        "solver_result": None,
        "solver_error_logs": [],
        "revisions_count": 0,
        "port_capacities": {}
    }

    try:
        print("\n--- Starting Execution ---")
        graph_config = {
            "recursion_limit": 10,
            "configurable": {"thread_id": args.thread_id},
        }

        latest_parameters: RoutingParameters | None = None
        revisions_count = initial_state["revisions_count"]
        if args.invoke:
            final_state = graph.invoke(initial_state, config=graph_config)
            latest_parameters = final_state.get("routing_parameters")
            revisions_count = final_state.get("revisions_count", revisions_count)
            solver_result = final_state.get("solver_result")
            if isinstance(solver_result, SolverResult):
                print("\n=== Solver Result (final) ===")
                print(f"solver_status={solver_result.status}")
                print("iis_log=")
                print(solver_result.iis_log or "")
        else:
            # Use stream instead of invoke to print each graph step.
            for output in graph.stream(
                initial_state,
                config=graph_config,
                stream_mode="updates",
            ):
                for node_name, state_update in output.items():
                    print(f"\n[NODE COMPLETED] {node_name}")

                    if state_update is None:
                        state_update = {}
                    if not isinstance(state_update, dict):
                        print(f"Unexpected node update type: {type(state_update)}")
                        continue

                    if "revisions_count" in state_update and isinstance(state_update["revisions_count"], int):
                        revisions_count = state_update["revisions_count"]

                    if "port_capacities" in state_update and isinstance(state_update["port_capacities"], dict):
                        print("\n=== Port Capacities (from sandbox) ===")
                        print(state_update["port_capacities"])

                    if "routing_parameters" in state_update and isinstance(
                        state_update["routing_parameters"], RoutingParameters
                    ):
                        latest_parameters = state_update["routing_parameters"]
                        print("\n=== RoutingParameters JSON ===")
                        print(latest_parameters.model_dump_json(indent=2))

                    if "solver_result" in state_update and isinstance(state_update["solver_result"], SolverResult):
                        solver_result = state_update["solver_result"]
                        print("\n=== Solver Result ===")
                        print(f"solver_status={solver_result.status}")
                        print("iis_log=")
                        print(solver_result.iis_log or "")

        print("\n--- Execution Finished ---")
        final_params = latest_parameters
        if final_params:
            print("\n=== Final Feasible Routing JSON ===")
            print(final_params.model_dump_json(indent=2))
            print(f"Total Revisions Required: {revisions_count}")
        else:
            print("Failed to produce a routing output.")
    except GraphRecursionError as e:
        print("\n--- Execution Stopped ---")
        print("Stopped due to recursion_limit=10")
        print(str(e))
    except Exception as e:
        print(f"Error during graph execution: {e}")

if __name__ == "__main__":
    main()
