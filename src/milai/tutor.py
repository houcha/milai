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
    planner = root.joinpath("topic_planner.md").read_text()
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
        exercise_interaction: tuple[str, str] | None = None,
    ) -> TutorReply:
        if not message.strip() or len(message) > 8000:
            raise ValueError("Send a message between 1 and 8000 characters")
        async with self.lock:
            self.store.authorize(learner, session)
            scope = self.store.learning_scope(learner, session)
            if exercise_interaction:
                exercise_id, action = exercise_interaction
                status = self.store.exercise_status(learner, session, exercise_id)
                if action not in {"answer", "hint"} or status["completed"]:
                    raise ValueError("This exercise cannot accept that action")
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
                trace_content=self.telemetry.content,
                max_tools=self.settings.max_tools,
                exercise_interaction=exercise_interaction,
            )
            state = json.dumps(self.store.prompt_state(scope), ensure_ascii=False)
            if exercise_interaction:
                exercise_id, action = exercise_interaction
                exercise = self.store.exercise(scope, exercise_id)
                state += (
                    "\nSelected exercise interaction (authoritative): "
                    + json.dumps(
                        {
                            "action": action,
                            "exercise": exercise,
                            "status": self.store.exercise_status(
                                learner, session, exercise_id
                            ),
                        },
                        ensure_ascii=False,
                    )
                )
                state += (
                    "\nFor a hint, give a useful hint and do not assess an attempt. "
                    "For an answer, assess only the selected exercise if there is "
                    "enough evidence. Clarification is allowed. "
                    "The action is not learner prose."
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
                    if exercise_interaction:
                        exercise_id, action = exercise_interaction
                        skill_ids = [
                            skill["id"]
                            for skill in self.store.exercise(scope, exercise_id)[
                                "skills"
                            ]
                        ]
                        if action == "hint":
                            recorded_skills = {
                                row[0]
                                for row in self.store.db.execute(
                                    "SELECT x.skill_id FROM assistance a "
                                    "JOIN assistance_skills x ON x.assistance_id=a.id "
                                    "WHERE a.exercise_id=? AND a.turn_id=?",
                                    (exercise_id, ctx.turn_id),
                                )
                            }
                            missing = [
                                skill
                                for skill in skill_ids
                                if skill not in recorded_skills
                            ]
                            if missing:
                                self.store.record_assistance(
                                    ctx, exercise_id, missing, "hint", reply
                                )
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
                                    (exercise_id, ctx.turn_id),
                                )
                            }
                            if remaining := [
                                skill for skill in weak if skill not in recorded_skills
                            ]:
                                self.store.record_assistance(
                                    ctx,
                                    exercise_id,
                                    remaining,
                                    "hint",
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
