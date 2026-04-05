import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Ensure src directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# Load .env before imports that read env vars.
_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


def _load_incident_trigger(path: Path):
    from agents.variant_b.state import IncidentTrigger  # noqa: WPS433

    payload = json.loads(path.read_text(encoding="utf-8"))
    return IncidentTrigger.model_validate(payload)


def main() -> None:
    from agents.variant_b import get_variant_b_graph  # noqa: WPS433
    from agents.variant_b.state import VariantBState  # noqa: WPS433
    from core.env_guard import assert_no_localhost_services  # noqa: WPS433
    from core.observability import setup_observability  # noqa: WPS433

    parser = argparse.ArgumentParser(description="Run the Variant B (stubbed) plan-and-execute graph.")
    parser.add_argument("--incident-json", required=True, help="Path to IncidentTrigger JSON file.")
    parser.add_argument("--thread-id", default="variant-b-session", help="LangGraph thread id.")
    parser.add_argument("--run-id", default=None, help="Optional run id override.")
    args = parser.parse_args()

    assert_no_localhost_services()
    setup_observability()

    incident_path = Path(args.incident_json)
    incident = _load_incident_trigger(incident_path)
    run_id = args.run_id or incident.incident_id

    initial_state: VariantBState = {
        "incident": incident,
        "run_id": run_id,
        "retry_count": 0,
        "incident_context": {},
        "scenarios": [],
        "judge_verdict": None,
        "judge_feedback": [],
        "sandbox_results": [],
        "final_report_md": None,
        "fatal_status": None,
        "agent_id": os.getenv("AGENT_ID", "scm-sandwich-variantb-v1"),
    }

    config = {
        "recursion_limit": 50,
        "configurable": {"thread_id": args.thread_id},
    }

    graph = get_variant_b_graph()

    print("--- Starting Variant B Execution (stubbed) ---")
    print(f"run_id={run_id} thread_id={args.thread_id}")

    last_retry = initial_state["retry_count"]
    fatal_status: str | None = None

    for output in graph.stream(initial_state, config=config, stream_mode="updates"):
        for node_name, state_update in output.items():
            print(f"[NODE COMPLETED] {node_name}")
            if not isinstance(state_update, dict):
                continue

            if isinstance(state_update.get("retry_count"), int) and state_update["retry_count"] != last_retry:
                last_retry = state_update["retry_count"]
                print(f"  retry_count={last_retry}")

            if isinstance(state_update.get("fatal_status"), str):
                fatal_status = state_update["fatal_status"]
                print(f"  fatal_status={fatal_status}")

    print("--- Execution Finished ---")
    if fatal_status:
        print(f"FINAL_STATUS={fatal_status}")
    else:
        print("FINAL_STATUS=SUCCESS")


if __name__ == "__main__":
    main()

