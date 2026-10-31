"""Verify public study artifacts, reproduce summaries and replay original I2/I3.

No credentials, model APIs or private source repository are used. Output is new
verification evidence; original decisions and scoring records are never changed.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
import io
import json
import socket
import sys
from pathlib import Path
from typing import Any

if not __debug__:
    raise RuntimeError("Validation requires assertions enabled")

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY / "code"))


def deny_network(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("Network forbidden during offline reproduction")


setattr(socket.socket, "connect", deny_network)
setattr(socket.socket, "connect_ex", deny_network)
socket.create_connection = deny_network
socket.getaddrinfo = deny_network

from tools.p4_world.world import canonical
from stage2.core.evaluator import evaluate as check_route
from stage2.core.solver import infeasibility_certificate
from tools.p5_interactive.operational import (
    OperationalWorld,
    parameters_instance,
    terminal_replay,
)
from tools.p5_interactive.operational_reference import (
    derive_reference,
    evaluate_outcome,
)


def load(path: str) -> Any:
    return json.loads((STUDY / path).read_text())


def replay_packet(world_definition: dict, packet: dict) -> tuple[dict, dict]:
    """Reconstruct original trusted-world events from compact public packets.

    Lookup and dispatcher releases are executed, not filled from private facts.
    A recorded solver witness is checked rather than searched again: the original
    50ms OR-Tools search can select another feasible witness. This does not change
    any gate code or replace the subject's proposal.
    """
    condition = packet.get("environment_condition", packet.get("condition"))
    assert isinstance(condition, dict)
    world = OperationalWorld(world_definition, tools=condition["tools"],
                             user_answers=condition["user_answers"])
    for step in packet["steps"]:
        action, args = step["action"], step["arguments"]
        if action == "ASK_USER":
            result = world.ask_user(args)
        elif action == "FINAL":
            if packet.get("pre_final_gate"):
                early_replay = terminal_replay(world_definition, world, packet["decision"])
            result = world.submit_final(args)
        elif action == "CALL_TOOL":
            tool, arguments = args["tool"], args["arguments"]
            result = step["response"]
            if tool == "plan_route" and result.get("status") == "OK":
                # Mirror the unchanged controller's admitted call transition.
                assert world._turn() is None
                assert world.tools_enabled and world.tool_calls < 3
                assert set(arguments) == {"parameters"}
                world.tool_calls += 1
                instance = parameters_instance(world_definition, arguments["parameters"])
                solution = result["solution"]
                assert check_route(instance, solution) == result["route_check"]
                if solution["status"] == "FEASIBLE":
                    assert result["route_check"]["valid"]
                elif solution["status"] == "INFEASIBLE_CERTIFIED":
                    assert infeasibility_certificate(instance) is not None
                else:
                    assert solution["status"] == "UNKNOWN"
                world._record(action, args, result)
            else:
                result = world.call_tool(tool, arguments)
        else:
            raise ValueError("Unknown recorded action")
        assert result == step["response"], "Released result differs"
        assert (world.questions, world.tool_calls) == (step["questions_used"], step["tools_used"])
    trace = world.export_trace()
    assert hashlib.sha256(trace).hexdigest() == packet["source_trace_sha256"], "Original event identity differs"
    decision = packet.get("decision")
    assert world._events and world._events[-1]["action"] == "FINAL"
    assert world._events[-1]["arguments"] == decision
    replay = early_replay if packet.get("pre_final_gate") else terminal_replay(world_definition, world, decision)
    assert replay == packet["replay"], "I2/I3 replay differs from frozen result"
    evaluation = evaluate_outcome(world_definition, trace, decision, replay, condition=condition)
    assert evaluation == packet["evaluation"], "Original evaluator readback differs"
    return replay, evaluation


def check_manifest() -> int:
    manifest = load("provenance/package-manifest.json")
    for entry in manifest["files"]:
        path = STUDY / entry["path"]
        assert path.is_file() and not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
    sources = load("provenance/source-export.json")["files"]
    assert len({s["path"] for s in sources}) == len(sources)
    for source in sources:
        assert hashlib.sha256((STUDY / source["path"]).read_bytes()).hexdigest() == source["sha256"], source["path"]
    return len(manifest["files"])


def run() -> dict:
    count = check_manifest()
    worlds30 = {w["id"]: w for w in load("data/research/evaluation/scenarios.json")}
    assignments = load("data/research/eval-op-v2/revision-1/assignments.json")
    worlds_r1 = {a["assignment_id"]: a["definition"] for a in assignments}
    from tools.eval_op_v2.ablation import build, validate_pairs
    assert build() == assignments
    from tools.evaluation_cohort.author import build as build_eval30
    from tools.eval_op_v2.author import build as build_precursor
    assert build_eval30() == list(worlds30.values())
    assert build_precursor() == load("data/research/eval-op-v2/scenarios.json")
    freeze = load("provenance/freeze-records.json")["r1"]
    assert hashlib.sha256(canonical(assignments).encode()).hexdigest() == freeze["assignment_canonical_sha256"]
    schedule = load("data/research/eval-op-v2/revision-1/schedule.json")
    assert hashlib.sha256(canonical(schedule).encode()).hexdigest() == freeze["schedule_canonical_sha256"]
    assert len(validate_pairs(assignments)) == 6
    assert [derive_reference(w) for w in worlds30.values()] == load("data/research/evaluation/references.json")
    refs_r1 = load("data/research/eval-op-v2/revision-1/references.json")
    # R1 references are keyed by assignment with independently derived records.
    derived = {a["assignment_id"]: derive_reference(a["definition"]) for a in assignments}
    assert derived == refs_r1
    report: dict[str, Any] = {"network": "disabled", "manifest_files_checked": count, "collections": {}}
    summary_rows = []
    for group, worlds in [("eval30", worlds30), ("luna-eval30", worlds30), ("r1", worlds_r1)]:
        packets = load(f"results/{group}/packets.json")
        assert len({(p["route"], p["assignment_id"]) for p in packets}) == len(packets)
        checked = 0
        for packet in packets:
            if packet["status"] == "completed":
                replay_packet(worlds[packet["assignment_id"]], packet)
                checked += 1
        analysis = load(f"results/{group}/analysis.json")
        if group == "r1":
            from tools.eval_op_v2.analyze_r1 import analyze
            totals = {r: s["durable_journal"] for r, s in analysis["providers"].items()}
            assert analyze(packets, totals) == analysis
            accounting = load("results/r1/accounting.json")
            assert sum(v["reservation_count"] for route, v in totals.items() if route != "dint") == accounting["scientific_requests"] == 150
            assert sum(p["calls"] for p in accounting["providers"]) == 150
            assert all(p["calls"] == totals[p["provider"]]["reservation_count"] for p in accounting["providers"])
            summaries = {r: {"correct": s["standalone_correct"], "denominator": 16,
                        "useful_I2": s["standalone_enriched_components"]["useful_i2"],
                        "useful_I3": s["standalone_enriched_components"]["useful_i3"],
                        "paired_difference": s["paired_complete_mean"]}
                         for r, s in analysis["providers"].items()}
        else:
            assert len(analysis["calls"]) == (185 if group == "eval30" else 48)
            summaries = {}
            for route, s in analysis["summaries"].items():
                rows = [p for p in packets if p["route"] == route]
                assert len(rows) == s["assigned"] == 30
                for key, field in [("correct", "independent_outcome_correct"), ("useful_I2", "useful_I2"), ("useful_I3", "useful_I3")]:
                    assert sum(bool(p.get("evaluation", {}).get(field)) for p in rows) == s[key]
                assert sum(p["status"] == "completed" for p in rows) == s["completed"]
                summaries[route] = {"correct": s["correct"], "denominator": 30,
                                    "useful_I2": s["useful_I2"], "useful_I3": s["useful_I3"]}
        for route, s in summaries.items():
            summary_rows.append({"collection": group, "route": route, **s})
        report["collections"][group] = {"assigned": len(packets), "terminal_replays": checked,
                "nonterminal_statuses": [{"route": p["route"], "assignment": p["assignment_id"], "status": p["status"]}
                                         for p in packets if p["status"] != "completed"], "summaries": summaries}
    report["terminal_replays"] = sum(x["terminal_replays"] for x in report["collections"].values())
    controls = load("results/controlled-diagnostic/packets.json")
    for packet in controls:
        replay_packet(worlds30[packet["assignment_id"]], packet)
    counterexample = next(p for p in controls if p["world"] == "EVAL-19" and p["diagnostic"].startswith("unconsulted_replacement:"))
    assert counterexample["replay"]["I3"]["admitted"] and not counterexample["evaluation"]["independent_outcome_correct"]
    report["separate_scripted_controls_replayed"] = len(controls)
    images = load("data/research/streetview/screenshot-inventory.json")
    second = load("data/research/streetview/second-pass-observations.json")
    sites = load("data/research/streetview/site-assessments.json")
    assert len(images) == len(second) == 41 and len(sites) == 12
    assert {x["filename"]: (x["sha256"], x["panorama_date"], x["candidate_poi_uuid"]) for x in images} == {x["filename"]: (x["sha256"], x["panorama_date"], x["candidate_poi_uuid"]) for x in second}
    counts = dict(Counter(x["classification"] for x in sites))
    assert counts == {"conditionally_plausible": 6, "potentially_constrained": 4, "insufficient_visual_evidence": 2}
    report["visual_metadata"] = {"POIs": 12, "screenshots_not_distributed": 41, "classification_counts": counts}
    report["summary_rows"] = summary_rows
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    table = io.StringIO()
    writer = csv.DictWriter(table, fieldnames=["collection", "route", "correct", "denominator", "useful_I2", "useful_I3", "paired_difference"])
    writer.writeheader()
    writer.writerows(report["summary_rows"])
    (args.output / "results.csv").write_text(table.getvalue())
    print(json.dumps({"terminal_replays": report["terminal_replays"], "collections": len(report["collections"]), "network": "disabled"}))


if __name__ == "__main__":
    main()
