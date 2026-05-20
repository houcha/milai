"""Protocol for provider-neutral LLM calls."""

from typing import Any, Protocol, TypeVar, overload

from pydantic import BaseModel

from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    @overload
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T],
        **kwargs: Any,
    ) -> T:
        """Return a structured response validated by response_model."""

    @overload
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: None = None,
        **kwargs: Any,
    ) -> str:
        """Return raw text when no response_model is supplied."""

    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T] | None = None,
        **kwargs: Any,
    ) -> T | str:
        """Return raw text or a structured response."""

    async def chat(self, messages: list[Message], **kwargs: Any) -> str:
        """Return free-form assistant text."""
