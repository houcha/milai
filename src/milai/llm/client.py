"""Protocol for provider-neutral LLM calls."""

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T],
        **kwargs: Any,
    ) -> T:
        """Return a structured response validated by response_model."""

    async def chat(self, messages: list[Message], **kwargs: Any) -> str:
        """Return free-form assistant text."""
