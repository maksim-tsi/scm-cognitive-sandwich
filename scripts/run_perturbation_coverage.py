import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv

# Ensure src directory is importable when executing from workspace root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)

from agents.state import PortAllocation, RoutingParameters  # noqa: E402
from batch_runner import _compute_world_state, _set_world_state  # noqa: E402

DEFAULT_RUN_IDS = "038,039,096,083,065,026,036,008"


def _normalize_run_id(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("run_id values must not be empty")
    if not candidate.isdigit():
        raise ValueError(f"run_id must be numeric, got: {value}")
    return candidate.zfill(3)


def _parse_run_ids_argument(raw_run_ids: str) -> list[str]:
    parsed = [_normalize_run_id(part) for part in raw_run_ids.split(",")]
    if not parsed:
        raise ValueError("--run-ids must contain at least one run id")
    return parsed


def _load_scenarios_by_run_id(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {str(row["run_id"]).zfill(3): row for row in rows}


def _build_forced_infeasible_params(
    params: RoutingParameters,
    capacities: dict[str, int],
    *,
    violation_teu: int,
) -> tuple[RoutingParameters, dict[str, Any]]:
    allocations = {alloc.port_code: alloc.teu_amount for alloc in params.allocations}
    for port in capacities:
        allocations.setdefault(port, 0)

    # Force the lowest-headroom port over capacity to guarantee infeasibility.
    headroom = {port: capacities.get(port, 0) - allocations.get(port, 0) for port in allocations}
    target_port = min(headroom, key=lambda port: headroom[port])

    target_current = allocations.get(target_port, 0)
    target_capacity = capacities.get(target_port, 0)
    min_increase_to_violate = max(1, target_capacity - target_current + 1)
    increase_needed = max(violation_teu, min_increase_to_violate)

    donor_candidates = sorted(
        [(port, teu) for port, teu in allocations.items() if port != target_port and teu > 0],
        key=lambda item: item[1],
        reverse=True,
    )
    available_to_move = sum(teu for _, teu in donor_candidates)
    if available_to_move < increase_needed:
        raise ValueError(
            "Cannot build perturbation: "
            f"need {increase_needed} TEU to move into {target_port}, have {available_to_move}."
        )

    updated_allocations = dict(allocations)
    remaining = increase_needed
    donor_moves: list[tuple[str, int]] = []
    for donor_port, donor_teu in donor_candidates:
        if remaining <= 0:
            break
        move_amount = min(donor_teu, remaining)
        updated_allocations[donor_port] -= move_amount
        remaining -= move_amount
        donor_moves.append((donor_port, move_amount))

    updated_allocations[target_port] = updated_allocations.get(target_port, 0) + increase_needed

    perturbed_allocations = [
        PortAllocation(port_code=port, teu_amount=teu)
        for port, teu in updated_allocations.items()
        if teu > 0
    ]
    perturbed_params = RoutingParameters(
        original_destination=params.original_destination,
        total_teu_to_reroute=params.total_teu_to_reroute,
        allocations=perturbed_allocations,
    )

    perturbation_meta = {
        "target_port": target_port,
        "target_capacity": target_capacity,
        "target_before": target_current,
        "target_after": updated_allocations.get(target_port, 0),
        "violation_teu": max(0, updated_allocations.get(target_port, 0) - target_capacity),
        "donors": donor_moves,
    }
    return perturbed_params, perturbation_meta


def run_perturbation_coverage(
    *,
    run_ids: list[str],
    scenarios_path: Path,
    sandbox_api_url: str,
    violation_teu: int,
) -> dict[str, Any]:
    if violation_teu <= 0:
        raise ValueError("--violation-teu must be greater than 0")

    scenarios = _load_scenarios_by_run_id(scenarios_path)
    missing = [run_id for run_id in run_ids if run_id not in scenarios]
    if missing:
        raise ValueError(f"run_ids not found in scenarios dataset: {missing}")

    from agents.graph import (  # noqa: WPS433
        node_draft_artifact,
        node_ingest_alert,
        node_repair_artifact,
        node_run_solver,
    )

    details: list[dict[str, Any]] = []
    with httpx.Client() as client:
        for run_id in run_ids:
            scenario = scenarios[run_id]
            primary_port = str(scenario["primary_port"])
            primary_event = str(scenario["primary_event"])
            secondary_port = str(scenario.get("secondary_port", ""))
            secondary_event = str(scenario.get("secondary_event", ""))
            capacity_multiplier = float(scenario["capacity_multiplier"])
            alert_text = str(scenario["alert_text"])

            row_result: dict[str, Any] = {
                "run_id": run_id,
                "primary_event": primary_event,
                "secondary_event": secondary_event,
            }

            try:
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

                state: dict[str, Any] = {
                    "alert_text": alert_text,
                    "routing_parameters": None,
                    "solver_result": None,
                    "solver_error_logs": [],
                    "revisions_count": 0,
                    "port_capacities": {},
                    "agent_id": "scm-sandwich-experiment-v1",
                }

                state.update(node_ingest_alert(state))
                state.update(node_draft_artifact(state))

                initial_params = state["routing_parameters"]
                perturbed_params, perturbation = _build_forced_infeasible_params(
                    initial_params,
                    state["port_capacities"],
                    violation_teu=violation_teu,
                )
                state["routing_parameters"] = perturbed_params

                first_solver_update = node_run_solver(state)
                state.update(first_solver_update)

                repair_update = node_repair_artifact(state)
                state.update(repair_update)

                second_solver_update = node_run_solver(state)
                state.update(second_solver_update)

                row_result.update(
                    {
                        "closed_ports": closed_ports,
                        "status_after_perturbation": first_solver_update["solver_result"].status,
                        "status_after_one_repair": second_solver_update["solver_result"].status,
                        "revisions_count_after_repair": int(state.get("revisions_count", 0)),
                        "perturbation": perturbation,
                    }
                )
            except Exception as exc:
                row_result.update(
                    {
                        "status_after_perturbation": "ERROR",
                        "status_after_one_repair": "ERROR",
                        "revisions_count_after_repair": int(row_result.get("revisions_count_after_repair", 0)),
                        "error": str(exc),
                    }
                )

            details.append(row_result)

    summary = {
        "run_ids": run_ids,
        "total_runs": len(details),
        "induced_infeasible_count": sum(
            row.get("status_after_perturbation") == "INFEASIBLE" for row in details
        ),
        "one_pass_feasible_count": sum(
            row.get("status_after_one_repair") == "FEASIBLE" for row in details
        ),
        "one_pass_infeasible_count": sum(
            row.get("status_after_one_repair") == "INFEASIBLE" for row in details
        ),
        "one_pass_other_count": sum(
            row.get("status_after_one_repair") not in {"FEASIBLE", "INFEASIBLE", "ERROR"}
            for row in details
        ),
        "error_count": sum(
            row.get("status_after_one_repair") == "ERROR" for row in details
        ),
        "revisions_distribution": {
            str(revisions): sum(
                row.get("revisions_count_after_repair") == revisions for row in details
            )
            for revisions in sorted(
                {int(row.get("revisions_count_after_repair", 0)) for row in details}
            )
        },
    }

    return {"summary": summary, "details": details}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run controlled perturbation coverage to verify that one repair pass "
            "converges to FEASIBLE after induced infeasibility."
        )
    )
    parser.add_argument(
        "--run-ids",
        type=str,
        default=DEFAULT_RUN_IDS,
        help=(
            "Comma-separated run IDs to evaluate. "
            f"Default: {DEFAULT_RUN_IDS}"
        ),
    )
    parser.add_argument(
        "--scenarios-path",
        type=Path,
        default=Path("data/scenarios_idwl_v1.csv"),
        help="Path to scenarios CSV file.",
    )
    parser.add_argument(
        "--sandbox-api-url",
        type=str,
        default=os.getenv("SANDBOX_API_URL", "http://localhost:8001"),
        help="Sandbox API base URL.",
    )
    parser.add_argument(
        "--violation-teu",
        type=int,
        default=1,
        help="Minimum TEU moved into a target port beyond capacity to induce infeasibility.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write full JSON output.",
    )
    args = parser.parse_args()

    run_ids = _parse_run_ids_argument(args.run_ids)
    result = run_perturbation_coverage(
        run_ids=run_ids,
        scenarios_path=args.scenarios_path,
        sandbox_api_url=args.sandbox_api_url.rstrip("/"),
        violation_teu=args.violation_teu,
    )

    print("=== SUMMARY ===")
    print(json.dumps(result["summary"], indent=2))
    print("=== DETAILS ===")
    for row in result["details"]:
        compact = {
            "run_id": row["run_id"],
            "after_perturbation": row.get("status_after_perturbation"),
            "after_one_repair": row.get("status_after_one_repair"),
            "rev": row.get("revisions_count_after_repair"),
            "target_port": (row.get("perturbation") or {}).get("target_port"),
            "violation_teu": (row.get("perturbation") or {}).get("violation_teu"),
            "error": row.get("error"),
        }
        print(json.dumps(compact, ensure_ascii=True))

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
