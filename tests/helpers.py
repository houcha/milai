"""Mock provider transport. These responses do NOT validate tutoring quality."""

import json

import httpx2 as httpx
from agents import OpenAIResponsesModel
from openai import AsyncOpenAI


def call(name, **arguments):
    return {
        "type": "function_call",
        "id": "replaced-by-transport",
        "call_id": "replaced-by-transport",
        "name": name,
        "arguments": json.dumps(arguments),
        "status": "completed",
    }


def say(text):
    return {
        "type": "message",
        "id": "replaced-by-transport",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


class MockProvider:
    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []
        self.client = AsyncOpenAI(
            api_key="test-only",
            base_url="https://model.invalid/v1",
            max_retries=0,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(self.handle), trust_env=False
            ),
        )
        # The SDK's async platform probe uses a thread executor; setting this in
        # the mock keeps short-lived asyncio.run tests from waiting on its shutdown.
        self.client._platform = "Linux"
        self.model = OpenAIResponsesModel("mock-model", self.client)

    async def handle(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        step = self.steps.pop(0)
        result = step(body) if callable(step) else step
        items = [
            item.copy() for item in (result if isinstance(result, list) else [result])
        ]
        for index, item in enumerate(items):
            item["id"] = f"item-{len(self.requests)}-{index}"
            if item["type"] == "function_call":
                item["call_id"] = f"call-{len(self.requests)}-{index}"
        return httpx.Response(
            200,
            json={
                "id": f"resp-{len(self.requests)}",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "mock-model",
                "output": items,
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )
