"""LiteLLM-backed LLM client."""

from typing import Any, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from milai.config import LLMConfig
from milai.llm.errors import LLMError, LLMParseError
from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)
DEFAULT_TIMEOUT_SECONDS = 60


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
            response = await litellm.acompletion(
                model=self._config.model,
                messages=_to_provider_messages(messages),
                temperature=self._config.temperature,
                top_p=self._config.top_p,
                max_tokens=self._config.max_tokens,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                response_format={"type": "json_object"},
            )
            raw = _extract_content(response)
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
            response = await litellm.acompletion(
                model=self._config.model,
                messages=_to_provider_messages(messages),
                temperature=self._config.temperature,
                top_p=self._config.top_p,
                max_tokens=self._config.max_tokens,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            content = _extract_content(response).strip()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        if not content:
            raise LLMError("empty chat response")
        return content


def _to_provider_messages(messages: list[Message]) -> list[dict[str, str]]:
    return [
        {"role": message.role.value, "content": message.content} for message in messages
    ]


def _extract_content(response: Any) -> str:
    try:
        choice = response["choices"][0]
        message = choice["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("provider response did not include message content") from exc
    if not isinstance(content, str):
        raise LLMError("provider response content was not text")
    return content
