import asyncio
import json

from milai.config import Settings
from milai.observability import Telemetry
from milai.probe import probe
from tests.helpers import MockProvider, call, say


def test_probe_exercises_real_adapter_with_mocked_transport(monkeypatch):
    def recall(body):
        value = next(m["content"] for m in body["messages"] if m["role"] == "tool")
        return say(value)

    provider = MockProvider([call("read_probe_value"), recall, recall, recall])
    monkeypatch.setattr("milai.probe.provider", lambda _: provider.model)
    result = asyncio.run(
        probe(
            Settings("https://model.invalid/v1", "mock-model", "test-only"),
            Telemetry(enabled=False),
        )
    )
    assert result["tool_round_trip"] == "passed"
    assert result["conversation_continuation"] == "passed"
    assert json.loads(json.dumps(result))["usage_first"]["requests"] == 2
    assert [r["reasoning_effort"] for r in provider.requests] == [
        "low",
        "low",
        "low",
        "high",
    ]
