import os
from pathlib import Path
from typing import Dict

from dotenv import find_dotenv, load_dotenv

# Load .env early so OpenTelemetry/OpenInference sees env vars.
_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(_dotenv_path, override=True)

OPENINFERENCE_PROJECT_NAME_ATTRIBUTE = "openinference.project.name"
LEGACY_PROJECT_NAME_ATTRIBUTE = "project.name"
SERVICE_NAME_ATTRIBUTE = "service.name"


def _parse_resource_attributes(raw_attributes: str | None) -> Dict[str, str]:
    if not raw_attributes:
        return {}

    attributes: Dict[str, str] = {}
    for pair in raw_attributes.split(","):
        normalized_pair = pair.strip().strip('"').strip("'")
        if not normalized_pair or "=" not in normalized_pair:
            continue
        key, value = normalized_pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            attributes[key] = value
    return attributes


def _resolve_project_name(raw_resource_attributes: str | None, phoenix_project_name: str | None) -> str | None:
    resource_attributes = _parse_resource_attributes(raw_resource_attributes)
    return (
        resource_attributes.get(OPENINFERENCE_PROJECT_NAME_ATTRIBUTE)
        or resource_attributes.get(LEGACY_PROJECT_NAME_ATTRIBUTE)
        or phoenix_project_name
    )


def _build_resource_attributes(project_name: str, raw_resource_attributes: str | None) -> Dict[str, str]:
    resource_attributes = _parse_resource_attributes(raw_resource_attributes)

    # Phoenix routes traces by openinference.project.name; support legacy project.name input.
    if (
        LEGACY_PROJECT_NAME_ATTRIBUTE in resource_attributes
        and OPENINFERENCE_PROJECT_NAME_ATTRIBUTE not in resource_attributes
    ):
        resource_attributes[OPENINFERENCE_PROJECT_NAME_ATTRIBUTE] = resource_attributes[
            LEGACY_PROJECT_NAME_ATTRIBUTE
        ]

    resource_attributes.setdefault(OPENINFERENCE_PROJECT_NAME_ATTRIBUTE, project_name)

    service_name = os.environ.get("OTEL_SERVICE_NAME") or project_name
    resource_attributes.setdefault(SERVICE_NAME_ATTRIBUTE, service_name)

    return resource_attributes

def setup_observability():
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from opentelemetry import trace as trace_api
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk import trace as trace_sdk
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    raw_resource_attributes = os.environ.get("OTEL_RESOURCE_ATTRIBUTES")
    project_name = _resolve_project_name(
        raw_resource_attributes=raw_resource_attributes,
        phoenix_project_name=os.environ.get("PHOENIX_PROJECT_NAME"),
    )

    if not endpoint or not project_name:
        print("Observability not configured. Skipping Phoenix setup.")
        return

    # Set project name for Phoenix
    os.environ["PHOENIX_PROJECT_NAME"] = project_name
    os.environ.setdefault("OTEL_SERVICE_NAME", project_name)

    resource_attributes = _build_resource_attributes(
        project_name=project_name,
        raw_resource_attributes=raw_resource_attributes,
    )

    # Keep env in sync for any instrumentors that lazily read OTEL_RESOURCE_ATTRIBUTES.
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(
        f"{key}={value}" for key, value in sorted(resource_attributes.items())
    )

    tracer_provider = trace_sdk.TracerProvider(resource=Resource.create(resource_attributes))
    
    # Configure OTLP Exporter for Phoenix
    # Using v1/traces as typical for OTLP HTTP depending on the endpoint string,
    # but usually the endpoint from env is the full URL (e.g. http://localhost:6006/v1/traces)
    span_exporter = OTLPSpanExporter(endpoint=endpoint)
    span_processor = SimpleSpanProcessor(span_exporter=span_exporter)
    tracer_provider.add_span_processor(span_processor=span_processor)
    
    trace_api.set_tracer_provider(tracer_provider=tracer_provider)

    # Instrument
    LangChainInstrumentor().instrument()

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except ModuleNotFoundError:
        # HTTPX spans are optional; LangGraph and LLM spans still export without this package.
        pass
    
    print(
        "Observability configured. "
        f"Exporting to {endpoint} for project {project_name} "
        f"({OPENINFERENCE_PROJECT_NAME_ATTRIBUTE}={resource_attributes[OPENINFERENCE_PROJECT_NAME_ATTRIBUTE]})."
    )

if __name__ == "__main__":
    setup_observability()
