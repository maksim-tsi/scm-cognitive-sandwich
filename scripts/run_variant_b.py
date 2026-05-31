import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Ensure src directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# Load .env before imports that read env vars.
_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


def _load_incident_trigger(path: Path):
    from agents.variant_b.state import IncidentTrigger  # noqa: WPS433

    payload = json.loads(path.read_text(encoding="utf-8"))
    return IncidentTrigger.model_validate(payload)

def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _strip_quotes(value: str) -> str:
    return value.strip().strip("'").strip('"')


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"{key} must be set.")
    return value.strip()


def _jsonable(value):
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _jsonable(value.model_dump())
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _merge_state(current: dict, update: dict) -> dict:
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


def _phoenix_base_url(collector_endpoint: str) -> str:
    endpoint = collector_endpoint.strip().rstrip("/")
    if endpoint.endswith("/v1/traces"):
        endpoint = endpoint[: -len("/v1/traces")]
    return endpoint.rstrip("/")


def _require_phoenix_collector_endpoint() -> str:
    endpoint = _strip_quotes(_require_env("PHOENIX_COLLECTOR_ENDPOINT"))
    if not endpoint.startswith(("http://", "https://")):
        raise RuntimeError(f"PHOENIX_COLLECTOR_ENDPOINT must be an HTTP URL: {endpoint!r}")
    if not endpoint.rstrip("/").endswith("/v1/traces"):
        raise RuntimeError(
            "PHOENIX_COLLECTOR_ENDPOINT must point at the OTLP traces endpoint "
            f"(.../v1/traces), got {endpoint!r}."
        )
    return endpoint


def _verify_phoenix_spans(*, thread_id: str, run_id: str) -> None:
    import httpx  # noqa: WPS433

    collector = _require_phoenix_collector_endpoint()
    project = _strip_quotes(_require_env("PHOENIX_PROJECT_NAME"))
    base = _phoenix_base_url(collector)

    url = f"{base}/v1/projects/{project}/spans"
    time.sleep(2.0)

    with httpx.Client() as client:
        response = client.get(url, params={"limit": 200}, timeout=15.0)
        response.raise_for_status()
        payload = response.json()

    spans = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(spans, list):
        raise ValueError("Phoenix spans response missing data list.")

    names = [span.get("name") for span in spans if isinstance(span, dict)]
    found_execute = any(name == "node_execute_sandbox" for name in names)
    found_synth = any(name == "node_synthesize_report" for name in names)

    def has_embedding_latency(span: dict) -> bool:
        attrs = span.get("attributes")
        if not isinstance(attrs, dict):
            return False
        return "embedding_latency_ms" in attrs

    found_latency = any(isinstance(span, dict) and has_embedding_latency(span) for span in spans)
    # Optional: thread_id filtering if attributes exist.
    thread_hits = 0
    for span in spans:
        if not isinstance(span, dict):
            continue
        attrs = span.get("attributes")
        if not isinstance(attrs, dict):
            continue
        if attrs.get("metadata.thread_id") == thread_id or attrs.get("thread_id") == thread_id:
            thread_hits += 1

    print(
        "PHOENIX VERIFY "
        f"project={project} thread_hits={thread_hits} "
        f"node_execute_sandbox={found_execute} node_synthesize_report={found_synth} "
        f"embedding_latency_ms={found_latency}"
    )
    if not (found_execute and found_synth and found_latency):
        raise RuntimeError(
            "Phoenix verification failed: expected spans for node_execute_sandbox, "
            "node_synthesize_report, and embedding_latency_ms attribute."
        )


