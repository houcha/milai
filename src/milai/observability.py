"""One framework integration plus an application-level commit summary."""

import os
from contextlib import contextmanager

from agents import set_trace_processors
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.trace import Status, StatusCode


def export_span(span: ReadableSpan) -> bool:
    from langfuse.span_filter import is_default_export_span

    return is_default_export_span(span) or bool(
        span.instrumentation_scope
        and span.instrumentation_scope.name == "milai.application"
    )


class Telemetry:
    def __init__(self, *, enabled: bool = True, exporter=None):
        self.client = None
        self.provider = TracerProvider()
        self.content = os.getenv("MILAI_TRACE_CONTENT", "false").lower() == "true"
        self.last_trace_id = None
        set_trace_processors([])  # Never export to OpenAI as a side effect.
        configured = all(
            os.getenv(k)
            for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
        )
        if enabled and (configured or exporter is not None):
            from openinference.instrumentation import TraceConfig
            from openinference.instrumentation.openai_agents import (
                OpenAIAgentsInstrumentor,
            )

            if exporter is not None:
                from opentelemetry.sdk.trace.export import SimpleSpanProcessor

                self.provider.add_span_processor(SimpleSpanProcessor(exporter))
            else:
                from langfuse import Langfuse

                self.client = Langfuse(
                    tracer_provider=self.provider,
                    timeout=10,
                    should_export_span=export_span,
                )
            instrumentor = OpenAIAgentsInstrumentor()
            if instrumentor.is_instrumented_by_opentelemetry:
                instrumentor.uninstrument()
            instrumentor.instrument(
                tracer_provider=self.provider,
                exclusive_processor=True,
                config=TraceConfig(
                    hide_inputs=not self.content,
                    hide_outputs=not self.content,
                ),
            )
        self.tracer = self.provider.get_tracer("milai.application")

    @contextmanager
    def turn(self, learner: str, session: str, prompt_version: str):
        from langfuse import propagate_attributes

        with (
            propagate_attributes(
                user_id=learner,
                session_id=session,
                version=prompt_version,
                trace_name="language-tutor",
            ),
            self.tracer.start_as_current_span(
                "tutor-turn", record_exception=False, set_status_on_exception=False
            ) as span,
        ):
            self.last_trace_id = format(span.get_span_context().trace_id, "032x")
            span.set_attribute("milai.prompt_version", prompt_version)
            try:
                yield span
            except BaseException as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise

    def flush(self):
        if self.client:
            self.client.flush()
        self.provider.force_flush(timeout_millis=10000)
