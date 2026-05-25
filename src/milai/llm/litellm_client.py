"""LiteLLM-backed LLM client."""

import json
import logging
from typing import Any, TypeVar, overload

import litellm
from pydantic import BaseModel, ValidationError

from milai.config import LLMConfig
from milai.llm.errors import LLMError, LLMParseError
from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_NUM_RETRIES = 5
logger = logging.getLogger(__name__)

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
        if response_model is not None:
            litellm_kwargs["response_format"] = response_model
        payload = self._completion_payload(messages, **litellm_kwargs)
        try:
            raw = await self._acompletion(payload)
        except Exception as exc:
            logger.error(
                "LLM completion failed before response parsing.\n"
                "Payload:\n"
                "%s\n"
                "Error:\n"
                "%s",
                _format_payload_for_log(payload),
                str(exc),
                exc_info=not isinstance(exc, LLMError),
            )
            if isinstance(exc, LLMError):
                raise
            raise LLMError(str(exc)) from exc

        if response_model is None:
            content = raw.strip()
            if not content:
                logger.error(
                    "LLM completion returned an empty text response.\nPayload:\n%s",
                    _format_payload_for_log(payload),
                )
                raise LLMError("empty completion response")
            return content

        try:
            return response_model.model_validate_json(raw)
        except ValidationError as exc:
            logger.error(
                "LLM completion response could not be parsed as %s.\n"
                "Payload:\n"
                "%s\n"
                "Raw response:\n"
                "%s\n"
                "Expected response:\n"
                "%s\n"
                "Validation error:\n"
                "%s",
                response_model.__name__,
                _format_payload_for_log(payload),
                _format_raw_response_for_log(raw),
                _format_response_schema_for_log(response_model),
                str(exc),
            )
            raise LLMParseError(
                f"failed to parse LLM response as {response_model.__name__}",
                raw_response=raw,
            ) from exc

    async def chat(self, messages: list[Message], **litellm_kwargs: Any) -> str:
        payload = self._completion_payload(messages, **litellm_kwargs)
        try:
            content = (await self._acompletion(payload)).strip()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        if not content:
            raise LLMError("empty chat response")
        return content

    def _completion_payload(
        self, messages: list[Message], **litellm_kwargs: Any
    ) -> dict[str, Any]:
        completion_kwargs: dict[str, Any] = {
            "timeout": DEFAULT_TIMEOUT_SECONDS,
            "num_retries": DEFAULT_NUM_RETRIES,
        }
        completion_kwargs.update(self._config.model_dump(exclude_none=True))
        completion_kwargs.update(litellm_kwargs)
        return {
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in messages
            ],
            **completion_kwargs,
        }

    async def _acompletion(self, payload: dict[str, Any]) -> str:
        response = await litellm.acompletion(**payload)
        try:
            choice = response["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("provider response did not include message content") from exc
        if not isinstance(content, str):
            raise LLMError("provider response content was not text")
        return content


def _format_payload_for_log(payload: dict[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=4)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except TypeError:
        if isinstance(value, dict):
            return {key: _json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return repr(value)
    return value


def _format_raw_response_for_log(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=4)
    except json.JSONDecodeError:
        return raw


def _format_response_schema_for_log(response_model: type[BaseModel]) -> str:
    return json.dumps(response_model.model_json_schema(), indent=4)
