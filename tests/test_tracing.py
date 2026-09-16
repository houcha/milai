import asyncio

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from milai.config import Settings
from milai.observability import Telemetry, export_span
from milai.store import Store
from milai.tutor import Tutor
from tests.helpers import MockProvider, call, say


def test_supported_instrumentation_parentage_usage_and_privacy(tmp_path, monkeypatch):
    monkeypatch.setenv("MILAI_TRACE_CONTENT", "false")
    exporter = InMemorySpanExporter()
    telemetry = Telemetry(exporter=exporter)
    config = Settings(
        "https://model.invalid/v1",
        "mock-model",
        "test-only",
        database=tmp_path / "trace.db",
    )
    store = Store(config.database)
    session = store.session(store.owner)
    provider = MockProvider(
        [
            call(
                "remember_profile",
                fact={
                    "field": "goals",
                    "value": "PRIVATE_SENTINEL",
                    "learner_quote": "PRIVATE_SENTINEL",
                },
            ),
            say("PRIVATE_SENTINEL"),
        ]
    )
    tutor = Tutor(config, store, telemetry, provider.model)
    asyncio.run(tutor.respond(store.owner, session, "PRIVATE_SENTINEL"))
    telemetry.flush()
    spans = exporter.get_finished_spans()
    assert len({s.context.trace_id for s in spans}) == 1
    kinds = [(s.attributes or {}).get("openinference.span.kind") for s in spans]
    assert kinds.count("LLM") == 2
    assert kinds.count("TOOL") == 1
    assert "PRIVATE_SENTINEL" not in str([s.attributes for s in spans])
    generations = [
        s for s in spans if (s.attributes or {}).get("openinference.span.kind") == "LLM"
    ]
    assert all(
        (s.attributes or {}).get("llm.token_count.prompt") == 20
        and (s.attributes or {}).get("llm.token_count.completion") == 10
        for s in generations
    )
    root = next(s for s in spans if s.name == "tutor-turn")
    assert export_span(root)
    assert root.attributes and root.attributes["milai.committed_event_ids"]
    asyncio.run(tutor.close())
    store.close()
