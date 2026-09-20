"""Mock provider transport. These responses do NOT validate tutoring quality."""

import json

import httpx2 as httpx
from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI


def call(name, **arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "replaced-by-transport",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def calls(*tool_calls):
    """Return several independent function calls from one model generation."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "replaced-by-transport",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for name, arguments in tool_calls
        ],
    }


def say(text):
    return {"role": "assistant", "content": text}


class MockProvider:
    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []
        self.client = AsyncOpenAI(
            api_key="test-only",
            base_url="https://model.invalid/v1",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handle)),
        )
        self.model = OpenAIChatCompletionsModel("mock-model", self.client)

    async def handle(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        step = self.steps.pop(0)
        message = step(body) if callable(step) else step
        if message.get("tool_calls"):
            for index, tool_call in enumerate(message["tool_calls"]):
                tool_call["id"] = f"call-{len(self.requests)}-{index}"
        return httpx.Response(
            200,
            json={
                "id": f"chat-{len(self.requests)}",
                "object": "chat.completion",
                "created": 1,
                "model": "mock-model",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls"
                        if message.get("tool_calls")
                        else "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )
