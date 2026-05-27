import asyncio
from typing import cast

import pytest

from milai.agents.assessment import AssessmentInterviewer, AssessmentPhase
from milai.llm.errors import LLMError
from milai.llm.types import Message, Role
from milai.models.assessment import AssessmentQuestion, Diagnosis, NextQuestion, Retry
from milai.models.session import LearningSession
from milai.models.user_state import UserProfile, UserState
from milai.state.handlers.assessment import (
    MAX_ASSESSMENT_QUESTIONS,
    MIN_USABLE_ASSESSMENT_EVIDENCE,
    AssessmentHandler,
)
from milai.state.variants import (
    AssessmentReviewState,
    AssessmentState,
)


def _user() -> UserState:
    return UserState(profile=UserProfile(target_language="Spanish"))


def _session(app: AssessmentState | AssessmentReviewState, user: UserState):
    return LearningSession(app=app, user=user)


def _question(text: str, answer: str | None = None) -> AssessmentQuestion:
    return AssessmentQuestion(text=text, user_answer=answer)


def _answered(count: int) -> list[AssessmentQuestion]:
    return [
        _question(f"Question {idx}", f"answer {idx}") for idx in range(1, count + 1)
    ]


def _interviewer(scripted: object) -> AssessmentInterviewer:
    return cast(AssessmentInterviewer, scripted)


def _next_question(text: str) -> NextQuestion:
    return NextQuestion(
        action="next_question",
        text=text,
        difficulty="beginner",
        rationale="Need one more evidence point.",
    )


def _first_question(text: str) -> NextQuestion:
    return NextQuestion(
        action="next_question",
        text=text,
        difficulty="beginner",
        rationale="Need first evidence point.",
    )


def _retry(text: str = "Try again in Spanish.") -> Retry:
    return Retry(
        action="retry",
        retry_reason="No usable target-language answer.",
        message="Please answer in the target language so I can assess it.",
        text=text,
    )


def _diagnosis(level: str = "A1") -> Diagnosis:
    return Diagnosis(
        action="diagnosis",
        fluency_level=level,
        rationale="Evidence supports placement.",
        confidence="high",
        evidence_summary="Consistent confirmed answers.",
    )


def _assistant_result(result: NextQuestion | Retry | Diagnosis) -> Message:
    return Message(role=Role.ASSISTANT, content=result.model_dump_json())


def _usable_evidence_messages(count: int) -> list[Message]:
    return [
        _assistant_result(_next_question(f"Recorded follow-up {idx}."))
        for idx in range(1, count + 1)
    ]


def test_assessment_starts_with_one_question() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([_first_question("Say good morning.")])
    handler = AssessmentHandler(
        ScriptedMediator([]),
        _interviewer(interviewer),
    )

    session = _session(AssessmentState(), _user())
    result = asyncio.run(handler.step(session))
    app = result.app
    user = result.user

    assert isinstance(app, AssessmentState)
    assert user.skills == []
    assert [question.text for question in app.questions] == ["Say good morning."]
    assert [message.role for message in app.assessment_messages] == [Role.ASSISTANT]
    assert len(interviewer.calls) == 1
    assert interviewer.calls[0].method == "next_action"
    assert interviewer.calls[0].args[2] is AssessmentPhase.INITIAL
    assert "metadata" not in interviewer.calls[0].kwargs


def test_assessment_records_strong_answer_then_asks_one_follow_up() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer(
        [_next_question("Ask for a train ticket.")]
    )
    handler = AssessmentHandler(
        ScriptedMediator(["Buenos dias. Necesito un boleto de tren."]),
        _interviewer(interviewer),
    )
    state = AssessmentState(questions=[_question("Greet the clerk.")])

    result = asyncio.run(handler.step(_session(state, _user())))
    result = asyncio.run(handler.step(result))
    app = result.app

    assert isinstance(app, AssessmentState)
    assert app.questions[0].user_answer == "Buenos dias. Necesito un boleto de tren."
    assert app.questions[1].text == "Ask for a train ticket."
    assert [message.role for message in app.assessment_messages] == [
        Role.ASSISTANT,
        Role.USER,
        Role.ASSISTANT,
    ]


def test_assessment_records_weak_mixed_and_contradictory_evidence() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer(
        [
            _next_question("Use a past-tense sentence."),
            _next_question("Repair the contradiction."),
            _diagnosis("A2"),
        ]
    )
    mediator = ScriptedMediator(
        [
            "Hola",
            "Ayer voy al museo",
            "I know past tense but cannot form it yet",
        ]
    )
    handler = AssessmentHandler(mediator, _interviewer(interviewer))
    app: AssessmentState | AssessmentReviewState = AssessmentState(
        questions=[
            *_answered(MIN_USABLE_ASSESSMENT_EVIDENCE - 3),
            _question("Say hello."),
        ],
        assessment_messages=_usable_evidence_messages(
            MIN_USABLE_ASSESSMENT_EVIDENCE - 3
        ),
    )
    user = _user()

    for _idx in range(6):
        result = asyncio.run(handler.step(_session(app, user)))
        app = cast(AssessmentState | AssessmentReviewState, result.app)
        user = result.user
        if isinstance(app, AssessmentReviewState):
            break

    assert isinstance(app, AssessmentReviewState)
    assert app.fluency_level == "A2"
    assert len(app.assessment_questions) == MIN_USABLE_ASSESSMENT_EVIDENCE
    assert app.assessment_questions[-1].user_answer == (
        "I know past tense but cannot form it yet"
    )


