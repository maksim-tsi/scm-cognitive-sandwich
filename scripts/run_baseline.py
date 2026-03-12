import sys
import os

# Ensure src directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from core.observability import setup_observability
from agents.graph import graph
from agents.state import GraphState, RoutingParameters


def main():
    setup_observability()

    print("Initializing state and running Baseline Cognitive Sandwich Graph...")

    # Mock alert text for testing
    initial_state: GraphState = {
        "alert_text": "Port of DEHAM is closed. 10000 TEU must be rerouted to NLRTM and BEANR.",
        "routing_parameters": None,
        "solver_result": None,
        "revisions_count": 0,
        "port_capacities": {}
    }

    try:
        print("\n--- Starting Execution ---")

        # Use stream instead of invoke to print each graph step.
        latest_parameters: RoutingParameters | None = None
        revisions_count = initial_state["revisions_count"]
        for output in graph.stream(initial_state, stream_mode="updates"):
            for node_name, state_update in output.items():
                print(f"\n[NODE COMPLETED] {node_name}")

                if "revisions_count" in state_update and isinstance(state_update["revisions_count"], int):
                    revisions_count = state_update["revisions_count"]

                # If this is a Draft or Repair node, print proposed parameters.
                if "current_parameters" in state_update and state_update["current_parameters"]:
                    if isinstance(state_update["current_parameters"], RoutingParameters):
                        latest_parameters = state_update["current_parameters"]
                    print("  Proposed Allocation:")
                    for alloc in state_update["current_parameters"].allocations:
                        print(f"    - {alloc.port_code}: {alloc.teu_amount} TEU")

                if "routing_parameters" in state_update and isinstance(state_update["routing_parameters"], RoutingParameters):
                    latest_parameters = state_update["routing_parameters"]

                # If this is a Solver node, print solver status and IIS log.
                if "solver_status" in state_update:
                    print(f"  Solver Status: {state_update['solver_status']}")
                    if state_update["solver_status"] == "INFEASIBLE":
                        print(f"  IIS Error: {state_update.get('solver_error_log', 'No log')}")

        print("\n--- Execution Finished ---")
        final_params = latest_parameters
        if final_params:
            print("\n=== Final Feasible Routing JSON ===")
            print(final_params.model_dump_json(indent=2))
            print(f"Total Revisions Required: {revisions_count}")
        else:
            print("Failed to produce a routing output.")
    except Exception as e:
        print(f"Error during graph execution: {e}")

if __name__ == "__main__":
    main()
