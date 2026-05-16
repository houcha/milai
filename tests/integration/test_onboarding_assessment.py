import asyncio

from milai.llm.prompts.assessment import AssessmentQuestionBatch, FluencyResult
from milai.models.assessment import AssessmentQuestion
from milai.state.handlers.assessment import AssessmentHandler
from milai.state.handlers.assessment_review import AssessmentReviewHandler
from milai.state.handlers.onboarding import OnboardingHandler
from milai.state.machine import StateMachine
from milai.state.variants import (
    AssessmentReviewState,
    AssessmentState,
    CurriculumGenerationState,
    OnboardingState,
)


def test_onboarding_to_assessment_persists_profile_answers_and_fluency() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator
    from tests.fakes.storage_client import InMemoryStorage

    mediator = ScriptedMediator(
        [
            "Spanish",
            "English",
            "travel",
            "20",
            "avoid=grammar jargon",
            "morning answer",
            "night answer",
            "thanks answer",
            "please answer",
            "ticket answer",
            "hotel answer",
            True,
        ]
    )
    llm = ScriptedLLMClient(
        [
            AssessmentQuestionBatch(
                questions=[
                    AssessmentQuestion(
                        text="Translate: good morning",
                    ),
                    AssessmentQuestion(
                        text="Translate: good night",
                    ),
                ]
            ),
            FluencyResult(
                fluency_level="A1",
                rationale="Early evidence.",
                confidence="high",
                follow_up_guidance="Probe polite phrases.",
            ),
            AssessmentQuestionBatch(
                questions=[
                    AssessmentQuestion(
                        text="Say thanks",
                    ),
                    AssessmentQuestion(
                        text="Say please",
                    ),
                ]
            ),
            FluencyResult(
                fluency_level="A1",
                rationale="More evidence.",
                confidence="high",
                follow_up_guidance="Probe travel needs.",
            ),
            AssessmentQuestionBatch(
                questions=[
                    AssessmentQuestion(
                        text="Ask for a ticket",
                    ),
                    AssessmentQuestion(
                        text="Ask for a hotel",
                    ),
                ]
            ),
            FluencyResult(
                fluency_level="A1",
                rationale="Ready for basics.",
                confidence="high",
                follow_up_guidance="No follow-up needed.",
            ),
        ]
    )
    storage = InMemoryStorage()
    machine = StateMachine(
        storage=storage,
        handlers={
            OnboardingState: OnboardingHandler(mediator),
            AssessmentState: AssessmentHandler(mediator, llm),
            AssessmentReviewState: AssessmentReviewHandler(mediator),
        },
    )

    asyncio.run(machine.run(max_steps=12))

    saved = asyncio.run(storage.load())
    assert saved is not None
    assert saved.user.profile.target_language == "Spanish"
    assert saved.user.profile.fluency_level == "A1"
    assert saved.user.skills == []
    assert isinstance(saved.app, CurriculumGenerationState)
    assert saved.app.assessment_questions[0].user_answer == "morning answer"
    assert saved.app.assessment_questions[1].user_answer == "night answer"
    assert saved.app.assessment_questions[2].user_answer == "thanks answer"
    assert saved.app.assessment_questions[3].user_answer == "please answer"
    assert saved.app.assessment_questions[4].user_answer == "ticket answer"
    assert saved.app.assessment_questions[5].user_answer == "hotel answer"
