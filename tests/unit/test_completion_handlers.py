import asyncio

import pytest

from milai.llm.errors import LLMError
from milai.llm.prompts.curriculum import CurriculumDraft
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.handlers.curriculum_complete import CurriculumCompleteHandler
from milai.state.handlers.lesson_complete import LessonCompleteHandler
from milai.state.variants import (
    CurriculumCompleteState,
    LessonCompleteState,
    LessonState,
    OnboardingState,
)


def _user() -> UserState:
    return UserState(
        profile=UserProfile(target_language="Spanish"),
        skills=[Skill(topic="greetings")],
        curriculum=Curriculum(
            modules=[
                Module(
                    title="Basics",
                    lessons=[
                        Lesson(title="Greetings"),
                        Lesson(title="Tickets"),
                    ],
                ),
                Module(
                    title="Food",
                    lessons=[Lesson(title="Ordering")],
                ),
            ]
        ),
    )


def test_lesson_complete_advances_lesson_and_module_cursors() -> None:
    from tests.fakes.mediator import ScriptedMediator

    user = _user()
    handler = LessonCompleteHandler(ScriptedMediator([]))

    result = asyncio.run(handler.step(LessonCompleteState(), user))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonState)
    assert updated.curriculum is not None
    assert updated.curriculum.modules[0].current_lesson_idx == 1
    assert updated.curriculum.current_module_idx == 0

    updated.curriculum.modules[0].current_lesson_idx = 1
    result = asyncio.run(handler.step(LessonCompleteState(), updated))
    assert result is not None
    app, updated = result
    assert isinstance(app, LessonState)
    assert updated.curriculum is not None
    assert updated.curriculum.current_module_idx == 1
    assert updated.curriculum.modules[1].current_lesson_idx == 0


def test_lesson_complete_moves_to_curriculum_complete_at_end() -> None:
    from tests.fakes.mediator import ScriptedMediator

    user = _user()
    assert user.curriculum is not None
    user.curriculum.current_module_idx = 1
    user.curriculum.modules[1].current_lesson_idx = 0

    result = asyncio.run(
        LessonCompleteHandler(ScriptedMediator([])).step(LessonCompleteState(), user)
    )
    assert result is not None
    app, _ = result

    assert isinstance(app, CurriculumCompleteState)


def test_curriculum_complete_can_extend_curriculum() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    extension = CurriculumDraft(
        curriculum=Curriculum(
            modules=[
                Module(
                    title="Next Steps",
                    lessons=[Lesson(title="Past Tense")],
                )
            ]
        ),
        initial_skills=[Skill(topic="past tense")],
    )
    handler = CurriculumCompleteHandler(
        ScriptedMediator(["extend"]),
        ScriptedLLMClient([extension]),
    )

    result = asyncio.run(handler.step(CurriculumCompleteState(), _user()))
    assert result is not None
    app, updated = result

    assert isinstance(app, LessonState)
    assert updated.curriculum is not None
    assert [module.title for module in updated.curriculum.modules][-1] == "Next Steps"
    assert updated.curriculum.current_module_idx == 2
    assert [skill.topic for skill in updated.skills] == ["greetings", "past tense"]


def test_curriculum_complete_extension_retry_and_no_data_loss() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    user = _user()
    handler = CurriculumCompleteHandler(
        ScriptedMediator(["extend", False]),
        ScriptedLLMClient([LLMError("timeout")]),
    )

    with pytest.raises(LLMError, match="timeout"):
        asyncio.run(handler.step(CurriculumCompleteState(), user))

    assert user.curriculum is not None
    assert [module.title for module in user.curriculum.modules] == ["Basics", "Food"]


def test_curriculum_complete_start_new_replaces_user_state() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    result = asyncio.run(
        CurriculumCompleteHandler(
            ScriptedMediator(["start_new"]),
            ScriptedLLMClient([]),
        ).step(CurriculumCompleteState(), _user())
    )
    assert result is not None
    app, updated = result

    assert isinstance(app, OnboardingState)
    assert updated == UserState()
