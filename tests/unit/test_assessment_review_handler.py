import asyncio

from milai.models.assessment import AssessmentQuestion
from milai.models.user_state import UserProfile, UserState
from milai.state.handlers.assessment_review import AssessmentReviewHandler
from milai.state.variants import AssessmentReviewState, CurriculumGenerationState


def test_assessment_review_confirms_fluency() -> None:
    from tests.fakes.mediator import ScriptedMediator

    mediator = ScriptedMediator([True])
    handler = AssessmentReviewHandler(mediator)

    app, user = asyncio.run(
        handler.step(
            AssessmentReviewState(
                fluency_level="A2",
                fluency_rationale="Good basics.",
                assessment_questions=[
                    AssessmentQuestion(
                        text="Translate: good morning",
                        user_answer="morning answer",
                    )
                ],
            ),
            UserState(profile=UserProfile(target_language="Spanish")),
        )
    )

    assert isinstance(app, CurriculumGenerationState)
    assert app.assessment_questions[0].user_answer == "morning answer"
    assert user.profile.fluency_level == "A2"


def test_assessment_review_allows_override() -> None:
    from tests.fakes.mediator import ScriptedMediator

    mediator = ScriptedMediator([False, "B1"])
    handler = AssessmentReviewHandler(mediator)

    app, user = asyncio.run(
        handler.step(
            AssessmentReviewState(fluency_level="A2", fluency_rationale="Good basics."),
            UserState(profile=UserProfile(target_language="Spanish")),
        )
    )

    assert isinstance(app, CurriculumGenerationState)
    assert user.profile.fluency_level == "B1"
