"""LiteLLM-backed LLM client."""

from typing import Any, TypeVar

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

    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T],
    ) -> T:
        try:
            raw = await self._acompletion(messages, response_format=response_model)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        try:
            return response_model.model_validate_json(raw)
        except ValidationError as exc:
            raise LLMParseError(str(exc), raw_response=raw) from exc

    async def chat(self, messages: list[Message]) -> str:
        try:
            content = (await self._acompletion(messages)).strip()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        if not content:
            raise LLMError("empty chat response")
        return content

    async def _acompletion(self, messages: list[Message], **kwargs: Any) -> str:
        if self._config.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self._config.reasoning_effort
            kwargs["allowed_openai_params"] = ["reasoning_effort"]
        response = await litellm.acompletion(
            model=self._config.model,
            messages=[
                {"role": message.role.value, "content": message.content}
                for message in messages
            ],
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            max_tokens=self._config.max_tokens,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            num_retries=DEFAULT_NUM_RETRIES,
            **kwargs,
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
