import asyncio
import json

from agents import OpenAIResponsesModel

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

    def structured(body):
        message = body["input"][-1]["content"]
        return say(json.dumps({"nonce": message.rsplit(" ", 1)[-1]}))

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
            structured,
        ]
    )
    provider.service_tier = "priority"
    monkeypatch.setattr(
        "milai.probe.providers",
        lambda _: (
            provider.model,
            OpenAIResponsesModel("gpt-6-sol", provider.client),
        ),
    )
    result = asyncio.run(
        probe(
            Settings("https://model.invalid/v1", "mock-model", "test-only"),
            Telemetry(enabled=False),
        )
    )
    assert result["tool_round_trip"] == "passed"
    assert result["conversation_continuation"] == "passed"
    assert result["lesson_structured_output"] == "passed"
    assert result["lesson_returned_service_tier"] == "priority"
    assert json.loads(json.dumps(result))["usage_first"]["requests"] == 2
    assert [r["reasoning"]["effort"] for r in provider.requests] == [
        "low",
        "low",
        "low",
        "high",
        "low",
    ]
    assert [r["model"] for r in provider.requests] == [
        "mock-model",
        "mock-model",
        "mock-model",
        "mock-model",
        "gpt-6-sol",
    ]
    assert provider.requests[-1]["service_tier"] == "fast"
    assert provider.requests[-1]["max_output_tokens"] == 32768
    assert provider.requests[-1]["text"]["format"]["type"] == "json_schema"
    assert all(r["store"] is False for r in provider.requests)
    assert all("reasoning.encrypted_content" in r["include"] for r in provider.requests)
    assert any(
        item.get("encrypted_content") == "synthetic-encrypted-reasoning"
        for item in provider.requests[1]["input"]
    )