def main() -> None:
    from agents.variant_b import get_variant_b_graph  # noqa: WPS433
    from agents.variant_b.state import VariantBState  # noqa: WPS433
    from core.env_guard import assert_no_localhost_services  # noqa: WPS433
    from core.observability import setup_observability  # noqa: WPS433
    from memory.adapters.qdrant_http import QdrantHttpAdapter  # noqa: WPS433
    from memory.adapters.typesense_http import TypesenseHttpAdapter  # noqa: WPS433
    from memory.yaam_facade import YAAMFacade, set_facade  # noqa: WPS433

    parser = argparse.ArgumentParser(description="Run the Variant B plan-and-execute graph.")
    parser.add_argument("--incident-json", required=True, help="Path to IncidentTrigger JSON file.")
    parser.add_argument("--thread-id", default="variant-b-session", help="LangGraph thread id.")
    parser.add_argument("--run-id", default=None, help="Optional run id override.")
    parser.add_argument(
        "--demo-clarifying-loop",
        action="store_true",
        help="First generation attempt intentionally includes a flawed scenario to demonstrate REJECT loop.",
    )
    args = parser.parse_args()

    if _is_truthy(os.getenv("DISABLE_OBSERVABILITY")):
        raise RuntimeError("DISABLE_OBSERVABILITY must not be set for Exec Plan 3 runs.")

    # Required namespaces (RFC-006 isolation).
    _require_env("REDIS_PREFIX")
    _require_env("POSTGRES_DB")
    _require_env("QDRANT_COLLECTION")
    _require_env("TYPESENSE_COLLECTION")

    # Require Phoenix env to be present and well-formed (observability feedback loop).
    _require_phoenix_collector_endpoint()
    phoenix_project = _strip_quotes(_require_env("PHOENIX_PROJECT_NAME"))

    assert_no_localhost_services()
    setup_observability()

    incident_path = Path(args.incident_json)
    incident = _load_incident_trigger(incident_path)
    run_id = args.run_id or incident.incident_id

    # YAAM facade wiring (lightweight HTTP adapters).
    qdrant_url = _require_env("QDRANT_URL")
    typesense_url = _require_env("TYPESENSE_URL")
    typesense_api_key = _require_env("TYPESENSE_API_KEY")

    qdrant = QdrantHttpAdapter(base_url=qdrant_url, api_key=(os.getenv("QDRANT_API_KEY") or "").strip() or None)
    typesense = TypesenseHttpAdapter(base_url=typesense_url, api_key=typesense_api_key)
    set_facade(
        YAAMFacade(
            project=phoenix_project,
            agent_id=os.getenv("AGENT_ID", "scm-sandwich-variantb-v1"),
            qdrant=qdrant,
            typesense=typesense,
        )
    )

    initial_state: VariantBState = {
        "incident": incident,
        "run_id": run_id,
        "retry_count": 0,
        "thread_id": args.thread_id,
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

    config = {
        "recursion_limit": 50,
        "configurable": {"thread_id": args.thread_id},
    }

    graph = get_variant_b_graph()

    if args.demo_clarifying_loop:
        os.environ["VARIANT_B_DEMO_CLARIFYING_LOOP"] = "true"

    run_dir = Path("data") / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print("--- Starting Variant B Execution ---")
    print(f"run_id={run_id} thread_id={args.thread_id}")
    print(f"artifacts_dir={run_dir}")

    last_retry = initial_state["retry_count"]
    fatal_status: str | None = None

    current_state: dict = dict(initial_state)
    step = 0

    for output in graph.stream(initial_state, config=config, stream_mode="updates"):
        for node_name, state_update in output.items():
            print(f"[NODE COMPLETED] {node_name}")
            if not isinstance(state_update, dict):
                continue

            current_state = _merge_state(current_state, state_update)
            step += 1
            snapshot_path = run_dir / f"{run_id}_step_{step:02d}.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "thread_id": args.thread_id,
                        "step": step,
                        "node": node_name,
                        "state": _jsonable(current_state),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            if isinstance(state_update.get("retry_count"), int) and state_update["retry_count"] != last_retry:
                last_retry = state_update["retry_count"]
                print(f"  retry_count={last_retry}")

            if node_name == "node_judge_validation":
                verdict = state_update.get("judge_verdict")
                if isinstance(verdict, str) and verdict:
                    print(f"  judge_verdict={verdict}")
                fb = state_update.get("judge_feedback")
                if isinstance(fb, list) and fb:
                    print(f"  judge_feedback={fb[-1]}")

            if node_name == "node_synthesize_report":
                emb_lat = state_update.get("embedding_latency_ms")
                emb_model = state_update.get("embedding_model")
                if isinstance(emb_model, str) and emb_model:
                    print(f"  embedding_model={emb_model}")
                if isinstance(emb_lat, (int, float)):
                    print(f"  embedding_latency_ms={float(emb_lat):.2f}")
                pareto_ids = state_update.get("pareto_frontier_ids")
                if isinstance(pareto_ids, list) and pareto_ids:
                    print(f"  pareto_frontier_ids={pareto_ids}")
                l3_status = state_update.get("yaam_l3_status")
                l4_status = state_update.get("yaam_l4_status")
                if isinstance(l3_status, str):
                    print(f"  yaam_l3_status={l3_status}")
                if isinstance(l4_status, str):
                    print(f"  yaam_l4_status={l4_status}")

            if isinstance(state_update.get("fatal_status"), str):
                fatal_status = state_update["fatal_status"]
                print(f"  fatal_status={fatal_status}")

    print("--- Execution Finished ---")
    if fatal_status:
        print(f"FINAL_STATUS={fatal_status}")
    else:
        print("FINAL_STATUS=SUCCESS")

    report = current_state.get("final_report_md")
    report_path = run_dir / f"report_{run_id}.md"
    if isinstance(report, str) and report.strip():
        report_path.write_text(report, encoding="utf-8")
    else:
        report_path.write_text("# Variant B Report\n\n(No report was produced.)\n", encoding="utf-8")
    print(f"report_path={report_path}")

    _verify_phoenix_spans(thread_id=args.thread_id, run_id=run_id)


if __name__ == "__main__":
    main()
