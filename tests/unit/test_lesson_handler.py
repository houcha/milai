import asyncio
from typing import cast

import pytest

from milai.io.mediator import IOMediator
from milai.llm.errors import LLMError
from milai.llm.lesson_service import LessonLLM
from milai.models.curriculum import (
    Curriculum,
    Exercise,
    ExerciseEvaluation,
    Lesson,
    Module,
)
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.handlers.lesson import LessonHandler
from milai.state.variants import DeviationState, LessonPracticeState, LessonState


class ScriptedLessonLLM:
    def __init__(self, responses: list[object]) -> None:
        self._responses = iter(responses)
        self.calls: list[str] = []

    async def generate_lesson_content(
        self, state: LessonState, user: UserState
    ) -> Lesson:
        _ = state, user
        return self._next("generate_lesson_content")

    async def generate_exercises(
        self,
        state: LessonState,
        user: UserState,
        *,
        requested_change: str = "",
    ) -> list[Exercise]:
        _ = state, user, requested_change
        return self._next("generate_exercises")

    async def change_lesson(
        self,
        state: LessonState,
        user: UserState,
        *,
        requested_change: str,
    ) -> Lesson:
        _ = state, user, requested_change
        return self._next("change_lesson")

    async def evaluate_answer(
        self,
        exercise: Exercise,
        user: UserState,
        *,
        answer: str,
        lesson_context: str,
    ) -> ExerciseEvaluation:
        _ = exercise, user, answer, lesson_context
        return self._next("evaluate_answer")

    def _next(self, method: str):
        self.calls.append(method)
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return result


def _empty_lesson_user() -> UserState:
    return UserState(
        profile=UserProfile(target_language="Spanish", fluency_level="A1"),
        skills=[Skill(topic="greetings", strength=0.1)],
        curriculum=Curriculum(
            modules=[
                Module(
                    title="Basics",
                    lessons=[Lesson(title="Greetings")],
                )
            ]
        ),
    )


def _active_lesson_user() -> UserState:
    user = _empty_lesson_user()
    assert user.curriculum is not None
    user.curriculum.modules[0].lessons[0] = Lesson(
        title="Greetings",
        theory="Hola means hello.",
        exercises=[
            Exercise(
                instruction="Translate hello",
                exercise_type="translation",
                skill_topics=["greetings"],
            )
        ],
    )
    return user


def _generated_lesson(
    title: str = "Greetings", theory: str = "Hola means hello."
) -> Lesson:
    return Lesson(title=title, theory=theory)


def _generated_exercises() -> list[Exercise]:
    return [
        Exercise(
            instruction="Translate hello",
            exercise_type="translation",
            skill_topics=["greetings"],
        )
    ]


def _generated_feedback(
    feedback: str,
    *,
    is_correct: bool | None = None,
) -> ExerciseEvaluation:
    return ExerciseEvaluation(feedback=feedback, is_correct=is_correct)


def _changed_lesson() -> Lesson:
    return Lesson(
        title="Greetings",
        theory="Use hola.",
        exercises=[
            Exercise(
                instruction="Say hello",
                exercise_type="open",
                skill_topics=["greetings"],
            )
        ],
    )


def _lesson_with_theory_only() -> UserState:
    user = _empty_lesson_user()
    assert user.curriculum is not None
    user.curriculum.modules[0].lessons[0] = Lesson(
        title="Greetings",
        theory="Hola means hello.",
    )
    return user


def _handler(mediator: IOMediator, llm: ScriptedLessonLLM) -> LessonHandler:
    return LessonHandler(mediator, cast(LessonLLM, llm))


def test_lesson_handler_generates_missing_lesson_theory_with_review_skills() -> None:
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLessonLLM([_generated_lesson()])
    handler = _handler(ScriptedMediator([]), llm)

    result = asyncio.run(handler.step(LessonState(), _empty_lesson_user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonState)
    assert updated.curriculum is not None
    lesson = updated.curriculum.modules[0].lessons[0]
    assert lesson.theory == "Hola means hello."
    assert lesson.exercises == []


def test_lesson_handler_generates_missing_exercises_lazily() -> None:
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLessonLLM([])
    mediator = ScriptedMediator(["practice"])
    handler = _handler(mediator, llm)

    result = asyncio.run(handler.step(LessonState(), _lesson_with_theory_only()))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonPracticeState)
    assert updated.curriculum is not None
    lesson = updated.curriculum.modules[0].lessons[0]
    assert lesson.theory == "Hola means hello."
    assert lesson.exercises == []
    assert llm.calls == []


def test_lesson_handler_retries_generated_lesson_content_error() -> None:
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLessonLLM([LLMError("provider failed"), _generated_lesson()])
    mediator = ScriptedMediator([True])
    handler = _handler(mediator, llm)

    result = asyncio.run(handler.step(LessonState(), _empty_lesson_user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonState)
    assert llm.calls == [
        "generate_lesson_content",
        "generate_lesson_content",
    ]
    assert mediator.errors == ["provider failed"]
    assert updated.curriculum is not None
    assert updated.curriculum.modules[0].lessons[0].theory == "Hola means hello."


def test_lesson_handler_declined_generated_lesson_retry_does_not_mutate_user() -> None:
    from tests.fakes.mediator import ScriptedMediator

    user = _empty_lesson_user()
    handler = _handler(
        ScriptedMediator([False]),
        ScriptedLessonLLM([LLMError("provider failed")]),
    )

    with pytest.raises(LLMError):
        asyncio.run(handler.step(LessonState(), user))

    assert user.curriculum is not None
    assert user.curriculum.modules[0].lessons[0].theory == ""


def test_lesson_handler_applies_dynamic_change() -> None:
    from tests.fakes.mediator import ScriptedMediator

    handler = _handler(
        ScriptedMediator(["change", "Make it easier"]),
        ScriptedLessonLLM([_changed_lesson()]),
    )

    result = asyncio.run(handler.step(LessonState(), _active_lesson_user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonState)
    assert updated.curriculum is not None
    lesson = updated.curriculum.modules[0].lessons[0]
    assert lesson.title == "Greetings"
    assert lesson.theory == "Use hola."
    assert lesson.exercises == []
    assert lesson.current_exercise_idx == 0


def test_lesson_handler_starts_deviation() -> None:
    from tests.fakes.mediator import ScriptedMediator

    result = asyncio.run(
        _handler(ScriptedMediator(["deviation"]), ScriptedLessonLLM([])).step(
            LessonState(), _active_lesson_user()
        )
    )
    assert result is not None
    app, _ = result
    assert isinstance(app, DeviationState)
    assert app.lesson_context == "Basics / Greetings"


def test_lesson_handler_shows_theory_without_exercise() -> None:
    from milai.io.types import ContentKind
    from tests.fakes.mediator import ScriptedMediator

    mediator = ScriptedMediator(["practice"])
    handler = _handler(mediator, ScriptedLessonLLM([]))

    result = asyncio.run(handler.step(LessonState(), _active_lesson_user()))
    assert result is not None
    app, _ = result

    assert isinstance(app, LessonPracticeState)
    assert [content.kind for content in mediator.shown] == [
        ContentKind.HEADER,
        ContentKind.MARKDOWN,
    ]
    assert "Translate hello" not in "\n".join(
        content.text for content in mediator.shown
    )
