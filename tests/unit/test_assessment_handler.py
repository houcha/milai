import asyncio

from milai.llm.errors import LLMError
from milai.llm.prompts.assessment import AssessmentQuestionBatch, FluencyResult
from milai.models.assessment import AssessmentQuestion
from milai.models.user_state import UserProfile, UserState
from milai.state.handlers.assessment import AssessmentHandler
from milai.state.variants import AssessmentReviewState, AssessmentState


def test_assessment_generates_questions_captures_answers_and_computes_fluency() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    question = AssessmentQuestion(
        text="Translate: good morning",
        difficulty="beginner",
    )
    second_question = AssessmentQuestion(
        text="Translate: good night",
        difficulty="beginner",
    )
    llm = ScriptedLLMClient(
        [
            AssessmentQuestionBatch(questions=[question, second_question]),
            FluencyResult(
                fluency_level="A1",
                rationale="Basic greetings are emerging.",
            ),
        ]
    )
    mediator = ScriptedMediator(["morning answer", "night answer"])
    handler = AssessmentHandler(mediator, llm)

    app, user = asyncio.run(
        handler.step(
            AssessmentState(),
            UserState(profile=UserProfile(target_language="Spanish")),
        )
    )
    assert isinstance(app, AssessmentState)
    assert app.questions == [question, second_question]
    assert app.current_idx == 0
    assert len(llm.calls) == 1

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentState)
    assert app.questions[0].user_answer == "morning answer"
    assert app.current_idx == 1
    assert user.skills == []

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentState)
    assert app.questions[1].user_answer == "night answer"
    assert app.current_idx == 2
    assert user.skills == []

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentReviewState)
    assert app.fluency_level == "A1"
    assert "Basic greetings" in app.fluency_rationale
    assert app.assessment_questions[0].user_answer == "morning answer"
    assert app.assessment_questions[1].user_answer == "night answer"
    assert user.skills == []
    assert len(llm.calls) == 2


def test_assessment_resumes_from_current_index() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    questions = [
        AssessmentQuestion(
            text="Answered",
            user_answer="hello answer",
        ),
        AssessmentQuestion(text="Pending"),
    ]
    llm = ScriptedLLMClient([FluencyResult(fluency_level="A2", rationale="Steady.")])
    mediator = ScriptedMediator(["bread answer"])
    handler = AssessmentHandler(mediator, llm)

    app, user = asyncio.run(
        handler.step(
            AssessmentState(questions=questions, current_idx=1),
            UserState(profile=UserProfile(target_language="Spanish")),
        )
    )

    assert isinstance(app, AssessmentState)
    assert app.current_idx == 2
    assert app.questions[1].user_answer == "bread answer"
    assert len(llm.calls) == 0

    app, _user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentReviewState)
    assert len(llm.calls) == 1
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "hello answer" in rendered
    assert "bread answer" in rendered


def test_assessment_retry_after_timeout_preserves_answered_questions() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    question = AssessmentQuestion(text="Say thanks")
    second_question = AssessmentQuestion(text="Say please")
    llm = ScriptedLLMClient(
        [
            AssessmentQuestionBatch(questions=[question, second_question]),
            LLMError("timeout"),
            FluencyResult(fluency_level="A1", rationale="Retry succeeded."),
        ]
    )
    mediator = ScriptedMediator(["thanks answer", "please answer", True])
    handler = AssessmentHandler(mediator, llm)

    app, user = asyncio.run(
        handler.step(
            AssessmentState(),
            UserState(profile=UserProfile(target_language="Spanish")),
        )
    )
    assert isinstance(app, AssessmentState)

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentState)
    assert app.questions[0].user_answer == "thanks answer"
    assert user.skills == []

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentState)
    assert app.questions[1].user_answer == "please answer"
    assert user.skills == []

    app, user = asyncio.run(handler.step(app, user))
    assert isinstance(app, AssessmentReviewState)
    assert app.fluency_level == "A1"
    assert mediator.errors == ["timeout"]
    rendered_retry = "\n".join(message.content for message in llm.calls[-1])
    assert "thanks answer" in rendered_retry


def test_assessment_declined_retry_raises_llm_error() -> None:
    import pytest

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
