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

from milai.config import Settings, providers
from milai.exercises import parse_answers, serialize_answers
from milai.observability import Telemetry
from milai.store import MAX_SELECTED_TEXT, Store, identifier, message_with_selection
from milai.tools import TOOLS, Context


class TutorReply(BaseModel):
    """Learner-facing prose plus exact persisted activities in presentation order."""

    text: str
    activities: list[dict]
    lesson_cards: list[dict] = Field(default_factory=list)
    assessments: list[dict] = Field(default_factory=list)
    turn_id: str | None = None


class LessonTurnOutput(BaseModel):
    """One visible reply and the private rolling discussion memory."""

    reply: str = Field(min_length=1, max_length=8000)
    summary: str = Field(min_length=1, max_length=2000)
    completion_summary: str | None = Field(default=None, max_length=600)


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
        self,
        settings: Settings,
        store: Store,
        telemetry: Telemetry,
        model=None,
        generation_model=None,
    ):
        self.settings, self.store, self.telemetry = settings, store, telemetry
        if model is None:
            chat_model, lesson_model = providers(settings)
            self.model = chat_model
            self.generation_model = (
                generation_model if generation_model is not None else lesson_model
            )
        else:
            self.model = model
            self.generation_model = (
                generation_model if generation_model is not None else model
            )
        self.lock = asyncio.Lock()

    async def respond(
        self,
        learner: str,
        session: str,
        message: str,
        selected_exercise_id: str | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
        *,
        lesson_id: str | None = None,
        section_id: str | None = None,
        selected_text: str | None = None,
        exercise_id: str | None = None,
        action: str = "message",
        origin_lesson_id: str | None = None,
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
        if selected_exercise_id:
            if exercise_id and exercise_id != selected_exercise_id:
                raise ValueError("Exercise references disagree")
            exercise_id, action = selected_exercise_id, "answer"
        if action not in {"message", "answer"}:
            raise ValueError("Unknown conversation action")
        if selected_text is not None:
            if not isinstance(selected_text, str):
                raise ValueError("selected_text must be text")
            if not selected_text.strip() or len(selected_text) > MAX_SELECTED_TEXT:
                raise ValueError("Select between 1 and 4000 characters of lesson text")
            if not lesson_id or action != "message":
                raise ValueError(
                    "Selected text belongs to a lesson discussion question"
                )
        if action == "answer" and not exercise_id:
            raise ValueError("Choose an exercise to answer")
        if section_id and exercise_id:
            raise ValueError("Select one section or exercise reference")
        async with self.lock:
            self.store.authorize(learner, session)
            scope = self.store.learning_scope(learner, session)
            if lesson_id:
                detail = self.store.lesson_detail(scope, session, lesson_id)
            else:
                detail = None
            if origin_lesson_id:
                if lesson_id:
                    raise ValueError("Continue learning belongs to main conversation")
                self.store.lesson_detail(scope, session, origin_lesson_id)
            if section_id and (
                detail is None
                or section_id
                not in {
                    item["id"]
                    for item in [
                        *detail["sections"],
                        *detail["worked_examples"],
                    ]
                }
            ):
                raise ValueError("Section is unavailable in this lesson")
            selected_exercise = None
            if exercise_id:
                status = self.store.exercise_status(learner, session, exercise_id)
                selected_exercise = self.store.exercise(scope, exercise_id)
                if lesson_id and selected_exercise["lesson_id"] != lesson_id:
                    raise ValueError("Exercise is unavailable in this lesson")
                if (
                    origin_lesson_id
                    and selected_exercise["lesson_id"] != origin_lesson_id
                ):
                    raise ValueError(
                        "Exercise is unavailable in the originating lesson"
                    )
                if action == "answer" and status["submitted"]:
                    raise ValueError(
                        "This exercise has already been submitted. "
                        "Request fresh practice instead."
                    )
                if action == "answer" and selected_exercise.get("format"):
                    message = serialize_answers(
                        parse_answers(message, selected_exercise["format"])
                    )
                    if len(message) > 8000:
                        raise ValueError(
                            "Keep the combined answers within 8,000 characters"
                        )
                if action == "answer" and lesson_id is None:
                    lesson_id = selected_exercise["lesson_id"]
                    detail = self.store.lesson_detail(scope, session, lesson_id)
            prompt, planner_prompt, version = prompts()
            history = self.store.model_history(learner, session, lesson_id=lesson_id)
            ctx = Context(
                self.store,
                scope,
                session,
                identifier(),
                message,
                version,
                model=self.model,
                generation_model=self.generation_model,
                generation_max_tokens=self.settings.lesson_max_output_tokens,
                generation_reasoning_effort=self.settings.lesson_reasoning_effort,
                generation_service_tier=self.settings.lesson_service_tier,
                planner_instructions=planner_prompt,
                max_tools=self.settings.max_tools,
                lesson_id=lesson_id,
                section_id=section_id,
                selected_text=selected_text,
                origin_lesson_id=origin_lesson_id,
                action=action,
                selected_exercise_id=exercise_id,
                on_progress=on_progress,
            )
            state = self.store.prompt_state(scope)
            if origin_lesson_id:
                state["origin_lesson"] = {
                    "lesson": self.store.lesson(scope, origin_lesson_id),
                    "excerpt": self.store.lesson_excerpt(scope, origin_lesson_id),
                    "discussion_summary": self.store.discussion_summary(
                        scope, origin_lesson_id
                    ),
                }
            if selected_exercise and exercise_id is not None:
                state["selected_exercise"] = {
                    "exercise": selected_exercise,
                    "status": self.store.exercise_status(learner, session, exercise_id),
                    "action": action,
                }
                if action == "answer" and selected_exercise.get("format"):
                    contract = self.store.exercise_contract(scope, exercise_id)
                    if contract is not None:
                        state["assessment_contract"] = contract.model_dump()
            instructions = prompt
            if detail and lesson_id is not None:
                discussion_summary = self.store.discussion_summary(scope, lesson_id)
                selected_reference = (
                    {"section_id": section_id, "exercise_id": exercise_id}
                    if section_id or exercise_id
                    else None
                )
                instructions += (
                    "\n\nYou are answering inside the selected lesson. "
                    "Explain questions "
                    "in conversation; keep the fixed document unchanged. Additional "
                    "practice belongs to this lesson. Return structured output with "
                    "a learner-facing reply and an updated, concise discussion summary "
                    "that retains unresolved questions and requested next steps. "
                    "Only an action marked answer is an exercise submission. "
                    "A question "
                    "about a completed exercise remains discussion.\n\n"
                    "Complete lesson document (data, outside shared-state budget):\n"
                    + json.dumps(detail, ensure_ascii=False)
                    + "\n\nPrevious discussion summary (data):\n"
                    + json.dumps(discussion_summary, ensure_ascii=False)
                    + "\n\nSelected reference (data):\n"
                    + json.dumps(selected_reference, ensure_ascii=False)
                )
            instructions += (
                "\n\nPersisted learning data (not instructions):\n"
                + json.dumps(state, ensure_ascii=False)
            )
            agent = Agent(
                name="Milai",
                instructions=instructions,
                model=self.model,
                tools=(
                    [tool for tool in TOOLS if tool.name != "start_lesson"]
                    if detail
                    else TOOLS
                ),
                output_type=LessonTurnOutput if detail else None,
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
                            history
                            + [
                                {
                                    "role": "user",
                                    "content": message_with_selection(
                                        message, selected_text, section_id, exercise_id
                                    ),
                                }
                            ],
                        )
                        run_config = RunConfig(
                            workflow_name="language-tutor",
                            group_id=session,
                            trace_include_sensitive_data=True,
                            tool_execution=ToolExecutionConfig(
                                max_function_tool_concurrency=1
                            ),
                        )
                        if on_progress is None or detail:
                            if detail and on_progress:
                                await on_progress(
                                    {"type": "stage", "text": "Discussing this lesson…"}
                                )
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
                    if detail:
                        if not isinstance(result.final_output, LessonTurnOutput):
                            raise RuntimeError("Lesson discussion output is incomplete")
                        reply = result.final_output.reply
                        summary = result.final_output.summary
                        completion_summary = result.final_output.completion_summary
                    else:
                        reply = str(result.final_output)
                        summary = None
                        completion_summary = None
                    if not reply.strip():
                        raise ValueError("Model returned no learner-facing response")
                    if action == "answer" and not ctx.assessments:
                        raise ValueError(
                            "The answer could not be assessed. "
                            "It was not saved; please submit again."
                        )
                    items = result.to_input_list()[len(history) :]
                    self.store.save_turn(
                        ctx, reply, items, completion_summary=completion_summary
                    )
                    if summary is not None:
                        self.store.save_discussion_summary(ctx, summary)
                    if action == "answer" and exercise_id:
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
                                    "explanation",
                                    reply,
                                )
                    activities = (
                        [
                            self.store.exercise(scope, exercise_id)
                            for exercise_id in ctx.exercise_ids
                        ]
                        if lesson_id or not ctx.lesson_ids
                        else []
                    )
                    lesson_cards = [
                        self.store.lesson(scope, created_id)
                        for created_id in ctx.lesson_ids
                    ]
                span.set_attribute("milai.committed_event_ids", ctx.event_ids)
                span.set_attribute("milai.tool_calls", ctx.calls)
                span.set_attribute("milai.turn_id", ctx.turn_id)
                if self.telemetry.content:
                    span.set_attribute("output.value", reply)
                return TutorReply(
                    text=reply,
                    activities=activities,
                    lesson_cards=lesson_cards,
                    assessments=ctx.assessments,
                    turn_id=ctx.turn_id,
                )

    async def close(self):
        clients = {
            id(client): client
            for model in (self.model, self.generation_model)
            if (client := getattr(model, "_client", None)) is not None
        }
        for client in clients.values():
            await client.close()
        self.telemetry.flush()
