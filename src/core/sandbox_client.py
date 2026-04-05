from __future__ import annotations

import httpx

from schemas.sandbox import SandboxExecutionOutput, SimulationExecutionRequest


def execute_simulation(
    *,
    base_url: str,
    request: SimulationExecutionRequest,
    timeout_s: float = 30.0,
) -> SandboxExecutionOutput:
    """Execute candidate scenarios in the Maritime Port Sandbox (strict contract).

    Contract source of truth: `src/schemas/sandbox.py`.
    """
    resolved_base_url = base_url.strip().rstrip("/")
    if not resolved_base_url:
        raise ValueError("base_url must be a non-empty URL")

    url = f"{resolved_base_url}/api/v1/simulation/execute"
    payload = request.model_dump()

    with httpx.Client() as client:
        response = client.post(url, json=payload, timeout=timeout_s)
        response.raise_for_status()
        return SandboxExecutionOutput.model_validate(response.json())

