"""Test double for LLMClient."""

from collections.abc import Iterable
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ValidationError

from milai.llm.errors import LLMError, LLMParseError
from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)
type ScriptedResponse = BaseModel | str | dict[str, object] | Exception


class ScriptedLLMClient:
    def __init__(self, responses: Iterable[ScriptedResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[list[Message]] = []
        self.call_kwargs: list[dict[str, Any]] = []
        self.response_models: list[type[BaseModel] | None] = []

    @overload
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T],
        **kwargs: Any,
    ) -> T: ...

    @overload
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: None = None,
        **kwargs: Any,
    ) -> str: ...

    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T] | None = None,
        **kwargs: Any,
    ) -> T | str:
        self.calls.append(messages)
        self.call_kwargs.append(kwargs)
        self.response_models.append(response_model)
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        if response_model is None:
            content = str(result).strip()
            if not content:
                raise LLMError("empty completion response")
            return content
        raw_response = (
            result.model_dump_json() if isinstance(result, BaseModel) else str(result)
        )
        payload = result.model_dump() if isinstance(result, BaseModel) else result
        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            raise LLMParseError(str(exc), raw_response=raw_response) from exc

    async def chat(self, messages: list[Message], **kwargs: Any) -> str:
        self.calls.append(messages)
        self.call_kwargs.append(kwargs)
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return str(result)
