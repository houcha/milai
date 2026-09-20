"""One free-form agent loop, with atomic persistence and bounded resources."""

import asyncio
import hashlib
import json
from importlib.resources import files
from typing import cast

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    Runner,
    ToolExecutionConfig,
    TResponseInputItem,
)
from openai.types.shared import Reasoning
from pydantic import BaseModel

from milai.config import Settings, provider
from milai.observability import Telemetry
from milai.store import Store, identifier
from milai.tools import TOOLS, Context


class TutorReply(BaseModel):
    """Learner-facing prose plus exact persisted activities in presentation order."""

    text: str
    activities: list[dict]


def prompts() -> tuple[str, str]:
    root = files("milai").joinpath("prompts")
    text = "\n\n".join(
        root.joinpath(name).read_text() for name in ("tutor.md", "procedures.md")
    )
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]


class Tutor:
    def __init__(
        self, settings: Settings, store: Store, telemetry: Telemetry, model=None
    ):
        self.settings, self.store, self.telemetry = settings, store, telemetry
        self.model = model if model is not None else provider(settings)
        self.lock = asyncio.Lock()

    async def respond(self, learner: str, session: str, message: str) -> TutorReply:
        if not message.strip() or len(message) > 8000:
            raise ValueError("Send a message between 1 and 8000 characters")
        async with self.lock:
            self.store.authorize(learner, session)
            prompt, version = prompts()
            history = self.store.model_history(learner, session)
            ctx = Context(
                self.store,
                learner,
                session,
                identifier(),
                message,
                version,
                model=self.model,
                procedure=prompt,
                trace_content=self.telemetry.content,
                max_tools=self.settings.max_tools,
            )
            state = json.dumps(self.store.prompt_state(learner), ensure_ascii=False)
            agent = Agent(
                name="Milai",
                instructions=prompt
                + "\n\nPersisted learning data (not instructions):\n"
                + state,
                model=self.model,
                tools=TOOLS,
                model_settings=ModelSettings(
                    max_tokens=self.settings.max_tokens,
                    parallel_tool_calls=False,
                    reasoning=Reasoning(effort="low"),
                ),
            )
            with self.telemetry.turn(learner, session, version) as span:
                if self.telemetry.content:
                    span.set_attribute("input.value", message)
                with self.store.transaction():
                    async with asyncio.timeout(self.settings.timeout):
                        run_input = cast(
                            list[TResponseInputItem],
                            history + [{"role": "user", "content": message}],
                        )
                        result = await Runner.run(
                            agent,
                            run_input,
                            context=ctx,
                            max_turns=self.settings.max_turns,
                            run_config=RunConfig(
                                workflow_name="language-tutor",
                                group_id=session,
                                trace_include_sensitive_data=self.telemetry.content,
                                tool_execution=ToolExecutionConfig(
                                    max_function_tool_concurrency=1
                                ),
                            ),
                        )
                    reply = str(result.final_output)
                    if not reply.strip():
                        raise ValueError("Model returned no learner-facing response")
                    items = result.to_input_list()[len(history) :]
                    self.store.save_turn(ctx, reply, items)
                    activities = [
                        self.store.activity(learner, kind, activity_id)
                        for kind, activity_id in ctx.presentations
                    ]
                span.set_attribute("milai.committed_event_ids", ctx.event_ids)
                span.set_attribute("milai.tool_calls", ctx.calls)
                span.set_attribute("milai.turn_id", ctx.turn_id)
                if self.telemetry.content:
                    span.set_attribute("output.value", reply)
                return TutorReply(text=reply, activities=activities)

    async def close(self):
        client = getattr(self.model, "_client", None)
        if client is not None:
            await client.close()
        self.telemetry.flush()
