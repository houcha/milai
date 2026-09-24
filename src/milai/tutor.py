"""One free-form agent loop, with atomic persistence and bounded resources."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
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
from openai.types.responses import ResponseTextDeltaEvent
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field

from milai.config import Settings, provider
from milai.observability import Telemetry
from milai.store import Store, identifier
from milai.tools import TOOLS, Context


class TutorReply(BaseModel):
    """Learner-facing prose plus exact persisted activities in presentation order."""

    text: str
    activities: list[dict]
    assessments: list[dict] = Field(default_factory=list)
    turn_id: str | None = None


def prompts() -> tuple[str, str, str]:
    root = files("milai").joinpath("prompts")
    tutor = "\n\n".join(
        root.joinpath(name).read_text() for name in ("tutor.md", "procedures.md")
    )
    planner = root.joinpath("lesson_planner.md").read_text()
    version = hashlib.sha256((tutor + "\n\n" + planner).encode()).hexdigest()[:16]
    return tutor, planner, version


class Tutor:
    def __init__(
        self, settings: Settings, store: Store, telemetry: Telemetry, model=None
    ):
        self.settings, self.store, self.telemetry = settings, store, telemetry
        self.model = model if model is not None else provider(settings)
        self.lock = asyncio.Lock()

    async def respond(
        self,
        learner: str,
        session: str,
        message: str,
        selected_exercise_id: str | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
    ) -> TutorReply:
        """Run and save one learner turn, returning prose and presented exercises.

        The turn's learning changes and transcript commit together on success.

        Args:
            learner: Owner of the session and its learning data.
            session: Session receiving this conversation turn.
            message: Learner's chat message or exercise answer.
            selected_exercise_id: ID of the exercise being answered, or ``None``
                for normal chat. It selects the exact task for assessment.

        Returns:
            The saved reply text, any exercises presented in this turn, assessments,
            and the turn ID.
        """
        if not message.strip() or len(message) > 8000:
            raise ValueError("Send a message between 1 and 8000 characters")
        async with self.lock:
            self.store.authorize(learner, session)
            scope = self.store.learning_scope(learner, session)
            if selected_exercise_id:
                status = self.store.exercise_status(
                    learner, session, selected_exercise_id
                )
                if status["completed"]:
                    raise ValueError("This exercise is already complete")
            prompt, planner_prompt, version = prompts()
            history = self.store.model_history(learner, session)
            ctx = Context(
                self.store,
                scope,
                session,
                identifier(),
                message,
                version,
                model=self.model,
                planner_instructions=planner_prompt,
                max_tools=self.settings.max_tools,
                selected_exercise_id=selected_exercise_id,
                on_progress=on_progress,
            )
            state = json.dumps(self.store.prompt_state(scope), ensure_ascii=False)
            if selected_exercise_id:
                exercise = self.store.exercise(scope, selected_exercise_id)
                state += "\nSelected exercise answer (authoritative): " + json.dumps(
                    {
                        "exercise": exercise,
                        "status": self.store.exercise_status(
                            learner, session, selected_exercise_id
                        ),
                    },
                    ensure_ascii=False,
                )
                state += (
                    "\nAssess only the selected exercise if there is enough "
                    "evidence. Clarification is allowed."
                )
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
                    store=False,
                    response_include=["reasoning.encrypted_content"],
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
                        run_config = RunConfig(
                            workflow_name="language-tutor",
                            group_id=session,
                            trace_include_sensitive_data=True,
                            tool_execution=ToolExecutionConfig(
                                max_function_tool_concurrency=1
                            ),
                        )
                        if on_progress is None:
                            result = await Runner.run(
                                agent,
                                run_input,
                                context=ctx,
                                max_turns=self.settings.max_turns,
                                run_config=run_config,
                            )
                        else:
                            result = Runner.run_streamed(
                                agent,
                                run_input,
                                context=ctx,
                                max_turns=self.settings.max_turns,
                                run_config=run_config,
                            )
                            async for event in result.stream_events():
                                if event.type == "raw_response_event" and isinstance(
                                    event.data, ResponseTextDeltaEvent
                                ):
                                    await on_progress(
                                        {
                                            "type": "reply_delta",
                                            "text": event.data.delta,
                                        }
                                    )
                    reply = str(result.final_output)
                    if not reply.strip():
                        raise ValueError("Model returned no learner-facing response")
                    items = result.to_input_list()[len(history) :]
                    self.store.save_turn(ctx, reply, items)
                    if selected_exercise_id:
                        for assessment in ctx.assessments:
                            weak = [
                                item["skill_id"]
                                for item in assessment["observations"]
                                if item["outcome"] != "success"
                            ]
                            recorded_skills = {
                                row[0]
                                for row in self.store.db.execute(
                                    "SELECT x.skill_id FROM assistance a "
                                    "JOIN assistance_skills x ON x.assistance_id=a.id "
                                    "WHERE a.exercise_id=? AND a.turn_id=?",
                                    (selected_exercise_id, ctx.turn_id),
                                )
                            }
                            if remaining := [
                                skill for skill in weak if skill not in recorded_skills
                            ]:
                                self.store.record_assistance(
                                    ctx,
                                    selected_exercise_id,
                                    remaining,
                                    "explanation",
                                    reply,
                                )
                    activities = [
                        self.store.exercise(scope, exercise_id)
                        for exercise_id in ctx.exercise_ids
                    ]
                span.set_attribute("milai.committed_event_ids", ctx.event_ids)
                span.set_attribute("milai.tool_calls", ctx.calls)
                span.set_attribute("milai.turn_id", ctx.turn_id)
                if self.telemetry.content:
                    span.set_attribute("output.value", reply)
                return TutorReply(
                    text=reply,
                    activities=activities,
                    assessments=ctx.assessments,
                    turn_id=ctx.turn_id,
                )

    async def close(self):
        client = getattr(self.model, "_client", None)
        if client is not None:
            await client.close()
        self.telemetry.flush()
