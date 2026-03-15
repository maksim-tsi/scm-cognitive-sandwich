from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

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


def test_parse_run_ids_argument_normalizes_values():
    module = _load_script_module("run_perturbation_coverage.py")

    parsed = module._parse_run_ids_argument("8,026,39")

    assert parsed == ["008", "026", "039"]


def test_build_forced_infeasible_params_preserves_total_and_violates_capacity():
    module = _load_script_module("run_perturbation_coverage.py")

    params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=9000,
        allocations=[
            PortAllocation(port_code="NLRTM", teu_amount=3000),
            PortAllocation(port_code="BEANR", teu_amount=3000),
            PortAllocation(port_code="DEHAM", teu_amount=3000),
        ],
    )
    capacities = {
        "NLRTM": 6000,
        "BEANR": 6000,
        "DEHAM": 6000,
        "DEBRV": 0,
    }

    perturbed, meta = module._build_forced_infeasible_params(
        params,
        capacities,
        violation_teu=1,
    )

    initial_total = sum(alloc.teu_amount for alloc in params.allocations)
    perturbed_total = sum(alloc.teu_amount for alloc in perturbed.allocations)
    perturbed_map = {alloc.port_code: alloc.teu_amount for alloc in perturbed.allocations}

    assert initial_total == perturbed_total == 9000
    assert meta["target_port"] == "DEBRV"
    assert perturbed_map["DEBRV"] > capacities["DEBRV"]
    assert meta["violation_teu"] >= 1


def test_build_forced_infeasible_params_raises_when_no_donor_capacity():
    module = _load_script_module("run_perturbation_coverage.py")

    params = RoutingParameters(
        original_destination="DEHAM",
        total_teu_to_reroute=0,
        allocations=[],
    )
    capacities = {
        "NLRTM": 0,
        "BEANR": 0,
        "DEHAM": 0,
        "DEBRV": 0,
    }

    try:
        module._build_forced_infeasible_params(params, capacities, violation_teu=1)
    except ValueError as exc:
        assert "Cannot build perturbation" in str(exc)
    else:
        raise AssertionError("Expected ValueError when no donor TEU is available")
