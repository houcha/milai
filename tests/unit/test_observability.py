import os
import sys
from contextlib import contextmanager
from types import SimpleNamespace


def test_langfuse_tracing_disabled_without_credentials(monkeypatch, caplog) -> None:
    import litellm

    from milai.observability import NoopObservability, configure_observability

    caplog.set_level("INFO")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(litellm, "callbacks", ["other", "langfuse_otel"])

    observability = configure_observability()

    assert isinstance(observability, NoopObservability)
    assert litellm.callbacks == ["other"]
    assert "Langfuse tracing disabled" in caplog.text


def test_langfuse_tracing_enabled_with_credentials(monkeypatch, caplog) -> None:
    import litellm

    from milai.observability import LangfuseObservability, configure_observability

    client = _FakeLangfuseClient()
    _install_fake_langfuse(monkeypatch, client)
    caplog.set_level("INFO")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    monkeypatch.delenv("USE_OTEL_LITELLM_REQUEST_SPAN", raising=False)
    monkeypatch.setattr(litellm, "callbacks", ["other"])

    observability = configure_observability()

    assert isinstance(observability, LangfuseObservability)
    assert litellm.callbacks == ["other", "langfuse_otel"]
    assert "Langfuse tracing enabled" in caplog.text
    assert os.environ["USE_OTEL_LITELLM_REQUEST_SPAN"] == "true"

    observability.shutdown()
    assert client.shutdown_called is True


def test_langfuse_callback_setup_is_deterministic(monkeypatch) -> None:
    import litellm

    from milai.observability import configure_observability

    _install_fake_langfuse(monkeypatch, _FakeLangfuseClient())
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    monkeypatch.setattr(litellm, "callbacks", ["langfuse_otel"])

    configure_observability()
    configure_observability()

    assert litellm.callbacks == ["langfuse_otel"]


def test_langfuse_tracing_disabled_without_base_url(monkeypatch) -> None:
    import litellm

    from milai.observability import NoopObservability, configure_observability

    _install_fake_langfuse(monkeypatch, _FakeLangfuseClient())
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_OTEL_HOST", "https://cloud.langfuse.com")
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setattr(litellm, "callbacks", ["other", "langfuse_otel"])

    observability = configure_observability()

    assert isinstance(observability, NoopObservability)
    assert litellm.callbacks == ["other"]


def test_langfuse_base_url_configures_litellm_otel_host(monkeypatch) -> None:
    from milai.observability import configure_observability

    _install_fake_langfuse(monkeypatch, _FakeLangfuseClient())
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_OTEL_HOST", raising=False)

    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://self-hosted.example")
    configure_observability()

    assert os.environ["LANGFUSE_OTEL_HOST"] == "https://self-hosted.example"

    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://canonical.example")
    monkeypatch.setenv("LANGFUSE_OTEL_HOST", "https://stale.example")

    configure_observability()

    assert os.environ["LANGFUSE_OTEL_HOST"] == "https://canonical.example"


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.shutdown_called = False

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        _ = kwargs
        yield SimpleNamespace(update=lambda **update_kwargs: None)

    def shutdown(self) -> None:
        self.shutdown_called = True


def _install_fake_langfuse(monkeypatch, client: _FakeLangfuseClient) -> None:
    @contextmanager
    def propagate_attributes(**kwargs):
        _ = kwargs
        yield

    monkeypatch.setitem(
        sys.modules,
        "langfuse",
        SimpleNamespace(
            get_client=lambda: client,
            propagate_attributes=propagate_attributes,
        ),
    )
