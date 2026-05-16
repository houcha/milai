import asyncio

from milai.state.handlers.onboarding import OnboardingHandler
from milai.state.variants import AssessmentState, OnboardingState


def test_onboarding_collects_required_and_optional_preferences() -> None:
    from milai.models.user_state import UserState
    from tests.fakes.mediator import ScriptedMediator

    mediator = ScriptedMediator(
        [
            "Spanish",
            "English",
            "travel",
            "25",
            "formality=casual, avoid=grammar jargon",
        ]
    )
    handler = OnboardingHandler(mediator)

    app, user = asyncio.run(handler.step(OnboardingState(), UserState()))

    assert isinstance(app, AssessmentState)
    assert user.profile.target_language == "Spanish"
    assert user.profile.native_language == "English"
    assert user.profile.learning_goal == "travel"
    assert user.profile.minutes_per_day == 25
    assert user.profile.preferences == {
        "formality": "casual",
        "avoid": "grammar jargon",
    }


def test_onboarding_requires_target_language_and_keeps_optional_defaults() -> None:
    from milai.models.user_state import UserState
    from tests.fakes.mediator import ScriptedMediator

    mediator = ScriptedMediator(["", "German", "", "", "", ""])
    handler = OnboardingHandler(mediator)

    app, user = asyncio.run(handler.step(OnboardingState(), UserState()))

    assert isinstance(app, AssessmentState)
    assert user.profile.target_language == "German"
    assert user.profile.native_language is None
    assert user.profile.learning_goal is None
    assert user.profile.minutes_per_day is None
    assert user.profile.preferences == {}
    assert mediator.errors == ["Target language is required."]
