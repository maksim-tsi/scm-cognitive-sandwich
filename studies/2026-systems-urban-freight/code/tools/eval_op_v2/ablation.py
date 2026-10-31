"""Construct revision 1: 16 enriched worlds plus six paired controls, no inference."""

from __future__ import annotations
import copy
import csv
import hashlib
import json
from pathlib import Path
from tools.p4_world.world import canonical
from tools.p5_interactive.operational import public_messages
from tools.p5_interactive.operational_reference import derive_reference

ROOT = Path(__file__).resolve().parents[2].parent / "data"
OUT = ROOT / "research/eval-op-v2/revision-1"
PAIR_IDS = ("OPV2-01", "OPV2-02", "OPV2-03", "OPV2-04", "OPV2-08", "OPV2-13")
CONTROL_FIRST = frozenset(("OPV2-01", "OPV2-03", "OPV2-13"))


def build():
    originals = json.loads((ROOT / "research/eval-op-v2/scenarios.json").read_text())
    names = {
        r["id"]: r["name"]
        for r in csv.DictReader(
            (ROOT / "evidence/stage1/geography/selected-sites.csv").open()
        )
    }
    ledger = json.loads(
        (ROOT / "research/streetview/second-pass-observations.json").read_text()
    )
    assignments = []
    for original in originals:
        world = copy.deepcopy(original)
        world["public"].pop("site_evidence_note")
        world["public"]["evidence_boundary"] = (
            "Historical views, if provided, show only described features; customer access alone does not establish freight access, and a visible curb alone does not establish loading permission. Current identity and real legal access remain unknown; synthetic scenario premises are not verified site facts."
        )
        world["public"]["site_names"] = {
            k: {
                "register_label": names[v],
                "identity_status": "historical register label; current identity unverified",
            }
            for k, v in world["public"]["site_mapping"].items()
            if k != "DEPOT"
        }
        # Hypothetical common assumption, not identification of an actual gate or road.
        world["public"]["synthetic_access_scope"] = (
            "For this hypothetical instance the booked route and vehicle access are stipulated as scenario inputs, not verified site facts; customer parking access is outside the modeled freight route."
        )
        if world["id"] == "OPV2-02":
            site = next(x for x in world["public"]["site_evidence"] if x["site"] == "A")
            r = next(x for x in ledger if x["filename"].endswith("20.38.13.png"))
            assert r["candidate_poi_uuid"] == site["poi_uuid"]
            site.update(
                source_file=r["filename"],
                source_sha256=r["sha256"],
                panorama_date=r["panorama_date"],
                observation=r["visible_observation"],
                qualification=site["qualification"]
                + " Function of the opening is unverified.",
            )
        eid = world["id"] + "-E"
        enriched = {
            "assignment_id": eid,
            "case_id": world["id"],
            "condition": "enriched",
            "definition": world,
        }
        if world["id"] not in PAIR_IDS:
            assignments.append(enriched)
            continue
        control_world = copy.deepcopy(world)
        del control_world["public"]["site_evidence"]
        control = {
            "assignment_id": world["id"] + "-C",
            "case_id": world["id"],
            "condition": "control",
            "definition": control_world,
        }
        assignments.extend(
            [control, enriched] if world["id"] in CONTROL_FIRST else [enriched, control]
        )
    return assignments


def validate_pairs(assignments):
    assert (
        len(assignments) == 22 and len({a["assignment_id"] for a in assignments}) == 22
    )
    checks = []
    for pid in PAIR_IDS:
        pair = [a for a in assignments if a["case_id"] == pid]
        assert {a["condition"] for a in pair} == {"control", "enriched"}
        c = next(a["definition"] for a in pair if a["condition"] == "control")
        e = next(a["definition"] for a in pair if a["condition"] == "enriched")
        stripped = copy.deepcopy(e)
        visual = stripped["public"].pop("site_evidence")
        assert visual and stripped == c
        assert derive_reference(c) == derive_reference(e)
        cp = public_messages(c, tools=True, user_answers=True)
        ep = public_messages(e, tools=True, user_answers=True)
        assert cp[0] == ep[0]
        cpacket = json.loads(cp[1]["content"])
        epacket = json.loads(ep[1]["content"])
        assert epacket["public"].pop("site_evidence") == visual and cpacket == epacket
        checks.append(
            {
                "pair_id": pid,
                "control": pid + "-C",
                "enriched": pid + "-E",
                "permitted_world_diff": ["public.site_evidence"],
                "permitted_public_packet_diff": ["public.site_evidence"],
                "reference_sha256": hashlib.sha256(
                    canonical(derive_reference(c)).encode()
                ).hexdigest(),
                "observations": visual,
                "control_first": pid in CONTROL_FIRST,
            }
        )
    return checks


def build_schedule(assignments):
    routes = ("qwen", "deepseek", "mistral", "openai")
    steps = []
    for index in range(16):
        case_id = f"OPV2-{index + 1:02}"
        case = [a for a in assignments if a["case_id"] == case_id]
        for a in case:
            steps.append({"route": "dint", "assignment_id": a["assignment_id"]})
        ordered_routes = routes[index % 4 :] + routes[: index % 4]
        for route in ordered_routes:
            ordered_case = list(case)
            if len(case) == 2 and route in ("mistral", "openai"):
                ordered_case.reverse()
            for a in ordered_case:
                steps.append({"route": route, "assignment_id": a["assignment_id"]})
    return steps


def main():
    assignments = build()
    checks = validate_pairs(assignments)
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, obj in [
        ("assignments.json", assignments),
        ("pairs.json", checks),
        ("schedule.json", build_schedule(assignments)),
    ]:
        (OUT / filename).write_text(
            json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
        )


if __name__ == "__main__":
    main()
