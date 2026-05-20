"""Lesson practice state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.llm.errors import LLMError
from milai.llm.lesson_service import LessonLLM
from milai.models.curriculum import Exercise, ExerciseEvaluation, Lesson
from milai.models.user_state import UserState
from milai.state.handlers.lesson import (
    _active_module_lesson,
    _apply_feedback,
    _lesson_context,
)
from milai.state.variants import (
    AppState,
    LessonCompleteState,
    LessonPracticeState,
    LessonState,
)


class LessonPracticeHandler:
    def __init__(self, mediator: IOMediator, llm: LessonLLM) -> None:
        self._mediator = mediator
        self._llm = llm

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[LessonPracticeState | LessonCompleteState, UserState] | None:
        if not isinstance(app, LessonPracticeState):
            raise TypeError(f"LessonPracticeHandler cannot handle {app.type!r}")
        if user.curriculum is None:
            await self._mediator.show_error("No confirmed curriculum is available.")
            return None

        updated = user.model_copy(deep=True)
        module, lesson = _active_module_lesson(updated)
        if not lesson.exercises:
            generated = await self._generate_exercises(updated)
            lesson.exercises = generated
            lesson.current_exercise_idx = 0

        if lesson.current_exercise_idx >= len(lesson.exercises):
            return LessonCompleteState(), updated

        exercise = lesson.exercises[lesson.current_exercise_idx]
        await self._show_practice(lesson, exercise)
        answer = await self._mediator.prompt("Your answer")
        feedback = await self._feedback(
            exercise,
            updated,
            answer=answer,
            lesson_context=_lesson_context(module, lesson),
        )
        _apply_feedback(updated, exercise, answer=answer, feedback=feedback)
        lesson.current_exercise_idx += 1
        await self._mediator.show(RichContent(feedback.feedback))

        if lesson.current_exercise_idx >= len(lesson.exercises):
            return LessonCompleteState(), updated
        return LessonPracticeState(), updated

    async def _show_practice(self, lesson: Lesson, exercise: Exercise) -> None:
        await self._mediator.clear()
        total = len(lesson.exercises)
        current = min(lesson.current_exercise_idx + 1, total)
        await self._mediator.show(
            RichContent(
                "Practice", kind=ContentKind.PROGRESS, current=current, total=total
            )
        )
        lines = [exercise.instruction]
        if exercise.options:
            lines.extend(f"- {option}" for option in exercise.options)
        await self._mediator.show(RichContent("\n".join(lines)))

    async def _generate_exercises(self, user: UserState) -> list[Exercise]:
        while True:
            try:
                return await self._llm.generate_exercises(LessonState(), user)
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _feedback(
        self,
        exercise: Exercise,
        user: UserState,
        *,
        answer: str,
        lesson_context: str,
    ) -> ExerciseEvaluation:
        while True:
            try:
                return await self._llm.evaluate_answer(
                    exercise,
                    user,
                    answer=answer,
                    lesson_context=lesson_context,
                )
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")