def test_assessment_retries_unusable_answer_without_extra_unanswered_items() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([_retry("Please answer in Spanish.")])
    mediator = ScriptedMediator(["I do not know"])
    handler = AssessmentHandler(
        mediator,
        _interviewer(interviewer),
    )
    state = AssessmentState(questions=[_question("Say good night.")])

    result = asyncio.run(handler.step(_session(state, _user())))
    result = asyncio.run(handler.step(result))
    app = result.app

    assert isinstance(app, AssessmentState)
    assert app.questions[0].text == "Please answer in Spanish."
    assert app.questions[0].user_answer is None
    assert sum(question.user_answer is None for question in app.questions) == 1
    assert app.assessment_messages[-2].content == "I do not know"
    assert [content.text for content in mediator.shown] == [
        "Question 1",
        "Please answer in the target language so I can assess it.",
    ]


def test_assessment_uses_collecting_phase_before_minimum_evidence() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([_next_question("Need more evidence.")])
    handler = AssessmentHandler(
        ScriptedMediator([]),
        _interviewer(interviewer),
    )

    result = asyncio.run(
        handler.step(
            _session(
                AssessmentState(
                    questions=_answered(MIN_USABLE_ASSESSMENT_EVIDENCE - 1)
                ),
                _user(),
            )
        )
    )
    app = result.app

    assert isinstance(app, AssessmentState)
    assert interviewer.calls[0].args[2] is AssessmentPhase.COLLECTING


def test_assessment_diagnoses_after_minimum_evidence() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([_diagnosis("A1")])
    handler = AssessmentHandler(ScriptedMediator([]), _interviewer(interviewer))

    result = asyncio.run(
        handler.step(
            _session(
                AssessmentState(
                    questions=_answered(MIN_USABLE_ASSESSMENT_EVIDENCE),
                    assessment_messages=_usable_evidence_messages(
                        MIN_USABLE_ASSESSMENT_EVIDENCE - 1
                    ),
                ),
                _user(),
            )
        )
    )
    app = result.app

    assert isinstance(app, AssessmentReviewState)
    assert app.fluency_level == "A1"
    assert len(app.assessment_questions) == MIN_USABLE_ASSESSMENT_EVIDENCE


def test_assessment_ignores_retry_messages_when_counting_usable_evidence() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([_next_question("Need more evidence.")])
    handler = AssessmentHandler(
        ScriptedMediator([]),
        _interviewer(interviewer),
    )

    result = asyncio.run(
        handler.step(
            _session(
                AssessmentState(
                    questions=_answered(MIN_USABLE_ASSESSMENT_EVIDENCE - 1),
                    assessment_messages=[
                        *_usable_evidence_messages(MIN_USABLE_ASSESSMENT_EVIDENCE - 2),
                        _assistant_result(_retry()),
                        _assistant_result(_retry()),
                    ],
                ),
                _user(),
            )
        )
    )
    app = result.app

    assert isinstance(app, AssessmentState)
    assert interviewer.calls[0].args[2] is AssessmentPhase.COLLECTING


def test_assessment_forces_diagnosis_at_maximum_items() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([_diagnosis("A1")])
    handler = AssessmentHandler(ScriptedMediator([]), _interviewer(interviewer))

    result = asyncio.run(
        handler.step(
            _session(
                AssessmentState(
                    questions=_answered(MAX_ASSESSMENT_QUESTIONS),
                    assessment_messages=[
                        *_usable_evidence_messages(MIN_USABLE_ASSESSMENT_EVIDENCE - 2),
                        _assistant_result(_retry()),
                        _assistant_result(_retry()),
                    ],
                ),
                _user(),
            )
        )
    )
    app = result.app

    assert isinstance(app, AssessmentReviewState)
    assert interviewer.calls[0].args[2] is AssessmentPhase.FORCED_DIAGNOSIS


def test_assessment_requests_forced_diagnosis_after_maximum_items() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([_diagnosis("A1")])
    handler = AssessmentHandler(
        ScriptedMediator([]),
        _interviewer(interviewer),
    )

    result = asyncio.run(
        handler.step(
            _session(
                AssessmentState(questions=_answered(MAX_ASSESSMENT_QUESTIONS)),
                _user(),
            )
        )
    )
    app = result.app

    assert isinstance(app, AssessmentReviewState)
    assert interviewer.calls[0].args[2] is AssessmentPhase.FORCED_DIAGNOSIS


def test_assessment_declined_retry_raises_llm_error() -> None:
    from tests.fakes.adaptive_agents import ScriptedAssessmentInterviewer
    from tests.fakes.mediator import ScriptedMediator

    interviewer = ScriptedAssessmentInterviewer([LLMError("provider unavailable")])
    mediator = ScriptedMediator([False])
    handler = AssessmentHandler(mediator, _interviewer(interviewer))

    with pytest.raises(LLMError, match="provider unavailable"):
        asyncio.run(handler.step(_session(AssessmentState(), _user())))

    assert mediator.errors == ["provider unavailable"]
