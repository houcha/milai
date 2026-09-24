import pytest
from agents import OpenAIResponsesModel

from milai.config import Settings, provider


def test_openai_defaults_ignore_old_provider(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "old-secret")
    settings = Settings.load()
    assert settings.model == "gpt-6-luna"
    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.api_key == "test-secret"
    assert settings.request_timeout == 300
    assert settings.timeout == 300
    assert "test-secret" not in repr(settings)
    model = provider(settings)
    assert isinstance(model, OpenAIResponsesModel)
    assert model._client.max_retries == 0


def test_missing_openai_key_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "old-secret")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings.load()
