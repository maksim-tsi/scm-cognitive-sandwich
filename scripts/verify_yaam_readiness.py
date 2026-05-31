"""Read-only YAAM consumer readiness verification for SCM Cognitive Sandwich."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


EXPECTED_RESOURCE_TEMPLATES = {
    "yaam://artifacts/{artifact_id}/lineage",
    "yaam://sessions/{session_id}/artifacts",
    "yaam://runs/{run_id}/artifacts",
    "yaam://runs/{run_id}/evidence",
    "yaam://incidents/{incident_id}/reports",
}
EXPECTED_PROMPTS = {
    "yaam.prompt.artifact_repair_context",
    "yaam.prompt.artifact_lineage_summary",
}


def _strip_quotes(value: str) -> str:
    return value.strip().strip("'").strip('"')


def _env(key: str, default: str | None = None) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        if default is None:
            raise RuntimeError(f"{key} must be set.")
        return default
    return _strip_quotes(value)


class MCPClient:
    def __init__(self, *, url: str, timeout_s: float) -> None:
        import httpx  # noqa: WPS433

        self._url = url
        self._timeout_s = timeout_s
        self._client = httpx.Client(timeout=timeout_s)
        self._headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
        }
        self._next_id = 1

    def close(self) -> None:
        self._client.close()

    def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params

        response = self._client.post(
            self._url,
            headers=self._headers,
            json=payload,
            timeout=self._timeout_s,
        )
        response.raise_for_status()
        data = response.json() if response.text else {}
        if data.get("error"):
            raise RuntimeError(f"MCP {method} failed: {data['error']}")
        return data

    def notify_initialized(self) -> None:
        response = self._client.post(
            self._url,
            headers=self._headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            timeout=self._timeout_s,
        )
        response.raise_for_status()


def _json_from_tool_text(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("result", {}).get("content", [])
    if not content or not isinstance(content[0], dict):
        raise RuntimeError("MCP tool response missing text content.")
    text = content[0].get("text")
    if not isinstance(text, str):
        raise RuntimeError("MCP tool response missing text field.")
    return json.loads(text)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _print_ok(message: str) -> None:
    print(f"OK {message}")


def _run_mcp_checks(*, client: MCPClient, session_id: str, agent_id: str) -> None:
    init = client.rpc(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "scm-cognitive-sandwich-readiness", "version": "0.1"},
        },
    )
    server_info = init.get("result", {}).get("serverInfo", {})
    _print_ok(f"MCP initialize server={server_info.get('name')} version={server_info.get('version')}")
    client.notify_initialized()

    tools = client.rpc("tools/list", {}).get("result", {}).get("tools", [])
    tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    _assert("yaam.health.check" in tool_names, "MCP missing yaam.health.check.")
    _assert("yaam.memory.get_context" in tool_names, "MCP missing yaam.memory.get_context.")
    _assert("yaam.evidence.table" in tool_names, "MCP missing yaam.evidence.table.")
    _print_ok(f"MCP tools discovered count={len(tool_names)}")

    resources = client.rpc("resources/list", {}).get("result", {}).get("resources", [])
    resource_uris = {resource.get("uri") for resource in resources if isinstance(resource, dict)}
    _assert("yaam://config/ciar" in resource_uris, "MCP missing yaam://config/ciar.")
    _print_ok(f"MCP static resources discovered count={len(resource_uris)}")

    templates = client.rpc("resources/templates/list", {}).get("result", {}).get("resourceTemplates", [])
    template_uris = {template.get("uriTemplate") for template in templates if isinstance(template, dict)}
    missing_templates = EXPECTED_RESOURCE_TEMPLATES - template_uris
    _assert(not missing_templates, f"MCP missing Cognitive Sandwich templates: {sorted(missing_templates)}")
    _print_ok("MCP Cognitive Sandwich resource templates discovered")

    prompts = client.rpc("prompts/list", {}).get("result", {}).get("prompts", [])
    prompt_names = {prompt.get("name") for prompt in prompts if isinstance(prompt, dict)}
    missing_prompts = EXPECTED_PROMPTS - prompt_names
    _assert(not missing_prompts, f"MCP missing Cognitive Sandwich prompts: {sorted(missing_prompts)}")
    _print_ok("MCP Cognitive Sandwich prompts discovered")

    ciar = client.rpc("resources/read", {"uri": "yaam://config/ciar"})
    ciar_contents = ciar.get("result", {}).get("contents", [])
    _assert(bool(ciar_contents), "MCP yaam://config/ciar returned no contents.")
    _print_ok("MCP yaam://config/ciar readable")

    health = _json_from_tool_text(client.rpc("tools/call", {"name": "yaam.health.check", "arguments": {}}))
    health_payload = health.get("health", {})
    _assert(health_payload.get("status") == "ok", f"MCP health is not ok: {health_payload.get('status')}")
    _print_ok("MCP yaam.health.check status=ok")

    fact = client.rpc("resources/read", {"uri": "yaam://facts/nonexistent-readiness-fact"})
    fact_contents = fact.get("result", {}).get("contents", [])
    fact_text = fact_contents[0].get("text") if fact_contents and isinstance(fact_contents[0], dict) else "{}"
    fact_payload = json.loads(fact_text)
    _assert(fact_payload.get("status") == "not_found", "MCP nonexistent fact lookup did not return not_found.")
    _print_ok("MCP nonexistent fact lookup returns not_found")

    scope = {
        "session_id": session_id,
        "agent_id": agent_id,
        "task_id": "artifact-repair-readiness",
        "run_id": "artifact-run-001",
        "caller_role": "benchmark_runtime_agent",
        "visibility_scope": "benchmark_runtime",
    }
    context_args = {
        **scope,
        "query": "artifact repair readiness context",
        "max_items": 5,
    }
    context_result = client.rpc(
        "tools/call",
        {"name": "yaam.memory.get_context", "arguments": context_args},
    ).get("result", {})
    _assert(not context_result.get("isError"), "MCP yaam.memory.get_context returned an error.")
    context = context_result.get("structuredContent", {}).get("context", {})
    _assert(context.get("leakage_guard_passed") is True, "MCP context leakage guard did not pass.")
    _print_ok(f"MCP context leakage_guard_passed=true items={len(context.get('items', []))}")

    evidence_args = {
        **scope,
        "query": "The artifact repair pass corrected the synthetic validation failure.",
    }
    evidence_result = client.rpc(
        "tools/call",
        {"name": "yaam.evidence.table", "arguments": evidence_args},
    ).get("result", {})
    _assert(not evidence_result.get("isError"), "MCP yaam.evidence.table returned an error.")
    evidence = evidence_result.get("structuredContent", {}).get("evidence_table", {})
    _assert(evidence.get("partial") is False, "MCP evidence table unexpectedly marked partial.")
    _print_ok(f"MCP evidence table assembled rows={len(evidence.get('rows', []))}")

    repair_prompt = client.rpc(
        "prompts/get",
        {
            "name": "yaam.prompt.artifact_repair_context",
            "arguments": {
                "artifact_id": "artifact-readiness-001",
                "run_id": "artifact-run-001",
                "include_feedback": "true",
            },
        },
    )
    _assert(repair_prompt.get("result", {}).get("messages"), "MCP artifact repair prompt did not render.")
    lineage_prompt = client.rpc(
        "prompts/get",
        {
            "name": "yaam.prompt.artifact_lineage_summary",
            "arguments": {
                "artifact_id": "artifact-readiness-001",
                "include_payload_hashes": "true",
            },
        },
    )
    _assert(lineage_prompt.get("result", {}).get("messages"), "MCP artifact lineage prompt did not render.")
    _print_ok("MCP Cognitive Sandwich prompts render")


def _run_rest_checks(*, rest_url: str, session_id: str, agent_id: str, timeout_s: float) -> None:
    import httpx  # noqa: WPS433

    base = rest_url.rstrip("/")
    scope_payload = {
        "session_id": session_id,
        "agent_id": agent_id,
        "task_id": "artifact-repair-readiness",
        "run_id": "artifact-run-001",
        "caller_role": "benchmark_runtime_agent",
        "visibility_scope": "benchmark_runtime",
    }
    with httpx.Client(timeout=timeout_s) as client:
        health = client.get(f"{base}/health")
        health.raise_for_status()
        health_payload = health.json()
        _assert(health_payload.get("status") == "ok", f"REST health is not ok: {health_payload.get('status')}")
        _print_ok("REST GET /health status=ok")

        context_payload = {
            **scope_payload,
            "query": "Return safe prior implementation notes for this benchmark task.",
            "max_items": 5,
        }
        context = client.post(f"{base}/v2/memory/context", json=context_payload)
        context.raise_for_status()
        context_body = context.json()
        context_data = context_body.get("context", {})
        _assert(context_data.get("leakage_guard_passed") is True, "REST context leakage guard did not pass.")
        _print_ok(f"REST /v2/memory/context items={len(context_data.get('items', []))}")

        query_payload = {
            **scope_payload,
            "query": "Return safe prior implementation notes for this benchmark task.",
            "limit": 5,
        }
        query = client.post(f"{base}/v2/memory/query", json=query_payload)
        query.raise_for_status()
        query_body = query.json()
        leakage_guard = query_body.get("leakage_guard", {})
        _assert(leakage_guard.get("leakage_guard_passed") is True, "REST query leakage guard did not pass.")
        _print_ok(f"REST /v2/memory/query results={len(query_body.get('results', []))}")

        l3_payload = {
            **scope_payload,
            "nl_query": "Return safe prior implementation notes for this benchmark task.",
            "limit": 5,
        }
        l3 = client.post(f"{base}/v2/memory/l3/query", json=l3_payload)
        l3.raise_for_status()
        l3_body = l3.json()
        _assert(l3_body.get("status") == "success", f"REST L3 query failed: {l3_body}")
        _print_ok(f"REST /v2/memory/l3/query results={len(l3_body.get('results', []))}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only YAAM consumer readiness checks.")
    parser.add_argument("--mcp-url", default=_env("YAAM_MCP_URL", "http://192.168.107.187:8003/mcp"))
    parser.add_argument("--rest-url", default=_env("YAAM_REST_URL", "http://192.168.107.187:8002"))
    parser.add_argument("--session-id", default="scm-cognitive-sandwich-readiness-readonly")
    parser.add_argument("--agent-id", default="codex-macbook-readiness")
    parser.add_argument("--timeout-s", type=float, default=20.0)
    args = parser.parse_args()

    project_id = _env("YAAM_PROJECT_ID", "scm-cognitive-sandwich")
    domain_packs = _env("YAAM_MCP_DOMAIN_PACKS", "auto")
    _assert(project_id == "scm-cognitive-sandwich", f"Unexpected YAAM_PROJECT_ID={project_id!r}")
    _assert(domain_packs == "auto", f"Unexpected YAAM_MCP_DOMAIN_PACKS={domain_packs!r}")
    _print_ok(f"YAAM env project={project_id} domain_packs={domain_packs}")

    client = MCPClient(url=args.mcp_url, timeout_s=args.timeout_s)
    try:
        _run_mcp_checks(client=client, session_id=args.session_id, agent_id=args.agent_id)
    finally:
        client.close()
    _run_rest_checks(
        rest_url=args.rest_url,
        session_id=args.session_id,
        agent_id=args.agent_id,
        timeout_s=args.timeout_s,
    )
    print("YAAM READINESS OK read_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
