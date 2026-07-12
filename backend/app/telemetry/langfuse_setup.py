import asyncio
import base64
import functools
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

logger = logging.getLogger(__name__)

tracer = trace.get_tracer("bandhu")


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
        from openinference.instrumentation.anthropic import AnthropicInstrumentor

        AnthropicInstrumentor().instrument(tracer_provider=provider)
    except ImportError:
        # clients/claude.py doesn't exist yet — nothing to auto-instrument.
        # Manual spans (session middleware, db, etc.) still export fine.
        logger.info("anthropic SDK not installed — Claude auto-instrumentation skipped.")

    logger.info("Langfuse telemetry configured (%s).", settings.langfuse_host)


def traced(span_name: str):
    """Decorator wrapping a function in a span. Works on both sync and async
    functions — every pipeline stage added later should use this rather than
    writing `with tracer.start_as_current_span(...)` at every call site."""

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
