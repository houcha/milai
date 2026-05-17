import asyncio

import pytest
from pydantic import BaseModel


class ToyResponse(BaseModel):
    answer: str


def test_litellm_client_parses_structured_json(monkeypatch) -> None:
    from milai.config import LLMConfig
    from milai.llm.litellm_client import LiteLLMClient
    from milai.llm.types import Message, Role

    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"answer":"hola"}'}}]}

    monkeypatch.setattr(
        "milai.llm.litellm_client.litellm.acompletion", fake_acompletion
    )
    client = LiteLLMClient(
        LLMConfig(model="test-model", temperature=0.1, top_p=0.9, max_tokens=50)
    )

    result = asyncio.run(
        client.complete(
            [Message(role=Role.USER, content="translate hello")],
            response_model=ToyResponse,
        )
    )

    assert result == ToyResponse(answer="hola")
    assert calls[0]["model"] == "test-model"
    assert calls[0]["response_format"] is ToyResponse
    assert calls[0]["reasoning_effort"] == "none"
    assert calls[0]["allowed_openai_params"] == ["reasoning_effort"]


def test_litellm_client_omits_reasoning_effort_when_configured_none(
    monkeypatch,
) -> None:
    from milai.config import LLMConfig
    from milai.llm.litellm_client import LiteLLMClient
    from milai.llm.types import Message, Role

    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": "hola"}}]}

    monkeypatch.setattr(
        "milai.llm.litellm_client.litellm.acompletion", fake_acompletion
    )
    client = LiteLLMClient(LLMConfig(model="test-model", reasoning_effort=None))

    result = asyncio.run(client.chat([Message(role=Role.USER, content="hello")]))

    assert result == "hola"
    assert "reasoning_effort" not in calls[0]
    assert "allowed_openai_params" not in calls[0]


def test_litellm_client_respects_explicit_reasoning_effort(monkeypatch) -> None:
    from milai.config import LLMConfig
    from milai.llm.litellm_client import LiteLLMClient
    from milai.llm.types import Message, Role

    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": "hola"}}]}

    monkeypatch.setattr(
        "milai.llm.litellm_client.litellm.acompletion", fake_acompletion
    )
    client = LiteLLMClient(LLMConfig(model="test-model", reasoning_effort="minimal"))

    result = asyncio.run(client.chat([Message(role=Role.USER, content="hello")]))

    assert result == "hola"
    assert calls[0]["reasoning_effort"] == "minimal"
    assert calls[0]["allowed_openai_params"] == ["reasoning_effort"]


def test_litellm_client_wraps_parse_and_provider_errors(monkeypatch) -> None:
    from milai.config import LLMConfig
    from milai.llm.errors import LLMError, LLMParseError
    from milai.llm.litellm_client import LiteLLMClient
    from milai.llm.types import Message, Role

    async def invalid_json(**kwargs):
        return {"choices": [{"message": {"content": "not-json"}}]}

    monkeypatch.setattr("milai.llm.litellm_client.litellm.acompletion", invalid_json)
    client = LiteLLMClient(LLMConfig(model="test-model"))

    with pytest.raises(LLMParseError) as parse_exc:
        asyncio.run(
            client.complete(
                [Message(role=Role.USER, content="hello")], response_model=ToyResponse
            )
        )
    assert parse_exc.value.retryable is True
    assert parse_exc.value.raw_response == "not-json"

    async def provider_failure(**kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        "milai.llm.litellm_client.litellm.acompletion", provider_failure
    )

    with pytest.raises(LLMError, match="timed out") as error_exc:
        asyncio.run(client.chat([Message(role=Role.USER, content="hello")]))
    assert error_exc.value.retryable is True


def test_litellm_client_rejects_empty_chat_response(monkeypatch) -> None:
    from milai.config import LLMConfig
    from milai.llm.errors import LLMError
    from milai.llm.litellm_client import LiteLLMClient
    from milai.llm.types import Message, Role

    async def empty_response(**kwargs):
        return {"choices": [{"message": {"content": "   "}}]}

    monkeypatch.setattr("milai.llm.litellm_client.litellm.acompletion", empty_response)
    client = LiteLLMClient(LLMConfig(model="test-model"))

    with pytest.raises(LLMError, match="empty"):
        asyncio.run(client.chat([Message(role=Role.USER, content="hello")]))
