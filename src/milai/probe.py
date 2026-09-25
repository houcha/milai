"""A live compatibility test; no mocked fallback."""

import asyncio
import json
import secrets

from agents import Agent, ModelSettings, RunConfig, Runner, function_tool
from openai.types.responses import ResponseCompletedEvent
from openai.types.shared import Reasoning
from pydantic import BaseModel, TypeAdapter

from milai.config import Settings, providers
from milai.observability import Telemetry


class LessonProbeResult(BaseModel):
    nonce: str


async def probe(settings: Settings, telemetry: Telemetry) -> dict:
    nonce = secrets.token_hex(8)
    calls = []

    @function_tool
    async def read_probe_value() -> str:
        """Read the opaque test value. Never guess it."""
        calls.append(True)
        return nonce

    model, lesson_model = providers(settings)
    try:
        agent = Agent(
            name="endpoint-probe",
            instructions=(
                "When asked for the value, call read_probe_value exactly once, then "
                "reply with its exact value. If asked to recall it, use conversation "
                "history and do not call the tool again."
            ),
            model=model,
            tools=[read_probe_value],
            model_settings=ModelSettings(
                max_tokens=4096,
                reasoning=Reasoning(effort="low"),
                store=False,
                response_include=["reasoning.encrypted_content"],
            ),
        )
        config = RunConfig(
            workflow_name="model-compatibility-probe",
            trace_include_sensitive_data=True,
        )
        with telemetry.turn("synthetic-probe", "synthetic-probe", "probe-v1"):
            async with asyncio.timeout(settings.timeout):
                first = await Runner.run(
                    agent, "Read the value now.", max_turns=4, run_config=config
                )
                if len(calls) != 1 or nonce not in str(first.final_output):
                    raise RuntimeError("Tool round trip failed verification")
                continued = await Runner.run(
                    agent,
                    first.to_input_list()
                    + [{"role": "user", "content": "Recall the same value, no tools."}],
                    max_turns=2,
                    run_config=config,
                )
                if len(calls) != 1 or nonce not in str(continued.final_output):
                    raise RuntimeError("Conversation continuation failed verification")
                deliberate = await Runner.run(
                    agent.clone(
                        tools=[],
                        model_settings=ModelSettings(
                            max_tokens=4096,
                            reasoning=Reasoning(effort="high"),
                            store=False,
                            response_include=["reasoning.encrypted_content"],
                        ),
                    ),
                    continued.to_input_list()
                    + [{"role": "user", "content": "Return the same value once more."}],
                    max_turns=1,
                    run_config=config,
                )
                if nonce not in str(deliberate.final_output):
                    raise RuntimeError("High-effort request failed verification")
                lesson_agent = Agent(
                    name="lesson-generation-probe",
                    instructions=(
                        "Return the nonce from the user message exactly in the "
                        "structured nonce field."
                    ),
                    model=lesson_model,
                    output_type=LessonProbeResult,
                    model_settings=ModelSettings(
                        max_tokens=settings.lesson_max_output_tokens,
                        reasoning=Reasoning(effort=settings.lesson_reasoning_effort),
                        extra_body={"service_tier": settings.lesson_service_tier},
                        store=False,
                        response_include=["reasoning.encrypted_content"],
                    ),
                )
                generation = Runner.run_streamed(
                    lesson_agent,
                    f"Return this nonce: {nonce}",
                    max_turns=1,
                    run_config=config,
                )
                returned_tier = None
                async for event in generation.stream_events():
                    if event.type == "raw_response_event" and isinstance(
                        event.data, ResponseCompletedEvent
                    ):
                        returned_tier = event.data.response.service_tier
                if not isinstance(generation.final_output, LessonProbeResult):
                    raise RuntimeError("Lesson structured output failed verification")
                if generation.final_output.nonce != nonce:
                    raise RuntimeError("Lesson structured output was incorrect")
        return {
            "kind": "live",
            "endpoint": settings.base_url,
            "model": settings.model,
            "lesson_model": settings.lesson_model,
            "tool_round_trip": "passed",
            "conversation_continuation": "passed",
            "reasoning_efforts": ["low", "high", settings.lesson_reasoning_effort],
            "lesson_structured_output": "passed",
            "lesson_requested_service_tier": settings.lesson_service_tier,
            "lesson_returned_service_tier": returned_tier,
            "usage_first": TypeAdapter(type(first.context_wrapper.usage)).dump_python(
                first.context_wrapper.usage, mode="json"
            ),
            "trace_id": telemetry.last_trace_id,
            "langfuse_configured": telemetry.client is not None,
        }
    finally:
        await model._client.close()
        telemetry.flush()


def main():
    settings = Settings.load()
    telemetry = Telemetry()
    print(json.dumps(asyncio.run(probe(settings, telemetry)), indent=2))


if __name__ == "__main__":
    main()
