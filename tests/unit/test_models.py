from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


def test_user_state_normalizes_unique_skill_topics() -> None:
    from milai.models.user_state import Skill, UserState

    now = datetime(2026, 4, 28, tzinfo=UTC)

    user = UserState(
        skills=[
            Skill(topic="Past Tense", strength=0.4, last_seen=now),
            Skill(topic="articles", strength=0.7, last_seen=now),
        ]
    )

    assert [skill.topic for skill in user.skills] == ["past tense", "articles"]

    with pytest.raises(ValidationError, match="unique"):
        UserState(
            skills=[
                Skill(topic="Past Tense", strength=0.4, last_seen=now),
                Skill(topic="past tense", strength=0.5, last_seen=now),
            ]
        )


def test_skill_strength_and_srs_fields_are_bounded() -> None:
    from milai.models.user_state import Skill

    now = datetime(2026, 4, 28, tzinfo=UTC)

    with pytest.raises(ValidationError):
        Skill(topic="grammar", strength=1.1, last_seen=now)
    with pytest.raises(ValidationError):
        Skill(topic="grammar", strength=-0.1, last_seen=now)
    with pytest.raises(ValidationError):
        Skill(topic="grammar", strength=0.5, streak=-1, last_seen=now)


def test_persisted_state_serializes_and_restores_discriminated_app_state() -> None:
    from milai.models.state import PersistedState
    from milai.models.user_state import UserState
    from milai.state.variants import (
        AssessmentState,
        LessonPracticeState,
        OnboardingState,
    )

    onboarding = PersistedState(user=UserState(), app=OnboardingState())
    restored = PersistedState.model_validate_json(onboarding.model_dump_json())
    assert isinstance(restored.app, OnboardingState)

    assessment = PersistedState(user=UserState(), app=AssessmentState(current_idx=2))
    restored = PersistedState.model_validate_json(assessment.model_dump_json())
    assert isinstance(restored.app, AssessmentState)
    assert restored.app.current_idx == 2

    practice = PersistedState(user=UserState(), app=LessonPracticeState())
    restored = PersistedState.model_validate_json(practice.model_dump_json())
    assert isinstance(restored.app, LessonPracticeState)


def test_persisted_state_round_trips_section_message_histories() -> None:
    from milai.llm.types import Message, Role
    from milai.models.state import PersistedState
    from milai.models.user_state import UserState
    from milai.state.variants import (
        AssessmentReviewState,
        AssessmentState,
        CurriculumGenerationState,
        CurriculumReviewState,
        LessonPracticeState,
        LessonState,
    )

    assessment_user = Message(
        role=Role.USER,
        content="I think it is hola.",
    )
    assessment_assistant = Message(
        role=Role.ASSISTANT,
        content="Translate good morning.",
    )
    curriculum_user = Message(
        role=Role.USER,
        content="Make the travel module shorter.",
    )
    curriculum_assistant = Message(
        role=Role.ASSISTANT,
        content='{"modules": ["Travel Spanish"]}',
    )
    lesson_user = Message(
        role=Role.USER,
        content="Can you give another example?",
    )
    lesson_assistant = Message(
        role=Role.ASSISTANT,
        content="Sure, here is another travel example.",
    )

    assessment = PersistedState(
        user=UserState(),
        app=AssessmentState(
            assessment_messages=[assessment_assistant, assessment_user]
        ),
    )
    restored = PersistedState.model_validate_json(assessment.model_dump_json())
    assert isinstance(restored.app, AssessmentState)
    assert restored.app.assessment_messages[0].role == Role.ASSISTANT
    assert restored.app.assessment_messages[1].content == "I think it is hola."

    assessment_review = PersistedState(
        user=UserState(),
        app=AssessmentReviewState(
            fluency_level="A1",
            assessment_messages=[assessment_assistant, assessment_user],
        ),
    )
    restored = PersistedState.model_validate_json(assessment_review.model_dump_json())
    assert isinstance(restored.app, AssessmentReviewState)
    assert restored.app.assessment_messages[0].content == "Translate good morning."

    curriculum = PersistedState(
        user=UserState(),
        app=CurriculumGenerationState(
            assessment_messages=[assessment_assistant, assessment_user],
            curriculum_messages=[curriculum_user, curriculum_assistant],
        ),
    )
    restored = PersistedState.model_validate_json(curriculum.model_dump_json())
    assert isinstance(restored.app, CurriculumGenerationState)
    assert restored.app.assessment_messages[1].role == Role.USER
    assert restored.app.curriculum_messages[0].content == (
        "Make the travel module shorter."
    )

    curriculum_review = PersistedState(
        user=UserState(),
        app=CurriculumReviewState(
            curriculum_messages=[curriculum_user, curriculum_assistant],
        ),
    )
    restored = PersistedState.model_validate_json(curriculum_review.model_dump_json())
    assert isinstance(restored.app, CurriculumReviewState)
    assert restored.app.curriculum_messages[1].role == Role.ASSISTANT

    lesson_state = PersistedState(
        user=UserState(),
        app=LessonState(lesson_messages=[lesson_user, lesson_assistant]),
    )
    restored = PersistedState.model_validate_json(lesson_state.model_dump_json())
    assert isinstance(restored.app, LessonState)
    assert restored.app.lesson_messages[0].role == Role.USER

    lesson = PersistedState(
        user=UserState(), app=LessonPracticeState(lesson_messages=[lesson_user])
    )
    restored = PersistedState.model_validate_json(lesson.model_dump_json())
    assert isinstance(restored.app, LessonPracticeState)
    assert restored.app.lesson_messages[0].content == "Can you give another example?"


def test_placeholder_lesson_is_valid_by_default() -> None:
    from milai.models.curriculum import Lesson

    lesson = Lesson(title="Greetings")

    assert lesson.title == "Greetings"
    assert lesson.theory == ""
    assert lesson.exercises == []


def test_module_requires_lessons() -> None:
    from milai.models.curriculum import Module

    with pytest.raises(ValidationError):
        Module(title="Basics", lessons=[])
