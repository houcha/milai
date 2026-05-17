import asyncio

import pytest

from milai.llm.errors import LLMError
from milai.llm.prompts.curriculum import CurriculumDraft
from milai.models.assessment import AssessmentQuestion
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.handlers.curriculum_gen import CurriculumGenerationHandler
from milai.state.variants import CurriculumGenerationState, CurriculumReviewState


def _draft(title: str = "Travel Basics") -> CurriculumDraft:
    return CurriculumDraft(
        curriculum=Curriculum(
            modules=[Module(title=title, lessons=[Lesson(title="Greetings")])]
        ),
        initial_skills=[
            Skill(topic="greetings", strength=0.3),
            Skill(topic="travel phrases", strength=0.2),
        ],
    )


def test_curriculum_generation_persists_draft_and_initial_skills() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLLMClient([_draft()])
    mediator = ScriptedMediator([])
    handler = CurriculumGenerationHandler(mediator, llm)
    user = UserState(
        profile=UserProfile(target_language="Spanish", fluency_level="A1"),
        skills=[Skill(topic="greetings", strength=0.8)],
    )
    state = CurriculumGenerationState(
        assessment_questions=[
            AssessmentQuestion(
                text="Translate good morning",
                user_answer="buenos dias",
            )
        ]
    )

    app, updated = asyncio.run(handler.step(state, user))

    assert isinstance(app, CurriculumReviewState)
    assert updated.curriculum is not None
    assert updated.curriculum.modules[0].title == "Travel Basics"
    assert [skill.topic for skill in updated.skills] == [
        "greetings",
        "travel phrases",
    ]
    assert updated.skills[0].strength == 0.8
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "buenos dias" in rendered
    assert "A1" in rendered


def test_curriculum_generation_retry_after_timeout_preserves_existing_user_state() -> (
    None
):
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLLMClient([LLMError("timeout"), _draft("Retry Draft")])
    mediator = ScriptedMediator([True])
    handler = CurriculumGenerationHandler(mediator, llm)
    user = UserState(
        profile=UserProfile(target_language="Spanish", fluency_level="A1"),
        skills=[Skill(topic="articles", strength=0.4)],
    )

    app, updated = asyncio.run(handler.step(CurriculumGenerationState(), user))

    assert isinstance(app, CurriculumReviewState)
    assert updated.curriculum is not None
    assert updated.curriculum.modules[0].title == "Retry Draft"
    assert [skill.topic for skill in updated.skills] == [
        "articles",
        "greetings",
        "travel phrases",
    ]
    assert mediator.errors == ["timeout"]
    assert len(llm.calls) == 2


def test_curriculum_generation_declined_retry_raises_without_mutating_user() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLLMClient([LLMError("provider unavailable")])
    mediator = ScriptedMediator([False])
    handler = CurriculumGenerationHandler(mediator, llm)
    user = UserState(
        profile=UserProfile(target_language="Spanish", fluency_level="A1"),
        skills=[Skill(topic="articles")],
    )

    with pytest.raises(LLMError, match="provider unavailable"):
        asyncio.run(handler.step(CurriculumGenerationState(), user))

    assert user.curriculum is None
    assert [skill.topic for skill in user.skills] == ["articles"]
    assert mediator.errors == ["provider unavailable"]
