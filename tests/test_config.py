import pytest

from milai.config import Settings


def test_gemini_defaults_ignore_old_provider(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.setenv("NVIDIA_MODEL", "old-model")
    monkeypatch.setenv("NVIDIA_API_KEY", "old-secret")
    settings = Settings.load()
    assert settings.model == "gemini-3.5-flash-lite"
    assert (
        settings.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    assert settings.api_key == "test-secret"
    assert "test-secret" not in repr(settings)


def test_missing_gemini_key_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "old-secret")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Settings.load()
