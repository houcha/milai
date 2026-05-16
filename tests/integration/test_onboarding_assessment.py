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
            True,
        ]
    )
    llm = ScriptedLLMClient(
        [
            AssessmentQuestionBatch(
                questions=[
                    AssessmentQuestion(
                        text="Translate: good morning",
                    )
                ]
            ),
            FluencyResult(fluency_level="A1", rationale="Ready for basics."),
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

    asyncio.run(machine.run(max_steps=5))

    saved = asyncio.run(storage.load())
    assert saved is not None
    assert saved.user.profile.target_language == "Spanish"
    assert saved.user.profile.fluency_level == "A1"
    assert saved.user.skills == []
    assert isinstance(saved.app, CurriculumGenerationState)
    assert saved.app.assessment_questions[0].user_answer == "morning answer"
