import asyncio
import json

from milai.config import Settings
from milai.observability import Telemetry
from milai.probe import probe
from tests.helpers import MockProvider, call, say


def test_probe_exercises_real_adapter_with_mocked_transport(monkeypatch):
    def recall(body):
        value = next(
            item["output"]
            for item in body["input"]
            if item.get("type") == "function_call_output"
        )
        return say(value)

    provider = MockProvider(
        [
            [
                {
                    "type": "reasoning",
                    "summary": [],
                    "encrypted_content": "synthetic-encrypted-reasoning",
                },
                call("read_probe_value"),
            ],
            recall,
            recall,
            recall,
        ]
    )
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
    assert [r["reasoning"]["effort"] for r in provider.requests] == [
        "low",
        "low",
        "low",
        "high",
    ]
    assert all(r["store"] is False for r in provider.requests)
    assert all("reasoning.encrypted_content" in r["include"] for r in provider.requests)
    assert any(
        item.get("encrypted_content") == "synthetic-encrypted-reasoning"
        for item in provider.requests[1]["input"]
    )
