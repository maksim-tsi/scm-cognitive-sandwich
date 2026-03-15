from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import httpx
from langchain_core.messages import AIMessage

from agents.state import PortAllocation, RoutingParameters


def _load_script_module(script_name: str) -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / script_name
    spec = spec_from_file_location(script_name.replace(".py", ""), script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module for {script_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compute_capacities_scales_non_closed_ports_and_closes_target_port():
    module = _load_script_module("batch_runner.py")

    baseline = {"NLRTM": 10000, "BEANR": 8000, "DEHAM": 9000, "DEBRV": 7000}
    capacities = module._compute_capacities(
        baseline=baseline,
        closed_port="DEHAM",
        capacity_multiplier=0.5,
    )

    assert capacities["DEHAM"] == 0
    assert capacities["NLRTM"] == 5000
    assert capacities["BEANR"] == 4000
    assert capacities["DEBRV"] == 3500


def test_is_retriable_error_detects_transport_and_429():
    module = _load_script_module("batch_runner.py")

    transport_error = httpx.ConnectError("boom")
    assert module._is_retriable_error(transport_error) is True

    request = httpx.Request("POST", "http://localhost")
    response = httpx.Response(429, request=request)
    status_error = httpx.HTTPStatusError("rate limited", request=request, response=response)
    assert module._is_retriable_error(status_error) is True


def test_extract_token_count_sums_usage_metadata_when_present():
    module = _load_script_module("batch_runner.py")

    messages = [
        AIMessage(
            content="a",
            usage_metadata={"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
        ),
        AIMessage(
            content="b",
            usage_metadata={"input_tokens": 4, "output_tokens": 3, "total_tokens": 7},
        ),
    ]
    state = {"messages": messages}

    assert module._extract_token_count(state) == 16


def test_serialize_final_json_dump_handles_routing_parameters_model():
    module = _load_script_module("batch_runner.py")

    routing = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[PortAllocation(port_code="NLRTM", teu_amount=10000)],
    )

    result = module._serialize_final_json_dump({"routing_parameters": routing})

    assert '"original_destination": "DEHAM"' in result
    assert '"total_teu_to_reroute": 10000' in result
