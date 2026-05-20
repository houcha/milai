import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from milai.llm.errors import LLMError
from milai.llm.lesson_service import LessonLLM
from milai.llm.types import Role
from milai.models.curriculum import (
    Curriculum,
    Exercise,
    ExerciseEvaluation,
    Lesson,
    Module,
)
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.variants import LessonState


def _user() -> UserState:
    return UserState(
        profile=UserProfile(target_language="Spanish", fluency_level="A1"),
        skills=[
            Skill(
                topic="greetings",
                strength=0.1,
                last_seen=datetime.now(UTC) - timedelta(days=2),
            )
        ],
        curriculum=Curriculum(
            modules=[
                Module(
                    title="Basics",
                    lessons=[
                        Lesson(
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
                    ],
                )
            ]
        ),
    )


def _exercise_batch(instruction: str = "Translate hello") -> dict[str, object]:
    return {
        "exercises": [
            {
                "instruction": instruction,
                "exercise_type": "translation",
                "skill_topics": ["greetings"],
            }
        ]
    }


def test_lesson_llm_generates_theory_without_changing_curriculum_title() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient

    llm = ScriptedLLMClient(["Use hola."])
    service = LessonLLM(llm)

    lesson = asyncio.run(service.generate_lesson_content(LessonState(), _user()))

    assert lesson.title == "Greetings"
    assert lesson.theory == "Use hola."
    assert lesson.exercises[0].instruction == "Translate hello"
    assert llm.response_models == [None]
    assert llm.call_kwargs == [{"timeout": 60}]
    assert [message.role for message in llm.calls[0]] == [Role.USER]
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "Write the theory for lesson Greetings in module Basics" in rendered
    assert "choose the level, language, examples, and teaching style" in rendered
    assert "Keep the output scoped to theory only" in rendered
    assert "Active curriculum position" not in rendered
    assert "Module:" not in rendered
    assert "Profile:" not in rendered
    assert "suitable for the learner" not in rendered
    assert "Reinforce these review topics" not in rendered
    assert "Current lesson placeholder/content" not in rendered
    assert "last_seen" not in rendered


def test_lesson_llm_generates_exercises_with_exercise_batch_model() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient

    llm = ScriptedLLMClient([_exercise_batch()])
    service = LessonLLM(llm)

    exercises = asyncio.run(
        service.generate_exercises(
            LessonState(),
            _user(),
            requested_change="More translation",
        )
    )

    assert exercises[0].instruction == "Translate hello"
    assert llm.response_models[0] is not None
    assert llm.response_models[0].__name__ == "_ExerciseBatch"
    assert llm.call_kwargs == [{"timeout": 60}]
    assert [message.role for message in llm.calls[0]] == [Role.USER]
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "Generate 2-5 exercises for lesson Greetings in module Basics" in rendered
    assert "Active curriculum position" not in rendered
    assert "Module:" not in rendered
    assert "Profile:" not in rendered
    assert (
        "Use the lesson theory as the source of what to practice: Hola means hello."
        in rendered
    )
    assert "Apply this requested change: More translation." in rendered
    assert "not as a replacement for the lesson focus" in rendered
    assert "Use options only for multiple_choice exercises" in rendered


def test_lesson_llm_dynamic_change_generates_changed_theory_only() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient

    llm = ScriptedLLMClient(
        [
            "Use hola.",
        ]
    )
    service = LessonLLM(llm)

    lesson = asyncio.run(
        service.change_lesson(
            LessonState(),
            _user(),
            requested_change="Make it easier",
        )
    )

    assert lesson.title == "Greetings"
    assert lesson.theory == "Use hola."
    assert lesson.current_exercise_idx == 0
    assert lesson.exercises == []
    assert llm.response_models[0] is None
    assert [message.role for message in llm.calls[0]] == [Role.USER]
    change_prompt = "\n".join(message.content for message in llm.calls[0])
    assert (
        "Revise only the theory for lesson Greetings in module Basics" in change_prompt
    )
    assert "Use the current lesson content as the baseline" in change_prompt
    assert (
        "Apply this requested change to theory content only: Make it easier."
        in change_prompt
    )
    assert "Do not change the title, exercises, or outside progress" in change_prompt
    assert "Active curriculum position" not in change_prompt
    assert "Module:" not in change_prompt
    assert "Profile:" not in change_prompt


def test_lesson_llm_evaluates_answer_with_feedback_model() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient

    user = _user()
    assert user.curriculum is not None
    exercise = user.curriculum.modules[0].lessons[0].exercises[0]
    llm = ScriptedLLMClient([{"feedback": "Correct.", "is_correct": True}])
    service = LessonLLM(llm)

    feedback = asyncio.run(
        service.evaluate_answer(
            exercise,
            user,
            answer="hola",
            lesson_context="Basics / Greetings",
        )
    )

    assert feedback.feedback == "Correct."
    assert llm.response_models == [ExerciseEvaluation]
    assert llm.call_kwargs == [{"timeout": 60}]
    assert [message.role for message in llm.calls[0]] == [Role.USER]
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "Evaluate the learner's answer for the given exercise" in rendered
    assert "lesson context: Basics / Greetings." in rendered
    assert "The learner answered: hola." in rendered
    assert "Active curriculum position" not in rendered
    assert "Profile:" not in rendered


def test_lesson_llm_propagates_llm_error_without_retrying() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient

    llm = ScriptedLLMClient([LLMError("timeout")])
    service = LessonLLM(llm)

    with pytest.raises(LLMError, match="timeout"):
        asyncio.run(service.generate_exercises(LessonState(), _user()))

    assert len(llm.calls) == 1
