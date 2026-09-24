"""A live compatibility test; no mocked fallback."""

import asyncio
import json
import secrets

from agents import Agent, ModelSettings, RunConfig, Runner, function_tool
from openai.types.shared import Reasoning
from pydantic import TypeAdapter

from milai.config import Settings, provider
from milai.observability import Telemetry


async def probe(settings: Settings, telemetry: Telemetry) -> dict:
    nonce = secrets.token_hex(8)
    calls = []

    @function_tool
    async def read_probe_value() -> str:
        """Read the opaque test value. Never guess it."""
        calls.append(True)
        return nonce

    model = provider(settings)
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
        return {
            "kind": "live",
            "endpoint": settings.base_url,
            "model": settings.model,
            "tool_round_trip": "passed",
            "conversation_continuation": "passed",
            "reasoning_efforts": ["low", "high"],
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
