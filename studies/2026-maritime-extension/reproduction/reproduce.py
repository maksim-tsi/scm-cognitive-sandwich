"""Reproduce retained historical summaries; no provider calls, DES or rescoring."""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def deny_network(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("Network forbidden during historical reproduction")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load(path: str) -> Any:
    return json.loads((ROOT / path).read_text())


def verify_files() -> None:
    for record in load("provenance/package-manifest.json")["files"]:
        p = ROOT / record["path"]
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Public package file identity differs: " + record["path"])
    for manifest in ["provenance/public-export.json", "provenance/historical-additions.json"]:
        for record in load(manifest)["files"]:
            if hashlib.sha256((ROOT / record["path"]).read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("Source-export identity differs")


def run() -> dict:
    if not __debug__:
        raise RuntimeError("Validation requires assertions enabled")
    setattr(socket.socket, "connect", deny_network)
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    verify_files()
    path = ROOT / "code/analysis.py"
    spec = importlib.util.spec_from_file_location("historical_analysis", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [json.loads(s) for s in (ROOT / "evidence/terminals.jsonl").read_text().splitlines()]
    result = module.analyze_rows(rows)
    assert result == load("evidence/analysis.json"), "Original analysis readback differs"
    metrics = load("evidence/accepted-metrics.json")
    for condition, expected in metrics["condition_outcomes"].items():
        observed = [r["conditions"][condition] for r in rows]
        assert sum(r["accepted"] for r in observed) == expected["accepted"]
        assert sum(r["des_admitted"] for r in observed) == expected["des_admitted"]
    des = [json.loads(s) for s in (ROOT / "evidence/des-replications.jsonl").read_text().splitlines()]
    keys = [(r["incident_id"], r["generation_id"], r["condition"], r["variant_id"], r["replication_id"]) for r in des]
    assert len(des) == len(set(keys)) == 15400
    cells = Counter((r["incident_id"], r["condition"], r["variant_id"]) for r in des)
    assert len({r["incident_id"] for r in des}) == 11
    assert len({r["variant_id"] for r in des}) == 7
    assert all(n == 100 for n in cells.values())
    assert all(r["conservation_ok"] and r["event_order_ok"] and r["resource_bounds_ok"] for r in des)
    lookup = {r["unit_id"]: r for r in rows}
    allocations = load("examples/retained-des-allocations.json")
    responses = load("examples/recovered-canonical-responses.json")
    hashes = {r["sha256"] for r in responses}
    assert len(allocations) == 35 and len(responses) == 27
    for record in responses:
        assert hashlib.sha256(canonical(record["canonical_parsed_response"]).encode()).hexdigest() == record["sha256"]
    for record in allocations:
        terminal = lookup[record["unit_id"]]["conditions"][record["condition"]]
        assert terminal["artifact_sha256"] == record["original_parsed_response_sha256"] in hashes
        response = dict(record["stored_DES_projection"])
        response.pop("generation_id")
        if terminal["repair_count"] == 0:
            response["condition"] = "llm_only"
        assert hashlib.sha256(canonical(response).encode()).hexdigest() == terminal["artifact_sha256"]
    design = load("data/phase-a-design-inputs.json")["units"]
    assert len(design) == 180 and len({u["incident_id"] for u in design}) == 60
    assert {u["generation_id"] for u in design} == {1, 2, 3}
    assert all(hashlib.sha256(canonical(u["input"]).encode()).hexdigest() == u["input_payload_sha256"] for u in design)
    return {"analysis_equal": True, "terminal_incidents": 60, "analyzable_clusters": 59,
            "retained_DES_rows": len(des), "DES_rows_reexecuted": 0,
            "allocation_projections_hash_checked": len(allocations), "canonical_responses_hash_checked": len(responses),
            "design_units_not_certified_scientific_population": len(design),
            "executed_input_binding_recovered": False, "network": "disabled", "new_model_calls": 0,
            "analysis": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "analysis"}))


if __name__ == "__main__":
    main()
