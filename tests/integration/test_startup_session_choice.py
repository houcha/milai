import asyncio

import milai.main as main_module
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.state import PersistedState
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.variants import AssessmentState, OnboardingState
from tests.fakes.mediator import ScriptedMediator
from tests.fakes.storage_client import InMemoryStorage


def test_launch_choice_can_continue_saved_session() -> None:
    saved = PersistedState(
        user=UserState(profile=UserProfile(target_language="Spanish")),
        app=AssessmentState(current_idx=1),
    )
    storage = InMemoryStorage(saved)
    mediator = ScriptedMediator(["continue"])

    selected = asyncio.run(main_module.prepare_launch_snapshot(storage, mediator))

    assert selected == saved


def test_launch_choice_can_start_new_session() -> None:
    saved = PersistedState(
        user=UserState(profile=UserProfile(target_language="Spanish")),
        app=AssessmentState(current_idx=1),
    )
    storage = InMemoryStorage(saved)
    mediator = ScriptedMediator(["start_new"])

    selected = asyncio.run(main_module.prepare_launch_snapshot(storage, mediator))

    assert isinstance(selected.app, OnboardingState)
    assert selected.user == UserState()


def test_confirmed_replacement_clears_profile_curriculum_and_progress() -> None:
    saved = PersistedState(
        user=UserState(
            profile=UserProfile(target_language="Spanish", fluency_level="B1"),
            skills=[Skill(topic="greetings")],
            curriculum=Curriculum(
                modules=[
                    Module(
                        title="Basics",
                        lessons=[Lesson(title="Hello", current_exercise_idx=1)],
                    )
                ]
            ),
        ),
        app=AssessmentState(current_idx=1),
    )
    storage = InMemoryStorage(saved)
    mediator = ScriptedMediator(["start_new"])

    selected = asyncio.run(main_module.prepare_launch_snapshot(storage, mediator))

    assert selected.user.profile == UserProfile()
    assert selected.user.skills == []
    assert selected.user.curriculum is None
    assert isinstance(selected.app, OnboardingState)
