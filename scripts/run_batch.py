import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# Ensure src directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)

RESULT_COLUMNS = [
    "incident_file",
    "run_id",
    "incident_id",
    "status",
    "fatal_status",
    "retry_count",
    "elapsed_sec",
    "error",
]


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"{key} must be set.")
    return value.strip()


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None:
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
            continue
        current = current.__context__
    return chain


def _is_retriable_error(exc: BaseException) -> bool:
    for current in _iter_exception_chain(exc):
        if isinstance(current, httpx.TransportError):
            return True
        if isinstance(current, httpx.HTTPStatusError) and current.response.status_code == 429:
            return True
        message = str(current).lower()
        if "rate limit" in message or "429" in message or "timeout" in message:
            return True
    return False


def _merge_state(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    append_keys = {"judge_feedback", "judge_findings", "tool_ledger"}
    merged = dict(current)
    for key, value in update.items():
        if key in append_keys and isinstance(value, list):
            existing = merged.get(key)
            if isinstance(existing, list):
                merged[key] = existing + value
            else:
                merged[key] = list(value)
            continue
        merged[key] = value
    return merged


def _load_incident_files(incidents_dir: Path) -> list[Path]:
    if not incidents_dir.exists():
        raise FileNotFoundError(f"Incidents directory does not exist: {incidents_dir}")
    if not incidents_dir.is_dir():
        raise ValueError(f"--incidents-dir must point to a directory: {incidents_dir}")

    files = sorted(path for path in incidents_dir.iterdir() if path.suffix.lower() == ".json")
    if not files:
        raise ValueError(f"No incident JSON files found in {incidents_dir}")
    return files


def _append_result_row(results_path: Path, row: dict[str, Any]) -> None:
    file_exists = results_path.exists()
    with results_path.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=RESULT_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


@retry(
    retry=retry_if_exception(_is_retriable_error),
    wait=wait_exponential(min=2, max=20),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _stream_graph_with_retry(
    initial_state: dict[str, Any],
    thread_id: str,
) -> dict[str, Any]:
    from agents.variant_b import get_variant_b_graph  # noqa: WPS433

    graph = get_variant_b_graph()
    config = {
        "recursion_limit": 50,
        "configurable": {"thread_id": thread_id},
    }

    running_state = dict(initial_state)
    for output in graph.stream(initial_state, config=config, stream_mode="updates"):
        if not isinstance(output, dict):
            continue
        for _node_name, state_update in output.items():
            if isinstance(state_update, dict):
                running_state = _merge_state(running_state, state_update)

    return running_state


def _determine_status(final_state: dict[str, Any], incident_valid: bool) -> str:
    if not incident_valid:
        return "FATAL_VALIDATION"

    fatal_status = final_state.get("fatal_status")
    if fatal_status == "FATAL_VALIDATION_ERROR":
        return "FATAL_VALIDATION"

    if isinstance(fatal_status, str) and fatal_status:
        return "ERROR"

    sandbox_results = final_state.get("sandbox_results")
    if isinstance(sandbox_results, list) and sandbox_results:
        has_success = any(
            isinstance(row, dict) and str(row.get("execution_status", "")).upper() == "SUCCESS"
            for row in sandbox_results
        )
        if has_success:
            return "SUCCESS"
        return "INFEASIBLE"

    return "ERROR"


def main() -> None:
    from agents.variant_b.state import IncidentTrigger  # noqa: WPS433
    from core.observability import setup_observability  # noqa: WPS433

    parser = argparse.ArgumentParser(description="Run Variant B in batch mode over incident JSON files.")
    parser.add_argument(
        "--incidents-dir",
        required=True,
        help="Directory containing IncidentTrigger JSON files.",
    )
    parser.add_argument(
        "--output-csv",
        default="data/results_variant_b_batch.csv",
        help="Path for batch result CSV output.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of incidents to run.")
    parser.add_argument(
        "--thread-prefix",
        default="variant-b-batch",
        help="Prefix used for LangGraph thread_id values.",
    )
    parser.add_argument(
        "--sleep-between-sec",
        type=float,
        default=1.0,
        help="Delay between incidents in seconds.",
    )
    args = parser.parse_args()

    if _is_truthy(os.getenv("DISABLE_OBSERVABILITY")):
        raise RuntimeError("DISABLE_OBSERVABILITY must be FALSE for batch runs.")

    _require_env("REDIS_PREFIX")
    _require_env("POSTGRES_DB")
    _require_env("QDRANT_COLLECTION")
    _require_env("TYPESENSE_COLLECTION")
    _require_env("PHOENIX_COLLECTOR_ENDPOINT")
    _require_env("PHOENIX_PROJECT_NAME")

    setup_observability()

    incident_files = _load_incident_files(Path(args.incidents_dir))
    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")
        incident_files = incident_files[: min(args.limit, len(incident_files))]

    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    counts = {
        "TOTAL": len(incident_files),
        "SUCCESS": 0,
        "FATAL_VALIDATION": 0,
        "INFEASIBLE": 0,
        "ERROR": 0,
    }

    for idx, incident_file in enumerate(incident_files, start=1):
        started_at = time.perf_counter()
        incident_valid = False
        final_state: dict[str, Any] = {}
        run_id = incident_file.stem
        incident_id = incident_file.stem
        error_text = ""

        print(f"[RUN {idx:03d}/{len(incident_files):03d}] incident_file={incident_file.name}")

        try:
            payload = json.loads(incident_file.read_text(encoding="utf-8"))
            incident = IncidentTrigger.model_validate(payload)
            incident_valid = True
            run_id = incident.incident_id
            incident_id = incident.incident_id

            thread_id = f"{args.thread_prefix}-{run_id}"
            initial_state: dict[str, Any] = {
                "incident": incident,
                "run_id": run_id,
                "retry_count": 0,
                "thread_id": thread_id,
                "incident_context": {},
                "scenarios": [],
                "judge_verdict": None,
                "judge_feedback": [],
                "judge_findings": [],
                "tool_ledger": [],
                "sandbox_results": [],
                "final_report_md": None,
                "fatal_status": None,
                "embedding_model": None,
                "embedding_latency_ms": None,
                "pareto_frontier_ids": [],
                "yaam_l3_status": None,
                "yaam_l4_status": None,
                "agent_id": os.getenv("AGENT_ID", "scm-sandwich-variantb-v1"),
            }

            final_state = _stream_graph_with_retry(initial_state=initial_state, thread_id=thread_id)

        except Exception as exc:  # noqa: BLE001
            error_text = f"{type(exc).__name__}: {exc}"
            print(f"  ERROR: {error_text}")

        elapsed = time.perf_counter() - started_at
        status = _determine_status(final_state, incident_valid=incident_valid)

        if status in counts:
            counts[status] += 1
        else:
            counts["ERROR"] += 1

        fatal_status = final_state.get("fatal_status") if isinstance(final_state, dict) else None
        retry_count = int(final_state.get("retry_count", 0)) if isinstance(final_state, dict) else 0

        row = {
            "incident_file": incident_file.name,
            "run_id": run_id,
            "incident_id": incident_id,
            "status": status,
            "fatal_status": fatal_status or "",
            "retry_count": retry_count,
            "elapsed_sec": f"{elapsed:.2f}",
            "error": error_text,
        }
        _append_result_row(output_path, row)

        print(
            f"  STATUS={status} "
            f"fatal_status={row['fatal_status'] or '-'} "
            f"retry_count={retry_count} "
            f"elapsed_sec={row['elapsed_sec']}"
        )

        if idx < len(incident_files) and args.sleep_between_sec > 0:
            time.sleep(args.sleep_between_sec)

    print("\nBatch Summary")
    print(
        f"Total Run: {counts['TOTAL']}, "
        f"Success: {counts['SUCCESS']}, "
        f"Fatal Validation: {counts['FATAL_VALIDATION']}, "
        f"Infeasible: {counts['INFEASIBLE']}"
    )
    print(f"Error: {counts['ERROR']}")
    print(f"Results CSV: {output_path}")


if __name__ == "__main__":
    main()
