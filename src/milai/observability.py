"""Runtime observability setup and tracing boundaries."""

import logging
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

import litellm

from milai.models.session import LearningSession

logger = logging.getLogger(__name__)
LANGFUSE_CALLBACK = "langfuse_otel"


class Observation(Protocol):
    def update(self, **kwargs: Any) -> None:
        """Update the active observation."""


class Observability(Protocol):
    def span(
        self, name: str, *, input: dict[str, Any] | None = None
    ) -> AbstractContextManager[Observation]:
        """Create a current observation span."""

    def state_dispatch(
        self, session: LearningSession
    ) -> AbstractContextManager[Observation]:
        """Create a current observation span for one state dispatch."""

    def shutdown(self) -> None:
        """Flush buffered observations and release tracing resources."""


class _NoopObservation:
    def update(self, **kwargs: Any) -> None:
        _ = kwargs


class NoopObservability(Observability):
    @contextmanager
    def span(
        self, name: str, *, input: dict[str, Any] | None = None
    ) -> Iterator[Observation]:
        _ = (name, input)
        yield _NoopObservation()

    @contextmanager
    def state_dispatch(self, session: LearningSession) -> Iterator[Observation]:
        _ = session
        yield _NoopObservation()

    def shutdown(self) -> None:
        pass


class LangfuseObservability(Observability):
    def __init__(self, client: Any, propagate_attributes: Any) -> None:
        self._client = client
        self._propagate_attributes = propagate_attributes

    def span(
        self, name: str, *, input: dict[str, Any] | None = None
    ) -> AbstractContextManager[Observation]:
        kwargs: dict[str, Any] = {"as_type": "span", "name": name}
        if input is not None:
            kwargs["input"] = input
        return self._client.start_as_current_observation(**kwargs)

    @contextmanager
    def state_dispatch(self, session: LearningSession) -> Iterator[Observation]:
        state = session.app.type
        with (
            self.span(
                f"milai.state.{state}",
                input={"state": state, "sessionId": session.id},
            ) as observation,
            self._propagate_attributes(
                session_id=session.id,
                tags=["milai", state],
                trace_name="milai.learning_session",
                metadata={"milaiState": state},
            ),
        ):
            yield observation

    def shutdown(self) -> None:
        self._client.shutdown()


def configure_observability() -> Observability:
    """Configure Langfuse tracing when credentials are present."""
    if not (
        os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
        and os.environ.get("LANGFUSE_BASE_URL")
    ):
        _disable_litellm_langfuse_callback()
        logger.info("Langfuse tracing disabled")
        return NoopObservability()

    # Sync LANGFUSE_OTEL_HOST with LANGFUSE_BASE_URL
    os.environ["LANGFUSE_OTEL_HOST"] = os.environ["LANGFUSE_BASE_URL"]
    os.environ.setdefault("USE_OTEL_LITELLM_REQUEST_SPAN", "true")

    _enable_litellm_langfuse_callback()
    from langfuse import get_client, propagate_attributes

    logger.info("Langfuse tracing enabled")
    return LangfuseObservability(get_client(), propagate_attributes)


def _enable_litellm_langfuse_callback() -> None:
    callbacks = _litellm_callbacks()
    if LANGFUSE_CALLBACK not in callbacks:
        callbacks.append(LANGFUSE_CALLBACK)
    litellm.callbacks = callbacks  # ty: ignore[invalid-assignment]


def _disable_litellm_langfuse_callback() -> None:
    litellm.callbacks = [  # ty: ignore[invalid-assignment]
        callback for callback in _litellm_callbacks() if callback != LANGFUSE_CALLBACK
    ]


def _litellm_callbacks() -> list[str]:
    callbacks = getattr(litellm, "callbacks", [])
    if callbacks is None:
        return []
    return list(callbacks)
