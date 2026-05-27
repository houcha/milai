import asyncio
from typing import cast

from milai.agents.assessment import AssessmentInterviewer
from milai.models.assessment import Diagnosis, NextQuestion
from milai.observability import NoopObservability
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


def _interviewer(scripted: object) -> AssessmentInterviewer:
    return cast(AssessmentInterviewer, scripted)


def _next_question(text: str, *, has_latest_answer: bool = True) -> NextQuestion:
    _ = has_latest_answer
    return NextQuestion(
        action="next_question",
        text=text,
        difficulty="beginner",
        rationale="Need one focused item.",
    )


def _first_question(text: str) -> NextQuestion:
    return NextQuestion(
        action="next_question",
        text=text,
        difficulty="beginner",
        rationale="Need one focused item.",
    )


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        action="diagnosis",
        fluency_level="A1",
        rationale="Ready for basics from six confirmed answers.",
        confidence="high",
        evidence_summary="Greetings and travel requests are beginner-level.",
    )


def test_onboarding_to_assessment_asks_one_question_turns_and_persists_rationale() -> (
    None
):
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
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
    interviewer = ScriptedAssessmentInterviewer(
        [
            _first_question("Translate: good morning"),
            _next_question("Translate: good night"),
            _next_question("Say thanks"),
            _next_question("Say please"),
            _next_question("Ask for a ticket"),
            _next_question("Ask for a hotel"),
            _diagnosis(),
        ]
    )
    storage = InMemoryStorage()
    machine = StateMachine(
        storage=storage,
        handlers={
            OnboardingState: OnboardingHandler(mediator),
            AssessmentState: AssessmentHandler(mediator, _interviewer(interviewer)),
            AssessmentReviewState: AssessmentReviewHandler(mediator),
        },
        observability=NoopObservability(),
    )

    asyncio.run(machine.run(max_steps=15))

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
    assert saved.user.profile.fluency_rationale is not None
    assert "six confirmed answers" in saved.user.profile.fluency_rationale
    assert all(
        question.user_answer is not None for question in saved.app.assessment_questions
    )
