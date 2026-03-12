import sys
import os

# Ensure src directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from core.observability import setup_observability
from agents.graph import graph

def main():
    setup_observability()
    
    print("Initializing state and running Baseline Cognitive Sandwich Graph...")
    
    # Mock alert text for testing
    initial_state = {
        "alert_text": "Port of DEHAM is closed. 10000 TEU must be rerouted to NLRTM and BEANR.",
        "routing_parameters": None,
        "solver_result": None,
        "revisions_count": 0,
        "port_capacities": {}
    }
    
    try:
        result = graph.invoke(initial_state)
        
        final_params = result.get("routing_parameters")
        if final_params:
            print("\n=== Final Feasible Routing JSON ===")
            print(final_params.model_dump_json(indent=2))
            print(f"Total Revisions Required: {result.get('revisions_count', 0)}")
        else:
            print("Failed to produce a routing output.")
    except Exception as e:
        print(f"Error during graph execution: {e}")

if __name__ == "__main__":
    main()
