"""Prospective R1 collector; no API traffic without a separate explicit live invocation."""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any
from tools.eval_op_v2.ablation import build, build_schedule, validate_pairs
from tools.mistral_pilot.collect import PacedClient
from tools.openai_extension.runtime import ResponsesClient, run_luna_episode
from tools.p4_world.world import canonical
from tools.p5_interactive.experiment import run_episode
from tools.p5_interactive.operational_baseline import OperationalBaseline
from tools.p5_interactive.operational_check import replay_trace
from tools.p5_interactive.operational_reference import evaluate_outcome
from tools.p5_interactive.providers import (
    HttpClient,
    IntegrityError,
    Journal,
    save_json,
)

ROUTES = ("qwen", "deepseek", "mistral", "openai")
MODEL_OUTPUT_ERRORS = {
    ("malformed_json", "invalid_assistant_json"),
    ("duplicate_keys", "duplicate_output_keys"),
}


def stop_for(result, capture):
    status = result["status"]
    if capture and (
        capture.get("http_status") != 200 or capture.get("unknown_completion")
    ):
        return "transport_or_http_failure"
    if status in ("completed", "invalid_model_event", "model_output_failure"):
        return None
    if capture and (status, capture.get("error")) in MODEL_OUTPUT_ERRORS:
        return None
    return status


