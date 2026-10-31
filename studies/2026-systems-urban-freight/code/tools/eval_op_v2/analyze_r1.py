"""Prespecified matched-pair analysis of recorded outcomes, without inference."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from stage2.core.evaluator import evaluate as check_route
from tools.eval_op_v2.ablation import PAIR_IDS, build, build_schedule
from tools.p4_world.world import canonical
from tools.p5_interactive.operational_reference import (
    derive_reference,
    reference_instance,
)

MODEL_ROUTES = ("qwen", "deepseek", "mistral", "openai")
ROUTES = (*MODEL_ROUTES, "dint")
MODEL_FAILURES = {
    "invalid_model_event",
    "model_output_failure",
    "malformed_json",
    "duplicate_keys",
}


def observed_score(row: dict[str, Any] | None):
    if not row:
        return None
    if row["status"] == "completed":
        value = row.get("evaluation", {}).get("independent_outcome_correct")
        if type(value) is not bool:
            raise ValueError("Completed result missing independent outcome")
        return int(value)
    if row["status"] in {"invalid_model_event", "model_output_failure"}:
        return 0
    if row["status"] in MODEL_FAILURES and row.get("model_failure_confirmed") is True:
        return 0
    return None


def provenance_flags(row: dict[str, Any], world: dict[str, Any]):
    flags = set()
    catalog = {r["id"]: r for r in world["records"]}
    ref = derive_reference(world)
    for source_id in (row.get("decision") or {}).get("evidence", []):
        record = catalog.get(source_id)
        if record is None:
            flags.add("unknown_or_nonliteral_id")
            continue
        binding = world["public"]["bindings"][record["slot"]]
        if (
            record["owner"] != binding["owner"]
            or record.get("issuer_role") not in binding["permitted_issuer_roles"]
            or not record["verified"]
            or record["authority"] != "confirmed"
            or record["assertion_kind"] != binding["required_assertion_kind"]
        ):
            flags.add("authority")
        if (
            record["scope"] != world["public"]["scope"]
            or record["entity"] != world["public"]["entity"]
        ):
            flags.add("scope_or_entity")
        if (
            record["available_at"] > world["epoch"]
            or not record["effective_from"]
            <= world["effective_time"]
            < record["effective_to"]
        ):
            flags.add("temporal")
        if record["precision"] != "confirmed":
            flags.add("approximate")
        if any(
            source_id in catalog[active]["supersedes"] for active in ref["source_ids"]
        ):
            flags.add("superseded")
    return flags


def components(rows: list[dict[str, Any]], worlds: dict[str, dict[str, Any]]):
    terminal = [r for r in rows if r.get("status") == "completed"]
    for row in terminal:
        replay = row.get("replay")
        if (
            not replay
            or replay["I2"]["proposal_sha256"] != replay["I3"]["proposal_sha256"]
            or replay["I2"]["proposal_sha256"]
            != hashlib.sha256(canonical(row.get("decision")).encode()).hexdigest()
        ):
            raise ValueError("I2 and I3 do not identify the same original proposal")
    numeric = [
        r
        for r in terminal
        if (r.get("decision") or {}).get("action") in ("UPDATE", "RETAIN", "INFEASIBLE")
    ]
    unsupported = [
        r for r in numeric if r.get("evaluation", {}).get("evidence_grounding") is False
    ]
    reference_checked = []
    for row in numeric:
        decision = row["decision"]
        ref = derive_reference(worlds[row["assignment_id"]])
        if ref["outcome"] != "INSUFFICIENT" and decision.get("plan"):
            try:
                valid = check_route(
                    reference_instance(worlds[row["assignment_id"]], ref["parameters"]),
                    decision["plan"],
                )["valid"]
            except (ValueError, TypeError, KeyError, IndexError):
                valid = False
            reference_checked.append(valid)
    return {
        "terminal_denominator": len(terminal),
        "numeric_denominator": len(numeric),
        "citation_diagnostic_denominator": len(terminal),
        "citation_provenance_flags": {
            flag: sum(
                flag in provenance_flags(r, worlds[r["assignment_id"]])
                for r in terminal
            )
            for flag in (
                "unknown_or_nonliteral_id",
                "authority",
                "scope_or_entity",
                "temporal",
                "approximate",
                "superseded",
            )
        },
        "unsupported_numeric_commitments": len(unsupported),
        "numeric_grounding_unknown": sum(
            r.get("evaluation", {}).get("evidence_grounding") is None for r in numeric
        ),
        "unsupported_admitted_i2": sum(
            bool(r["replay"]["I2"]["admitted"]) for r in unsupported
        ),
        "unsupported_admitted_i3": sum(
            bool(r["replay"]["I3"]["admitted"]) for r in unsupported
        ),
        "reference_physical_checked": len(reference_checked),
        "reference_physical_errors": sum(not v for v in reference_checked),
        "submitted_parameter_feasibility_errors": sum(
            r.get("evaluation", {}).get("feasibility") is False for r in numeric
        ),
        "numeric_semantic_transition_errors": sum(
            r.get("evaluation", {}).get("action_correctness") is False for r in numeric
        ),
        "appropriate_insufficiency": sum(
            bool(r.get("evaluation", {}).get("correct_justified_refusal"))
            for r in terminal
        ),
        "evaluator_unnecessary_refusals_feasible_only": sum(
            bool(r.get("evaluation", {}).get("unnecessary_refusal")) for r in terminal
        ),
        "unnecessary_insufficient_full_reference": sum(
            (r.get("decision") or {}).get("action") == "INSUFFICIENT"
            and derive_reference(worlds[r["assignment_id"]])["outcome"]
            in ("FEASIBLE_PLAN", "INFEASIBLE")
            for r in terminal
        ),
        "deferred_clarifications": sum(
            bool(r.get("evaluation", {}).get("deferred_clarify")) for r in terminal
        ),
        "useful_i2": sum(
            bool(r.get("evaluation", {}).get("useful_I2")) for r in terminal
        ),
        "useful_i3": sum(
            bool(r.get("evaluation", {}).get("useful_I3")) for r in terminal
        ),
        "additional_i3_rejections": sum(
            bool(r["replay"]["I2"]["admitted"]) and not r["replay"]["I3"]["admitted"]
            for r in terminal
        ),
        "correct_i3_rejections": sum(
            bool(r.get("evaluation", {}).get("independent_outcome_correct"))
            and bool(r["replay"]["I2"]["admitted"])
            and not r["replay"]["I3"]["admitted"]
            for r in terminal
        ),
    }


def analyze(
    results: list[dict[str, Any]], journal_totals: dict[str, Any] | None = None
):
    assignments = build()
    lookup = {a["assignment_id"]: a for a in assignments}
    schedule = build_schedule(assignments)
    valid = {(r["route"], r["assignment_id"]) for r in schedule}
    index = {(r["route"], r["assignment_id"]): r for r in results}
    if len(index) != len(results) or not set(index) <= valid:
        raise ValueError("Duplicate or unknown route/assignment")
    for row in results:
        a = lookup[row["assignment_id"]]
        if (
            row.get("case_id") != a["case_id"]
            or row.get("ablation_condition") != a["condition"]
        ):
            raise ValueError("Assignment metadata mismatch")
    worlds = {a["assignment_id"]: a["definition"] for a in assignments}
    summaries = {}
    for route in ROUTES:
        pairs = []
        for case in PAIR_IDS:
            c = index.get((route, case + "-C"))
            e = index.get((route, case + "-E"))
            a, b = observed_score(c), observed_score(e)
            pairs.append(
                {
                    "case_id": case,
                    "control_status": c.get("status") if c else "missing_record",
                    "enriched_status": e.get("status") if e else "missing_record",
                    "control_missing_reason": c.get("reason")
                    if c
                    else "missing_record",
                    "enriched_missing_reason": e.get("reason")
                    if e
                    else "missing_record",
                    "control": a,
                    "enriched": b,
                    "difference": None if a is None or b is None else b - a,
                }
            )
        complete = [p["difference"] for p in pairs if p["difference"] is not None]
        lower = sum(
            (p["enriched"] if p["enriched"] is not None else 0)
            - (p["control"] if p["control"] is not None else 1)
            for p in pairs
        ) / len(pairs)
        upper = sum(
            (p["enriched"] if p["enriched"] is not None else 1)
            - (p["control"] if p["control"] is not None else 0)
            for p in pairs
        ) / len(pairs)
        standalone = [
            observed_score(index.get((route, f"OPV2-{i:02}-E"))) for i in range(1, 17)
        ]
        paired_rows = [
            r for r in results if r["route"] == route and r["case_id"] in PAIR_IDS
        ]
        standalone_rows = [
            r
            for r in results
            if r["route"] == route and r["ablation_condition"] == "enriched"
        ]
        journal = (journal_totals or {}).get(
            route,
            {
                "reservation_count": None,
                "reserved_usd": None,
                "dispatch_intents": None,
                "unfinished": None,
                "status": "unavailable",
            },
        )

        summaries[route] = {
            "pairs": pairs,
            "complete_pairs": len(complete),
            "pair_denominator": len(pairs),
            "paired_complete_mean": sum(complete) / len(complete) if complete else None,
            "finite_assignment_lower_bound": lower,
            "finite_assignment_upper_bound": upper,
            "paired_components_by_condition": {
                c: components(
                    [r for r in paired_rows if r["ablation_condition"] == c], worlds
                )
                for c in ("control", "enriched")
            },
            "standalone_enriched_components": components(standalone_rows, worlds),
            "standalone_observed": sum(v is not None for v in standalone),
            "standalone_correct": sum(v or 0 for v in standalone),
            "standalone_assigned": 16,
            "durable_journal": journal,
            "deterministic_model_api_generations": 0 if route == "dint" else None,
        }
    return {
        "primary": "per-provider mean paired enriched-minus-control correctness, six fixed pairs; missing values bounded",
        "providers": summaries,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    data = json.loads(a.results.read_text())
    from tools.eval_op_v2.collection_r1 import read_journal_counts

    totals = {route: read_journal_counts(a.results.parent / route) for route in ROUTES}
    if data.get("journal_totals") and data["journal_totals"] != totals:
        raise ValueError("Persisted totals differ from durable journal readback")
    a.output.write_text(json.dumps(analyze(data["results"], totals), indent=2) + "\n")


if __name__ == "__main__":
    main()
