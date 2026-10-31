"""Produce transparent mapping from frozen public site mappings; never alter cases."""

import argparse
import csv
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("sites", type=Path)
    p.add_argument("cases", type=Path)
    p.add_argument("inventory", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--assessments", type=Path, required=True)
    p.add_argument("--second-pass", type=Path, required=True)
    a = p.parse_args()
    sites = list(csv.DictReader(a.sites.open()))
    cases = json.loads(a.cases.read_text())
    images = json.loads(a.inventory.read_text())
    assessments = {r["poi_uuid"]: r for r in json.loads(a.assessments.read_text())}
    observations = json.loads(a.second_pass.read_text())
    out = []
    for site in sites:
        mappings = []
        for case in cases:
            for label, poi in case["public"]["site_mapping"].items():
                if poi == site["id"]:
                    node = (
                        ord(label) - ord("A") + 1
                        if len(label) == 1 and "A" <= label <= "Z"
                        else None
                    )
                    orders = [
                        o
                        for o in case["routing"].get("orders", [])
                        if o.get("node") == node
                    ]
                    bindings = (
                        {
                            k: v
                            for k, v in case["public"].get("bindings", {}).items()
                            if len(v.get("path", [])) > 1
                            and v["path"][0] == "orders"
                            and v["path"][1] == node - 1
                        }
                        if node
                        else {}
                    )
                    mappings.append(
                        {
                            "scenario_id": case["id"],
                            "site_label": label,
                            "instruction": case["instruction"],
                            "modeled_orders": orders,
                            "site_order_bindings": bindings,
                            "snapshot_provenance": case["public"].get(
                                "snapshot_provenance"
                            ),
                            "note": "Mapping identifies a modeled site, not proof that its specific route or vehicle is physically accessible.",
                        }
                    )
        assessment = assessments[site["id"]]
        out.append(
            {
                "poi_uuid": site["id"],
                "name": site["name"],
                "category": site["category"],
                "scenarios": mappings,
                "candidate_screenshots": [
                    x["filename"]
                    for x in images
                    if x["candidate_poi_uuid"] == site["id"]
                ],
                "evidence_status": "assistant second pass; no independent expert validation",
                "visual_assessment": assessment["classification"],
                "visual_evidence": assessment["visual_observation"],
                "supporting_screenshots": assessment["supporting_screenshots"],
                "evidence_gaps": assessment["evidence_gaps"],
                "osm_crosscheck_ref": "osm-site-index.json#" + site["id"],
                "direct_visual_observations": [
                    {"filename": r["filename"], "panorama_date": r["panorama_date"], "observation": r["visible_observation"]}
                    for r in observations if r["candidate_poi_uuid"] == site["id"]
                ],
                "scenario_assumption_status": "Scenario orders, bindings and routing are modeled data, not verified real-world delivery access.",
                "potential_enrichment": "Before use as a new premise, verify delivery entrance, route, vehicle dimensions, permissions and handling; specific issue: "
                + assessment["evidence_gaps"],
            }
        )
    a.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
