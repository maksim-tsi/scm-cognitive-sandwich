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


def test_compute_world_state_applies_base_multiplier_and_disruptions():
    module = _load_script_module("batch_runner.py")

    closed_ports, capacities = module._compute_world_state(
        primary_port="NLRTM",
        primary_event="SEVERE_CONGESTION",
        secondary_port="DEHAM",
        secondary_event="OPERATIONAL_RESTRICTION",
        capacity_multiplier=0.5,
    )

    assert closed_ports == []
    assert capacities["NLRTM"] == 3000
    assert capacities["DEHAM"] == 7500
    assert capacities["BEANR"] == 7500
    assert capacities["DEBRV"] == 7500


def test_compute_world_state_collects_closed_ports_for_total_closure():
    module = _load_script_module("batch_runner.py")

    closed_ports, capacities = module._compute_world_state(
        primary_port="DEBRV",
        primary_event="TOTAL_CLOSURE",
        secondary_port="",
        secondary_event="",
        capacity_multiplier=0.8,
    )

    assert closed_ports == ["DEBRV"]
    assert capacities == {
        "NLRTM": 12000,
        "BEANR": 12000,
        "DEHAM": 12000,
        "DEBRV": 0,
    }


def test_is_retriable_error_detects_transport_and_429():
    module = _load_script_module("batch_runner.py")

    transport_error = httpx.ConnectError("boom")
    assert module._is_retriable_error(transport_error) is True

    request = httpx.Request("POST", "http://localhost")
    response = httpx.Response(429, request=request)
    status_error = httpx.HTTPStatusError("rate limited", request=request, response=response)
    assert module._is_retriable_error(status_error) is True


def test_schema_columns_match_new_pipeline_contract():
    module = _load_script_module("batch_runner.py")

    assert module.SCENARIO_COLUMNS == [
        "run_id",
        "total_teu",
        "primary_port",
        "primary_event",
        "secondary_port",
        "secondary_event",
        "capacity_multiplier",
        "alert_text",
    ]
    assert module.RESULT_COLUMNS == [
        "run_id",
        "primary_event",
        "secondary_event",
        "final_status",
        "revisions_count",
        "total_time_sec",
        "llm_token_count",
        "final_json",
    ]


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


def test_serialize_final_json_handles_routing_parameters_model():
    module = _load_script_module("batch_runner.py")

    routing = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=10000,
        allocations=[PortAllocation(port_code="NLRTM", teu_amount=10000)],
    )

    result = module._serialize_final_json({"routing_parameters": routing})

    assert '"original_destination": "DEHAM"' in result
    assert '"total_teu_to_reroute": 10000' in result
