import asyncio

from milai.llm.types import Message, Role
from milai.models.assessment import AssessmentQuestion
from milai.models.session import LearningSession
from milai.models.user_state import UserProfile, UserState
from milai.state.handlers.assessment_review import AssessmentReviewHandler
from milai.state.variants import AssessmentReviewState, CurriculumGenerationState


def test_assessment_review_confirms_fluency() -> None:
    from tests.fakes.mediator import ScriptedMediator

    mediator = ScriptedMediator([True])
    handler = AssessmentReviewHandler(mediator)

    result = asyncio.run(
        handler.step(
            LearningSession(
                app=AssessmentReviewState(
                    fluency_level="A2",
                    fluency_rationale="Good basics.",
                    assessment_questions=[
                        AssessmentQuestion(
                            text="Translate: good morning",
                            user_answer="morning answer",
                        )
                    ],
                    assessment_messages=[
                        Message(role=Role.USER, content="morning answer")
                    ],
                ),
                user=UserState(profile=UserProfile(target_language="Spanish")),
            )
        )
    )
    app = result.app
    user = result.user

    assert isinstance(app, CurriculumGenerationState)
    assert app.assessment_questions[0].user_answer == "morning answer"
    assert app.assessment_messages[0].content == "morning answer"
    assert user.profile.fluency_level == "A2"
    assert user.profile.fluency_rationale == "Good basics."


def test_assessment_review_allows_override() -> None:
    from tests.fakes.mediator import ScriptedMediator

    mediator = ScriptedMediator([False, "B1"])
    handler = AssessmentReviewHandler(mediator)

    result = asyncio.run(
        handler.step(
            LearningSession(
                app=AssessmentReviewState(
                    fluency_level="A2", fluency_rationale="Good basics."
                ),
                user=UserState(profile=UserProfile(target_language="Spanish")),
            )
        )
    )
    app = result.app
    user = result.user

    assert isinstance(app, CurriculumGenerationState)
    assert user.profile.fluency_level == "B1"
    assert user.profile.fluency_rationale is None
