import asyncio
import base64
import functools
import json
import logging

from opentelemetry import baggage, context, trace
from opentelemetry.trace import Span
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

logger = logging.getLogger(__name__)

tracer = trace.get_tracer("bandhu")


class BaggageToSpanProcessor(SpanProcessor):
    """Copies `langfuse.session.id` from OTel baggage onto every span at
    start time — including ones this codebase never wraps in @traced, like
    OpenAIInstrumentor's auto-created ChatCompletion/CreateEmbeddings spans
    (openinference.instrumentation.openai builds its own tracer/spans
    directly, bypassing traced()'s decorator entirely). A SpanProcessor is
    the one hook that sees every span regardless of which code/library
    created it, so this is the only way to get baggage onto those spans
    too. Langfuse's own docs: session grouping needs this key on every span
    in the trace, not just the root, to work reliably."""

    def on_start(self, span: SdkSpan, parent_context: context.Context | None = None) -> None:
        session_id = baggage.get_baggage("langfuse.session.id", parent_context)
        if session_id:
            span.set_attribute("langfuse.session.id", session_id)


def setup_telemetry() -> None:
    """Wires spans to Langfuse. If keys aren't configured yet, this is a
    no-op — every `tracer.start_as_current_span(...)` call elsewhere in the
    app still works, it just creates spans that go nowhere, same graceful
    degradation as clients/db.py without a DATABASE_URL."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse keys not configured — telemetry spans are local no-ops.")
        return

    auth = base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
    ).decode()

    provider = TracerProvider()
    # Registered before the exporting processor — on_start runs
    # synchronously when a span is created, well before BatchSpanProcessor
    # reads its attributes at on_end/export time, so ordering between these
    # two doesn't actually matter for correctness; listed first because it
    # determines what gets exported, so it reads naturally that way.
    provider.add_span_processor(BaggageToSpanProcessor())
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{settings.langfuse_host}/api/public/otel/v1/traces",
                headers={"Authorization": f"Basic {auth}"},
            )
        )
    )
    trace.set_tracer_provider(provider)

    try:
        from openinference.instrumentation.openai import OpenAIInstrumentor

        # Patches the openai SDK client library itself, not a specific
        # provider's endpoint — this auto-traces clients/llm.py's calls to
        # NVIDIA NIM the same way it would trace calls to OpenAI directly,
        # since NVIDIA NIM is accessed through the openai package.
        OpenAIInstrumentor().instrument(tracer_provider=provider)
    except ImportError:
        # openai SDK not installed — nothing to auto-instrument yet.
        # Manual spans (session middleware, db, etc.) still export fine.
        logger.info("openai SDK not installed — LLM auto-instrumentation skipped.")

    logger.info("Langfuse telemetry configured (%s).", settings.langfuse_host)


def traced(span_name: str):
    """Decorator wrapping a function in a span. Works on both sync and async
    functions — every pipeline stage added later should use this rather than
    writing `with tracer.start_as_current_span(...)` at every call site.

    `langfuse.session.id` (what groups these into Langfuse's Sessions view)
    doesn't need to be set here — BaggageToSpanProcessor above stamps it
    onto every span, from every source, at start time."""

    def decorator(fn):
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(span_name):
                    return await fn(*args, **kwargs)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name):
                return fn(*args, **kwargs)

        return sync_wrapper

    return decorator


def record_io(span: Span, *, input_data=None, output_data=None) -> None:
    """Sets Langfuse's own recognized attribute keys (`langfuse.observation.
    input`/`.output`, see docs/opentelemetry) so a custom pipeline-stage span
    populates the Input/Output panes in Langfuse's UI, the same way
    OpenAIInstrumentor's auto-traced ChatCompletion/CreateEmbeddings spans
    already do via the OpenInference convention. Plain custom attributes
    (`classify.emotion`, `generate.response_text`, ...) never populated
    those panes — Langfuse only looks at this specific key, `gen_ai.prompt`/
    `.completion`, or the OpenInference `input.value`/`output.value`.
    Callers are responsible for the same TelemetryConfig gating already used
    for any other raw-content attribute at the call site — this helper does
    not add its own privacy check."""
    if input_data is not None:
        span.set_attribute("langfuse.observation.input", json.dumps(input_data, default=str))
    if output_data is not None:
        span.set_attribute("langfuse.observation.output", json.dumps(output_data, default=str))
