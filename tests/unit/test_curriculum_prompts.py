import pytest
from pydantic import ValidationError

from milai.llm.prompts.curriculum import (
    CurriculumDraft,
    build_adjustment_prompt,
    build_generation_prompt,
)
from milai.models.assessment import AssessmentQuestion
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.user_state import UserProfile, UserState
from milai.state.variants import CurriculumGenerationState, CurriculumReviewState


def test_generation_prompt_includes_assessment_answers_for_skill_inference() -> None:
    user = UserState(
        profile=UserProfile(
            target_language="Spanish",
            native_language="English",
            learning_goal="travel",
            fluency_level="A1",
        )
    )
    state = CurriculumGenerationState(
        assessment_questions=[
            AssessmentQuestion(
                text="Translate: good morning",
                user_answer="morning answer",
                difficulty="beginner",
            )
        ]
    )

    rendered = "\n".join(
        message.content for message in build_generation_prompt(state, user)
    )

    assert "Spanish" in rendered
    assert "morning answer" in rendered
    assert "initial skill" in rendered.lower()
    assert "Existing skills" not in rendered
    draft = CurriculumDraft.model_validate(
        {
            "curriculum": Curriculum(
                modules=[Module(title="Basics", lessons=[Lesson(title="Hello")])]
            ).model_dump(),
            "initial_skills": [{"topic": "greetings"}],
        }
    )
    assert draft.initial_skills[0].topic == "greetings"


def test_adjustment_prompt_includes_current_curriculum_and_feedback() -> None:
    user = UserState(
        profile=UserProfile(target_language="Spanish", fluency_level="A1"),
        curriculum=Curriculum(
            modules=[
                Module(title="Travel Basics", lessons=[Lesson(title="Greetings")]),
                Module(title="Food", lessons=[Lesson(title="Ordering")]),
            ]
        ),
    )

    rendered = "\n".join(
        message.content
        for message in build_adjustment_prompt(
            CurriculumReviewState(),
            user,
            feedback="Move food earlier and remove hotel vocabulary.",
        )
    )

    assert "Travel Basics" in rendered
    assert "Food" in rendered
    assert "Move food earlier" in rendered
    assert "remove hotel vocabulary" in rendered
    assert "Spanish" in rendered
    assert "Existing skills" not in rendered


def test_curriculum_draft_rejects_malformed_llm_response() -> None:
    with pytest.raises(ValidationError):
        CurriculumDraft.model_validate(
            {
                "curriculum": {"modules": [{"description": "Missing title"}]},
                "initial_skills": [{"topic": ""}],
            }
        )


def test_curriculum_draft_requires_usable_module_and_lesson_structure() -> None:
    with pytest.raises(ValidationError):
        CurriculumDraft.model_validate({"curriculum": {"modules": []}})

    with pytest.raises(ValidationError):
        CurriculumDraft.model_validate(
            {"curriculum": {"modules": [{"title": "Travel", "lessons": []}]}}
        )
