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
    from milai.state.variants import AssessmentState, OnboardingState

    onboarding = PersistedState(user=UserState(), app=OnboardingState())
    restored = PersistedState.model_validate_json(onboarding.model_dump_json())
    assert isinstance(restored.app, OnboardingState)

    assessment = PersistedState(user=UserState(), app=AssessmentState(current_idx=2))
    restored = PersistedState.model_validate_json(assessment.model_dump_json())
    assert isinstance(restored.app, AssessmentState)
    assert restored.app.current_idx == 2


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
