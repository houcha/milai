import asyncio

import pytest

from milai.llm.errors import LLMError
from milai.llm.prompts.curriculum import CurriculumDraft
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.handlers.curriculum_review import CurriculumReviewHandler
from milai.state.variants import CurriculumReviewState, LessonState


def _user() -> UserState:
    return UserState(
        profile=UserProfile(target_language="Spanish", fluency_level="A1"),
        skills=[Skill(topic="greetings")],
        curriculum=Curriculum(
            modules=[
                Module(title="Basics", lessons=[Lesson(title="Greetings")]),
                Module(title="Travel", lessons=[Lesson(title="Tickets")]),
                Module(title="Food", lessons=[Lesson(title="Ordering")]),
            ]
        ),
    )


def _titles(user: UserState) -> list[str]:
    assert user.curriculum is not None
    return [module.title for module in user.curriculum.modules]


def test_curriculum_review_confirm_starts_lessons() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    handler = CurriculumReviewHandler(
        ScriptedMediator(["confirm"]), ScriptedLLMClient([])
    )

    result = asyncio.run(handler.step(CurriculumReviewState(), _user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonState)
    assert _titles(updated) == ["Basics", "Travel", "Food"]


def test_curriculum_review_feedback_adjusts_curriculum() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    adjusted = CurriculumDraft(
        curriculum=Curriculum(
            modules=[Module(title="Restaurant Spanish", lessons=[Lesson(title="Menu")])]
        ),
        initial_skills=[Skill(topic="restaurant phrases")],
    )
    llm = ScriptedLLMClient([adjusted])
    mediator = ScriptedMediator(
        ["feedback", "Move food earlier and remove the travel module."]
    )
    handler = CurriculumReviewHandler(mediator, llm)

    result = asyncio.run(handler.step(CurriculumReviewState(), _user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, CurriculumReviewState)
    assert _titles(updated) == ["Restaurant Spanish"]
    assert [skill.topic for skill in updated.skills] == [
        "greetings",
        "restaurant phrases",
    ]
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "Move food earlier" in rendered
    assert "remove the travel module" in rendered
    assert "Basics" in rendered


def test_curriculum_review_feedback_retry_preserves_current_curriculum() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    adjusted = CurriculumDraft(
        curriculum=Curriculum(
            modules=[Module(title="Retry Curriculum", lessons=[Lesson(title="Retry")])]
        )
    )
    llm = ScriptedLLMClient([LLMError("timeout"), adjusted])
    mediator = ScriptedMediator(["feedback", "Shorter modules please.", True])
    handler = CurriculumReviewHandler(mediator, llm)

    result = asyncio.run(handler.step(CurriculumReviewState(), _user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, CurriculumReviewState)
    assert _titles(updated) == ["Retry Curriculum"]
    assert mediator.errors == ["timeout"]
    assert len(llm.calls) == 2


def test_curriculum_review_declined_retry_raises_without_mutating_user() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    user = _user()
    llm = ScriptedLLMClient([LLMError("provider unavailable")])
    mediator = ScriptedMediator(["feedback", "More grammar.", False])
    handler = CurriculumReviewHandler(mediator, llm)

    with pytest.raises(LLMError, match="provider unavailable"):
        asyncio.run(handler.step(CurriculumReviewState(), user))

    assert _titles(user) == ["Basics", "Travel", "Food"]
    assert mediator.errors == ["provider unavailable"]
