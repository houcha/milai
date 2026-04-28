"""Test double for LLMClient."""

from collections.abc import Iterable
from typing import TypeVar

from pydantic import BaseModel

from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)


class ScriptedLLMClient:
    def __init__(self, responses: Iterable[BaseModel | str | Exception]) -> None:
        self._responses = iter(responses)
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T],
    ) -> T:
        self.calls.append(messages)
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, response_model):
            return result
        return response_model.model_validate(result)

    async def chat(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return str(result)
