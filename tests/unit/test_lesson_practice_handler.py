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
from milai.state.handlers.lesson_practice import LessonPracticeHandler
from milai.state.variants import LessonCompleteState, LessonPracticeState, LessonState


class ScriptedLessonLLM:
    def __init__(self, responses: list[object]) -> None:
        self._responses = iter(responses)
        self.calls: list[str] = []

    async def generate_exercises(
        self,
        state: LessonState,
        user: UserState,
        *,
        requested_change: str = "",
    ) -> list[Exercise]:
        _ = state, user, requested_change
        return self._next("generate_exercises")

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


def _lesson_with_theory_only() -> UserState:
    user = _empty_lesson_user()
    assert user.curriculum is not None
    user.curriculum.modules[0].lessons[0] = Lesson(
        title="Greetings",
        theory="Hola means hello.",
    )
    return user


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


def _handler(mediator: IOMediator, llm: ScriptedLessonLLM) -> LessonPracticeHandler:
    return LessonPracticeHandler(mediator, cast(LessonLLM, llm))


def test_practice_handler_generates_missing_exercises_and_answers_without_theory() -> (
    None
):
    from milai.io.types import ContentKind
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLessonLLM(
        [_generated_exercises(), _generated_feedback("Correct.", is_correct=True)]
    )
    mediator = ScriptedMediator(["hola"])
    handler = _handler(mediator, llm)

    result = asyncio.run(
        handler.step(LessonPracticeState(), _lesson_with_theory_only())
    )
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonCompleteState)
    assert llm.calls == ["generate_exercises", "evaluate_answer"]
    assert [content.kind for content in mediator.shown[:-1]] == [
        ContentKind.PROGRESS,
        ContentKind.TEXT,
    ]
    assert "Hola means hello." not in "\n".join(
        content.text for content in mediator.shown
    )
    assert updated.curriculum is not None
    exercise = updated.curriculum.modules[0].lessons[0].exercises[0]
    assert exercise.user_answer == "hola"
    assert exercise.feedback == "Correct."
    assert exercise.is_correct is True
    assert updated.skills[0].strength == 0.2
    assert updated.skills[0].streak == 1


def test_practice_handler_feedback_timeout_can_retry_without_data_loss() -> None:
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLessonLLM(
        [LLMError("timeout"), _generated_feedback("Try again.", is_correct=False)]
    )
    mediator = ScriptedMediator(["wrong", True])
    handler = _handler(mediator, llm)

    result = asyncio.run(handler.step(LessonPracticeState(), _active_lesson_user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonCompleteState)
    assert llm.calls == ["evaluate_answer", "evaluate_answer"]
    assert mediator.errors == ["timeout"]
    assert updated.curriculum is not None
    exercise = updated.curriculum.modules[0].lessons[0].exercises[0]
    assert exercise.user_answer == "wrong"
    assert exercise.feedback == "Try again."


def test_practice_handler_declined_feedback_retry_does_not_mutate_user() -> None:
    from tests.fakes.mediator import ScriptedMediator

    user = _active_lesson_user()
    handler = _handler(
        ScriptedMediator(["hola", False]),
        ScriptedLessonLLM([LLMError("timeout")]),
    )

    with pytest.raises(LLMError, match="timeout"):
        asyncio.run(handler.step(LessonPracticeState(), user))

    assert user.curriculum is not None
    assert user.curriculum.modules[0].lessons[0].exercises[0].user_answer is None


def test_practice_handler_retries_generated_exercises_error() -> None:
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLessonLLM(
        [
            LLMError("provider failed"),
            _generated_exercises(),
            _generated_feedback("Correct.", is_correct=True),
        ]
    )
    mediator = ScriptedMediator([True, "hola"])
    handler = _handler(mediator, llm)

    result = asyncio.run(
        handler.step(LessonPracticeState(), _lesson_with_theory_only())
    )
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonCompleteState)
    assert llm.calls == [
        "generate_exercises",
        "generate_exercises",
        "evaluate_answer",
    ]
    assert mediator.errors == ["provider failed"]
    assert updated.curriculum is not None
    assert updated.curriculum.modules[0].lessons[0].exercises[0].instruction


def test_practice_handler_continues_when_more_exercises_remain() -> None:
    from tests.fakes.mediator import ScriptedMediator

    user = _active_lesson_user()
    assert user.curriculum is not None
    user.curriculum.modules[0].lessons[0].exercises.append(
        user.curriculum.modules[0].lessons[0].exercises[0].model_copy(deep=True)
    )
    handler = _handler(
        ScriptedMediator(["hola"]),
        ScriptedLessonLLM([_generated_feedback("Correct.", is_correct=True)]),
    )

    result = asyncio.run(handler.step(LessonPracticeState(), user))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonPracticeState)
    assert updated.curriculum is not None
    assert updated.curriculum.modules[0].lessons[0].current_exercise_idx == 1


def test_practice_handler_completes_finished_lesson() -> None:
    from tests.fakes.mediator import ScriptedMediator

    user = _active_lesson_user()
    assert user.curriculum is not None
    user.curriculum.modules[0].lessons[0].current_exercise_idx = 1

    result = asyncio.run(
        _handler(ScriptedMediator([]), ScriptedLessonLLM([])).step(
            LessonPracticeState(), user
        )
    )
    assert result is not None
    app, _ = result
    assert isinstance(app, LessonCompleteState)
