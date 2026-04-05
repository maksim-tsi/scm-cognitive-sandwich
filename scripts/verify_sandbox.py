import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Ensure src directory is importable when executing from workspace root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


def main() -> int:
    from core.sandbox_client import execute_simulation  # noqa: WPS433
    from schemas.sandbox import CandidateScenario, SimulationExecutionRequest  # noqa: WPS433

    sandbox_url = (os.getenv("SANDBOX_API_URL") or "").strip()
    if not sandbox_url:
        raise ValueError("SANDBOX_API_URL must be set for verify_sandbox.py")

    request = SimulationExecutionRequest(
        run_id="verify-sandbox",
        scenarios=[
            CandidateScenario(
                scenario_id="verify-S1",
                target_ports=["NLRTM", "BEANR", "DEHAM"],
            ),
            CandidateScenario(
                scenario_id="verify-S2",
                target_ports=["BEANR", "NLRTM", "DEBRV"],
            ),
            CandidateScenario(
                scenario_id="verify-S3",
                target_ports=["DEHAM", "NLRTM", "BEANR"],
            ),
        ],
    )

    output = execute_simulation(base_url=sandbox_url, request=request, timeout_s=30.0)
    print(f"SANDBOX OK run_id={output.run_id} scenarios={len(output.simulated_scenarios)}")
    for result in output.simulated_scenarios:
        if result.execution_status == "SUCCESS" and result.metrics is not None:
            print(
                "  "
                f"scenario_id={result.scenario_id} status={result.execution_status} "
                f"time={result.metrics.total_lead_time_hours} "
                f"cost={result.metrics.total_cost_usd} "
                f"risk={result.metrics.bottleneck_severity}"
            )
        else:
            print(f"  scenario_id={result.scenario_id} status={result.execution_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

