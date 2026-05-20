import asyncio
from typing import Literal

import pytest

from milai.llm.errors import LLMError
from milai.llm.prompts.assessment import (
    ASSESSMENT_QUESTION_BATCH_SIZE,
    MAX_ASSESSMENT_QUESTIONS,
    MIN_ASSESSMENT_QUESTIONS,
    AssessmentQuestionBatch,
    FluencyResult,
)
from milai.models.assessment import AssessmentQuestion
from milai.models.user_state import UserProfile, UserState
from milai.state.handlers.assessment import AssessmentHandler
from milai.state.variants import AssessmentReviewState, AssessmentState


def _question(text: str) -> AssessmentQuestion:
    return AssessmentQuestion(text=text)


def _batch(prefix: str) -> AssessmentQuestionBatch:
    return AssessmentQuestionBatch(
        questions=[
            _question(f"{prefix} {idx}")
            for idx in range(1, ASSESSMENT_QUESTION_BATCH_SIZE + 1)
        ]
    )


def _fluency(
    *,
    confidence: Literal["low", "medium", "high"] = "high",
    guidance: str = "No follow-up needed.",
) -> FluencyResult:
    return FluencyResult(
        fluency_level="A1",
        rationale="Basic greetings are emerging.",
        confidence=confidence,
        follow_up_guidance=guidance,
    )


def _answered_questions(count: int) -> list[AssessmentQuestion]:
    return [
        AssessmentQuestion(
            text=f"Question {idx}",
            user_answer=f"answer {idx}",
        )
        for idx in range(1, count + 1)
    ]


def test_assessment_generates_initial_batch_and_captures_answers() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    initial_batch = _batch("Initial")
    llm = ScriptedLLMClient([initial_batch])
    mediator = ScriptedMediator(["first answer", "second answer"])
    handler = AssessmentHandler(mediator, llm)

    app, user = asyncio.run(
        handler.step(
            AssessmentState(),
            UserState(profile=UserProfile(target_language="Spanish")),
        )
    )
    assert isinstance(app, AssessmentState)
    assert app.questions == initial_batch.questions
    assert app.current_idx == 0
    assert len(llm.calls) == 1

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentState)
    assert app.questions[0].user_answer == "first answer"
    assert app.current_idx == 1
    assert user.skills == []

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentState)
    assert app.questions[1].user_answer == "second answer"
    assert app.current_idx == 2
    assert user.skills == []


def test_assessment_evaluates_after_batch_and_appends_guided_follow_up() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    state = AssessmentState(
        questions=_answered_questions(ASSESSMENT_QUESTION_BATCH_SIZE),
        current_idx=ASSESSMENT_QUESTION_BATCH_SIZE,
    )
    llm = ScriptedLLMClient(
        [
            _fluency(confidence="high", guidance="Probe harder past tense."),
            _batch("Follow-up"),
        ]
    )
    mediator = ScriptedMediator([])
    handler = AssessmentHandler(mediator, llm)

    app, _user = asyncio.run(
        handler.step(state, UserState(profile=UserProfile(target_language="Spanish")))
    )

    assert isinstance(app, AssessmentState)
    assert len(app.questions) == ASSESSMENT_QUESTION_BATCH_SIZE * 2
    assert app.current_idx == ASSESSMENT_QUESTION_BATCH_SIZE
    rendered_follow_up = "\n".join(message.content for message in llm.calls[-1])
    assert "Probe harder past tense" in rendered_follow_up
    assert "answer 1" in rendered_follow_up


def test_assessment_stops_on_high_confidence_after_minimum_questions() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    state = AssessmentState(
        questions=_answered_questions(MIN_ASSESSMENT_QUESTIONS),
        current_idx=MIN_ASSESSMENT_QUESTIONS,
    )
    llm = ScriptedLLMClient([_fluency(confidence="high")])
    mediator = ScriptedMediator([])
    handler = AssessmentHandler(mediator, llm)

    app, user = asyncio.run(
        handler.step(state, UserState(profile=UserProfile(target_language="Spanish")))
    )

    assert isinstance(app, AssessmentReviewState)
    assert app.fluency_level == "A1"
    assert "Basic greetings" in app.fluency_rationale
    assert len(app.assessment_questions) == MIN_ASSESSMENT_QUESTIONS
    assert user.skills == []