def verify_capture(
    journal: Journal,
    episode: str,
    result: dict[str, Any],
    world: dict[str, Any],
    *,
    synthetic: bool,
):
    with journal.connect() as db:
        rows = db.execute(
            "SELECT id,status FROM calls WHERE episode=? ORDER BY rowid", (episode,)
        ).fetchall()
    if result.get("status") in (
        "completed",
        "invalid_model_event",
        "model_output_failure",
    ) and not result.get("last_request_id"):
        raise IntegrityError("Terminal result missing last request id")
    if result.get("last_request_id") and (
        not rows or rows[-1][0] != result["last_request_id"]
    ):
        raise IntegrityError("Episode last request differs from durable journal")
    if (
        result.get("status")
        in ("completed", "invalid_model_event", "model_output_failure")
        and not rows
    ):
        raise IntegrityError("Terminal result without durable calls")
    for request_id, status in rows:
        directory = journal.root / request_id
        if status != "processed" or not (directory / "step.json").exists():
            raise IntegrityError("Unfinished capture")
        if not synthetic and not (directory / "dispatch.intent").is_file():
            raise IntegrityError("Missing dispatch marker")
        c = json.loads((directory / "capture.json").read_text())
        for key in ("request", "response"):
            raw = (directory / (key + ".bin")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != c[key + "_sha256"]:
                raise IntegrityError("Capture hash mismatch")
    if result.get("status") == "completed":
        trace = (journal.root / episode / "trace.jsonl").read_bytes()
        replay = replay_trace(world, trace)
        if replay != result.get("replay"):
            raise IntegrityError("Terminal replay differs")
        decision_sha = hashlib.sha256(
            canonical(result["decision"]).encode()
        ).hexdigest()
        if (
            replay["I2"]["proposal_sha256"] != decision_sha
            or replay["I3"]["proposal_sha256"] != decision_sha
        ):
            raise IntegrityError("Gate proposal identity differs from decision")
        evaluated = evaluate_outcome(
            world,
            trace,
            result["decision"],
            replay,
            condition={"tools": True, "user_answers": True},
        )
        if evaluated != result.get("evaluation"):
            raise IntegrityError("Terminal evaluation differs")
    return len(rows)


def read_journal_counts(root: Path):
    try:
        with sqlite3.connect(f"file:{root / 'calls.sqlite'}?mode=ro", uri=True) as db:
            rows = db.execute(
                "SELECT id,status,reservation FROM calls ORDER BY rowid"
            ).fetchall()
        return {
            "reservation_count": len(rows),
            "reserved_usd": sum(reservation for _, _, reservation in rows),
            "dispatch_intents": sum(
                (root / ident / "dispatch.intent").is_file() for ident, _, _ in rows
            ),
            "unfinished": sum(status != "processed" for _, status, _ in rows),
            "status": "available",
        }
    except Exception:
        return {
            "reservation_count": None,
            "reserved_usd": None,
            "dispatch_intents": None,
            "unfinished": None,
            "status": "unavailable",
        }


def journal_counts(journal: Journal):
    return read_journal_counts(journal.root)


def collect(
    assignments: list[dict[str, Any]],
    schedule: list[dict[str, str]],
    clients: dict[str, Any],
    root: Path,
    *,
    expected_sha256: str,
    budgets: dict[str, float],
    max_hours: float,
):
    digest = hashlib.sha256(canonical(assignments).encode()).hexdigest()
    if (
        digest != expected_sha256
        or assignments != build()
        or schedule != build_schedule(assignments)
    ):
        raise ValueError("Approved revision, ordered assignments or schedule differ")
    validate_pairs(assignments)
    if (
        set(clients) != set(ROUTES)
        or set(budgets) != set(ROUTES)
        or budgets["qwen"] != 0
        or any(not 0 < budgets[k] <= 2 for k in ROUTES if k != "qwen")
        or not 0 < max_hours <= 8
    ):
        raise ValueError("Invalid routes, budget or duration")
    root.mkdir(parents=True, exist_ok=False)
    deadline = time.time() + max_hours * 3600
    journals = {r: Journal(root / r, 154, budgets[r]) for r in ROUTES}
    journals["dint"] = Journal(root / "dint", 154, 0)
    for route in ROUTES:
        journals[route].deadline = deadline
        clients[route].deadline = deadline
    clients["mistral"].journal = journals["mistral"]
    clients["mistral"].experimental_profile = "native-structured-no-unique-v1"
    index = {a["assignment_id"]: a for a in assignments}
    results = []
    stop = None
    for step in schedule:
        route = step["route"]
        assignment = index[step["assignment_id"]]
        name = assignment["assignment_id"]
        w = assignment["definition"]
        if stop is None and time.time() >= deadline:
            stop = "wall_clock_limit"
        base = {
            "route": route,
            "assignment_id": name,
            "case_id": assignment["case_id"],
            "ablation_condition": assignment["condition"],
        }
        if stop:
            results.append({**base, "status": "unattempted", "reason": stop})
            continue
        try:
            if route == "dint":
                result = run_episode(
                    w, OperationalBaseline(), journals[route], "qwen", name=name
                )
            elif route == "openai":
                result = run_luna_episode(w, clients[route], journals[route], name=name)
            else:
                result = run_episode(
                    w, clients[route], journals[route], route, name=name
                )
            capture = None
            if result.get("last_request_id"):
                capture = json.loads(
                    (
                        journals[route].root
                        / result["last_request_id"]
                        / "capture.json"
                    ).read_text()
                )
            count = verify_capture(
                journals[route], name, result, w, synthetic=route == "dint"
            )
            stop = stop_for(result, capture)
            with journals[route].connect() as db:
                journal_stop = db.execute(
                    "SELECT stop FROM settings WHERE id=1"
                ).fetchone()[0]
            if journal_stop:
                stop = journal_stop
            result["durable_journal_attempts"] = count if route != "dint" else 0
            result["model_failure_confirmed"] = bool(
                capture
                and (result["status"], capture.get("error")) in MODEL_OUTPUT_ERRORS
            )
        except IntegrityError:
            stop = "integrity_or_unknown_delivery"
            result = {"episode": w["id"], "status": "collection_paused", "reason": stop}
        except Exception:
            journals[route].stop("transport_or_persistence_exception")
            stop = "transport_or_persistence_exception"
            result = {"episode": w["id"], "status": "collection_paused", "reason": stop}
        if "condition" in result:
            result["environment_condition"] = result.pop("condition")
        results.append({**base, **result})
        save_json(
            root / f"progress-{len(results):03}.json",
            {"results": results, "stop": stop},
        )
    final = {
        "revision": "EVAL-OP-V2-R1",
        "assignment_sha256": digest,
        "results": results,
        "stop": stop,
        "request_caps_per_route": 154,
        "budgets_usd": budgets,
        "journal_totals": {
            route: journal_counts(journals[route]) for route in (*ROUTES, "dint")
        },
    }
    save_json(root / "results.json", final)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error("Explicit live mode and researcher-approved receipt required")
    auth = json.loads(args.authorization.read_text())
    from tools.eval_op_v2.freeze import MANIFEST, manifest

    if (
        hashlib.sha256(MANIFEST.read_bytes()).hexdigest() != auth.get("manifest_sha256")
        or json.loads(MANIFEST.read_text()) != manifest()
    ):
        parser.error("Approved manifest hash or source integrity differs")
    if (
        auth.get("researcher_approved") is not True
        or auth.get("experiment") != "EVAL-OP-V2-R1"
    ):
        parser.error("R1 approval receipt required")
    secrets = {
        r: os.environ.get(k, "")
        for r, k in [
            ("qwen", "EVAL_OP_QWEN_KEY"),
            ("deepseek", "EVAL_OP_DEEPSEEK_KEY"),
            ("mistral", "EVAL_OP_MISTRAL_KEY"),
            ("openai", "OPENAI_API_KEY"),
        ]
    }
    if not all(secrets.values()):
        parser.error("Required provider environment variables are missing")
    clients = {
        "qwen": HttpClient(
            "qwen", secrets["qwen"], ca_file=os.environ.get("EVAL_OP_QWEN_CA")
        ),
        "deepseek": HttpClient("deepseek", secrets["deepseek"]),
        "mistral": PacedClient(secrets["mistral"], None, minimum_gap_s=15),
        "openai": ResponsesClient(secrets["openai"]),
    }
    assignments = build()
    collect(
        assignments,
        build_schedule(assignments),
        clients,
        args.output,
        expected_sha256=auth["assignment_canonical_sha256"],
        budgets=auth["budgets_usd"],
        max_hours=auth["max_hours"],
    )


if __name__ == "__main__":
    main()
