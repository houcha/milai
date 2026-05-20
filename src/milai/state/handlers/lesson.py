"""Lesson state handler."""

from collections.abc import Iterable

from milai.io.mediator import IOMediator
from milai.io.types import Choice, ContentKind, RichContent
from milai.llm.errors import LLMError
from milai.llm.lesson_service import LessonLLM
from milai.models.curriculum import Exercise, ExerciseEvaluation, Lesson, Module
from milai.models.user_state import Skill, UserState
from milai.srs.scheduler import update_skill
from milai.state.variants import (
    AppState,
    DeviationState,
    LessonPracticeState,
    LessonState,
)


class LessonHandler:
    def __init__(self, mediator: IOMediator, llm: LessonLLM) -> None:
        self._mediator = mediator
        self._llm = llm

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[LessonState | LessonPracticeState | DeviationState, UserState] | None:
        if not isinstance(app, LessonState):
            raise TypeError(f"LessonHandler cannot handle {app.type!r}")
        if user.curriculum is None:
            await self._mediator.show_error("No confirmed curriculum is available.")
            return None

        updated = user.model_copy(deep=True)
        module, lesson = _active_module_lesson(updated)
        if not lesson.theory.strip():
            generated = await self._generate_lesson_content(app, updated)
            _replace_active_lesson(updated, generated)
            return LessonState(), updated

        await self._show_lesson(module, lesson)
        choice = await self._mediator.choose(
            "Lesson",
            [
                Choice("Practice", "practice", "Start lesson practice"),
                Choice("Ask", "deviation", "Ask a question before continuing"),
                Choice("Change", "change", "Adjust this lesson"),
            ],
        )
        if choice.value == "deviation":
            return DeviationState(
                lesson_context=_lesson_context(module, lesson)
            ), updated
        if choice.value == "change":
            request = await self._mediator.prompt("Requested change")
            changed = await self._change_lesson(app, updated, requested_change=request)
            changed.exercises = []
            changed.current_exercise_idx = 0
            _replace_active_lesson(updated, changed)
            return LessonState(), updated

        return LessonPracticeState(), updated

    async def _show_lesson(self, module: Module, lesson: Lesson) -> None:
        await self._mediator.clear()
        await self._mediator.show(
            RichContent(_lesson_context(module, lesson), kind=ContentKind.HEADER)
        )
        await self._mediator.show(RichContent(lesson.theory, kind=ContentKind.MARKDOWN))

    async def _generate_lesson_content(
        self, state: LessonState, user: UserState
    ) -> Lesson:
        while True:
            try:
                return await self._llm.generate_lesson_content(state, user)
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _change_lesson(
        self,
        state: LessonState,
        user: UserState,
        *,
        requested_change: str,
    ) -> Lesson:
        while True:
            try:
                return await self._llm.change_lesson(
                    state,
                    user,
                    requested_change=requested_change,
                )
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")


def _active_module_lesson(user: UserState) -> tuple[Module, Lesson]:
    if user.curriculum is None:
        raise ValueError("user has no curriculum")
    module = user.curriculum.modules[user.curriculum.current_module_idx]
    lesson = module.lessons[module.current_lesson_idx]
    return module, lesson


def _replace_active_lesson(user: UserState, lesson: Lesson) -> None:
    module, _ = _active_module_lesson(user)
    module.lessons[module.current_lesson_idx] = lesson


def _lesson_context(module: Module, lesson: Lesson) -> str:
    return f"{module.title} / {lesson.title}"


def _apply_feedback(
    user: UserState,
    exercise: Exercise,
    *,
    answer: str,
    feedback: ExerciseEvaluation,
) -> None:
    exercise.user_answer = answer
    exercise.feedback = feedback.feedback
    exercise.is_correct = feedback.is_correct
    if feedback.skill_topics:
        exercise.skill_topics = feedback.skill_topics
    topics = exercise.skill_topics
    if not topics:
        return
    success = feedback.is_correct is not False
    user.skills = _update_skills(user.skills, topics, success=success)


def _update_skills(
    skills: Iterable[Skill],
    topics: Iterable[str],
    *,
    success: bool,
) -> list[Skill]:
    by_topic = {skill.topic: skill for skill in skills}
    for raw_topic in topics:
        topic = " ".join(raw_topic.strip().lower().split())
        if not topic:
            continue
        current = by_topic.get(topic, Skill(topic=topic))
        by_topic[topic] = update_skill(current, success=success)
    return list(by_topic.values())