def test_assessment_continues_on_low_confidence_after_minimum_questions() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    state = AssessmentState(
        questions=_answered_questions(MIN_ASSESSMENT_QUESTIONS),
        current_idx=MIN_ASSESSMENT_QUESTIONS,
    )
    llm = ScriptedLLMClient(
        [
            _fluency(confidence="low", guidance="Check basic vocabulary."),
            _batch("Vocabulary"),
        ]
    )
    mediator = ScriptedMediator([])
    handler = AssessmentHandler(mediator, llm)

    app, _user = asyncio.run(
        handler.step(state, UserState(profile=UserProfile(target_language="Spanish")))
    )

    assert isinstance(app, AssessmentState)
    expected_count = MIN_ASSESSMENT_QUESTIONS + ASSESSMENT_QUESTION_BATCH_SIZE
    assert len(app.questions) == expected_count
    rendered_follow_up = "\n".join(message.content for message in llm.calls[-1])
    assert "Check basic vocabulary" in rendered_follow_up


def test_assessment_forces_review_at_maximum_questions() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    state = AssessmentState(
        questions=_answered_questions(MAX_ASSESSMENT_QUESTIONS),
        current_idx=MAX_ASSESSMENT_QUESTIONS,
    )
    llm = ScriptedLLMClient([_fluency(confidence="low")])
    mediator = ScriptedMediator([])
    handler = AssessmentHandler(mediator, llm)

    app, _user = asyncio.run(
        handler.step(state, UserState(profile=UserProfile(target_language="Spanish")))
    )

    assert isinstance(app, AssessmentReviewState)
    assert len(app.assessment_questions) == MAX_ASSESSMENT_QUESTIONS


def test_assessment_resumes_from_current_index() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    questions = _answered_questions(MIN_ASSESSMENT_QUESTIONS - 1)
    questions.append(AssessmentQuestion(text="Pending"))
    llm = ScriptedLLMClient([_fluency(confidence="high")])
    mediator = ScriptedMediator(["pending answer"])
    handler = AssessmentHandler(mediator, llm)

    app, user = asyncio.run(
        handler.step(
            AssessmentState(
                questions=questions,
                current_idx=MIN_ASSESSMENT_QUESTIONS - 1,
            ),
            UserState(profile=UserProfile(target_language="Spanish")),
        )
    )

    assert isinstance(app, AssessmentState)
    assert app.current_idx == MIN_ASSESSMENT_QUESTIONS
    assert app.questions[-1].user_answer == "pending answer"
    assert len(llm.calls) == 0

    app, _user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentReviewState)
    assert len(llm.calls) == 1
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "answer 1" in rendered
    assert "pending answer" in rendered


def test_assessment_retry_after_timeout_preserves_answered_questions() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    state = AssessmentState(
        questions=_answered_questions(MIN_ASSESSMENT_QUESTIONS),
        current_idx=MIN_ASSESSMENT_QUESTIONS,
    )
    llm = ScriptedLLMClient(
        [
            LLMError("timeout"),
            _fluency(confidence="high", guidance="Retry succeeded."),
        ]
    )
    mediator = ScriptedMediator([True])
    handler = AssessmentHandler(mediator, llm)

    app, _user = asyncio.run(
        handler.step(state, UserState(profile=UserProfile(target_language="Spanish")))
    )

    assert isinstance(app, AssessmentReviewState)
    assert app.fluency_level == "A1"
    assert mediator.errors == ["timeout"]
    rendered_retry = "\n".join(message.content for message in llm.calls[-1])
    assert "answer 1" in rendered_retry


def test_assessment_declined_retry_raises_llm_error() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLLMClient([LLMError("provider unavailable")])
    mediator = ScriptedMediator([False])
    handler = AssessmentHandler(mediator, llm)

    with pytest.raises(LLMError, match="provider unavailable"):
        asyncio.run(
            handler.step(
                AssessmentState(),
                UserState(profile=UserProfile(target_language="Spanish")),
            )
        )

    assert mediator.errors == ["provider unavailable"]
