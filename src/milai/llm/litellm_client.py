"""LiteLLM-backed LLM client."""

from typing import Any, TypeVar, overload

import litellm
from pydantic import BaseModel, ValidationError

from milai.config import LLMConfig
from milai.llm.errors import LLMError, LLMParseError
from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_NUM_RETRIES = 5

litellm.suppress_debug_info = True  # ty: ignore[invalid-assignment]


class LiteLLMClient:
    """Concrete LLMClient backed by one resolved LiteLLM profile."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    @overload
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T],
        **litellm_kwargs: Any,
    ) -> T: ...

    @overload
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: None = None,
        **litellm_kwargs: Any,
    ) -> str: ...

    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T] | None = None,
        **litellm_kwargs: Any,
    ) -> T | str:
        try:
            if response_model is not None:
                litellm_kwargs["response_format"] = response_model
            raw = await self._acompletion(messages, **litellm_kwargs)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        if response_model is None:
            content = raw.strip()
            if not content:
                raise LLMError("empty completion response")
            return content

        try:
            return response_model.model_validate_json(raw)
        except ValidationError as exc:
            raise LLMParseError(str(exc), raw_response=raw) from exc

    async def chat(self, messages: list[Message], **litellm_kwargs: Any) -> str:
        try:
            content = (await self._acompletion(messages, **litellm_kwargs)).strip()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        if not content:
            raise LLMError("empty chat response")
        return content

    async def _acompletion(self, messages: list[Message], **litellm_kwargs: Any) -> str:
        completion_kwargs: dict[str, Any] = {
            "timeout": DEFAULT_TIMEOUT_SECONDS,
            "num_retries": DEFAULT_NUM_RETRIES,
        }
        completion_kwargs.update(self._config.model_dump(exclude_none=True))
        completion_kwargs.update(litellm_kwargs)
        response = await litellm.acompletion(
            messages=[
                {"role": message.role.value, "content": message.content}
                for message in messages
            ],
            **completion_kwargs,
        )
        try:
            choice = response["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("provider response did not include message content") from exc
        if not isinstance(content, str):
            raise LLMError("provider response content was not text")
        return content
