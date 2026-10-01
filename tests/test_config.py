import asyncio
from types import SimpleNamespace

import pytest
from agents import OpenAIResponsesModel

from milai.config import Settings, provider, providers
from milai.observability import Telemetry
from milai.store import Store
from milai.tutor import Tutor


def test_openai_defaults_ignore_old_provider(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    for name in (
        "OPENAI_LESSON_MODEL",
        "OPENAI_LESSON_REASONING_EFFORT",
        "OPENAI_LESSON_SERVICE_TIER",
        "MILAI_LESSON_MAX_OUTPUT_TOKENS",
        "OPENAI_REVIEW_MODEL",
        "OPENAI_REVIEW_REASONING_EFFORT",
        "MILAI_REVIEW_MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "old-secret")
    settings = Settings.load()
    assert settings.model == "gpt-6.1-sol"
    assert settings.lesson_model == "gpt-6.1-sol"
    assert settings.lesson_reasoning_effort == "low"
    assert settings.lesson_service_tier == "fast"
    assert settings.lesson_max_output_tokens == 32768
    assert settings.review_model == "gpt-6-luna"
    assert settings.review_reasoning_effort == "medium"
    assert settings.review_max_output_tokens == 8192
    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.api_key == "test-secret"
    assert settings.request_timeout == 300
    assert settings.timeout == 300
    assert "test-secret" not in repr(settings)
    model = provider(settings)
    assert isinstance(model, OpenAIResponsesModel)
    assert model._client.max_retries == 0


def test_lesson_generation_overrides_and_shared_client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "custom-chat")
    monkeypatch.setenv("OPENAI_LESSON_MODEL", "custom-generation")
    monkeypatch.setenv("OPENAI_LESSON_REASONING_EFFORT", "high")
    monkeypatch.setenv("OPENAI_LESSON_SERVICE_TIER", "priority")
    monkeypatch.setenv("MILAI_LESSON_MAX_OUTPUT_TOKENS", "16000")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "custom-review")
    monkeypatch.setenv("OPENAI_REVIEW_REASONING_EFFORT", "high")
    monkeypatch.setenv("MILAI_REVIEW_MAX_OUTPUT_TOKENS", "6000")
    settings = Settings.load()
    assert settings.model == "custom-chat"
    assert settings.lesson_model == "custom-generation"
    assert settings.lesson_reasoning_effort == "high"
    assert settings.lesson_service_tier == "priority"
    assert settings.lesson_max_output_tokens == 16000
    assert settings.review_model == "custom-review"
    assert settings.review_reasoning_effort == "high"
    assert settings.review_max_output_tokens == 6000
    chat, generation = providers(settings)
    assert chat.model == "custom-chat"
    assert generation.model == "custom-generation"
    assert chat._client is generation._client


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("OPENAI_LESSON_MODEL", " ", "OPENAI_LESSON_MODEL"),
        ("OPENAI_LESSON_REASONING_EFFORT", "ultra", "REASONING_EFFORT"),
        ("OPENAI_LESSON_SERVICE_TIER", " ", "SERVICE_TIER"),
        ("MILAI_LESSON_MAX_OUTPUT_TOKENS", "0", "MAX_OUTPUT_TOKENS"),
        ("OPENAI_REVIEW_MODEL", " ", "OPENAI_REVIEW_MODEL"),
        ("OPENAI_REVIEW_REASONING_EFFORT", "minimal", "REASONING_EFFORT"),
        ("MILAI_REVIEW_MAX_OUTPUT_TOKENS", "0", "MAX_OUTPUT_TOKENS"),
        ("MILAI_REVIEW_MAX_OUTPUT_TOKENS", "broken", "MAX_OUTPUT_TOKENS"),
    ],
)
def test_invalid_lesson_generation_config(monkeypatch, tmp_path, name, value, expected):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=expected):
        Settings.load()


def test_missing_openai_key_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "old-secret")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings.load()


def test_tutor_closes_shared_client_once(tmp_path):
    class Client:
        close_calls = 0

        async def close(self):
            self.close_calls += 1

    client = Client()
    store = Store(tmp_path / "shared-client.db")
    tutor = Tutor(
        Settings("https://model.invalid", "chat", "test"),
        store,
        Telemetry(enabled=False),
        model=SimpleNamespace(_client=client),
        generation_model=SimpleNamespace(_client=client),
        review_model=SimpleNamespace(_client=client),
    )
    asyncio.run(tutor.close())
    assert client.close_calls == 1
    store.close()
