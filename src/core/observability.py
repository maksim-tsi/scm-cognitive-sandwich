import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load .env early so OpenTelemetry/OpenInference sees env vars.
_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(_dotenv_path, override=True)

def setup_observability():
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from opentelemetry import trace as trace_api
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk import trace as trace_sdk
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    project_name = os.environ.get("PHOENIX_PROJECT_NAME")

    if not endpoint or not project_name:
        print("Observability not configured. Skipping Phoenix setup.")
        return

    # Set project name for Phoenix
    os.environ["PHOENIX_PROJECT_NAME"] = project_name
    os.environ["OTEL_SERVICE_NAME"] = project_name

    tracer_provider = trace_sdk.TracerProvider()
    
    # Configure OTLP Exporter for Phoenix
    # Using v1/traces as typical for OTLP HTTP depending on the endpoint string,
    # but usually the endpoint from env is the full URL (e.g. http://localhost:6006/v1/traces)
    span_exporter = OTLPSpanExporter(endpoint=endpoint)
    span_processor = SimpleSpanProcessor(span_exporter=span_exporter)
    tracer_provider.add_span_processor(span_processor=span_processor)
    
    trace_api.set_tracer_provider(tracer_provider=tracer_provider)

    # Instrument
    LangChainInstrumentor().instrument()
    
    print(f"Observability configured. Exporting to {endpoint} for project {project_name}.")

if __name__ == "__main__":
    setup_observability()
