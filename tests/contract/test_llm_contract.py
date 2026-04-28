import asyncio
import inspect

import pytest
from pydantic import BaseModel


class ToyResponse(BaseModel):
    answer: str


def test_llm_client_protocol_shape_is_async() -> None:
    from milai.llm.client import LLMClient

    assert getattr(LLMClient, "_is_protocol", False)
    assert inspect.iscoroutinefunction(LLMClient.complete)
    assert inspect.iscoroutinefunction(LLMClient.chat)


def test_llm_errors_expose_retry_and_raw_response() -> None:
    from milai.llm.errors import LLMError, LLMParseError

    retryable = LLMError("temporary")
    hard_failure = LLMError("quota exhausted", retryable=False)
    parse_error = LLMParseError("bad json", raw_response="<html>")

    assert retryable.retryable is True
    assert hard_failure.retryable is False
    assert parse_error.retryable is True
    assert parse_error.raw_response == "<html>"
    assert isinstance(parse_error, LLMError)


def test_scripted_llm_client_returns_structured_and_chat_responses() -> None:
    from milai.llm.types import Message, Role
    from tests.fakes.llm_client import ScriptedLLMClient

    structured = ToyResponse(answer="hola")
    client = ScriptedLLMClient([structured, "free-form answer"])
    messages = [Message(role=Role.USER, content="translate hello")]

    async def run_script() -> None:
        assert await client.complete(messages, response_model=ToyResponse) == structured
        assert await client.chat(messages) == "free-form answer"

    asyncio.run(run_script())

    assert client.calls == [messages, messages]


def test_scripted_llm_client_raises_scripted_errors_without_retrying() -> None:
    from milai.llm.errors import LLMError
    from milai.llm.types import Message, Role
    from tests.fakes.llm_client import ScriptedLLMClient

    error = LLMError("provider unavailable")
    client = ScriptedLLMClient([error])
    messages = [Message(role=Role.USER, content="hello")]

    async def run_script() -> None:
        with pytest.raises(LLMError, match="provider unavailable"):
            await client.complete(messages, response_model=ToyResponse)

    asyncio.run(run_script())
    assert client.calls == [messages]
