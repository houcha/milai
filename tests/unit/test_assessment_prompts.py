import asyncio

from milai.agents.assessment import (
    AssessmentInterviewer,
    AssessmentPhase,
    build_assessment_step_instructions,
    build_assessment_system_prompt,
)
from milai.llm.types import Message, Role
from milai.models.assessment import Diagnosis, NextQuestion, Retry
from milai.models.user_state import UserProfile, UserState
from milai.state.handlers.assessment import (
    MAX_ASSESSMENT_QUESTIONS,
    MIN_USABLE_ASSESSMENT_EVIDENCE,
)
from milai.state.variants import AssessmentState


def _assistant_result(result: NextQuestion | Retry | Diagnosis) -> Message:
    return Message(role=Role.ASSISTANT, content=result.model_dump_json())


def test_assessment_system_prompt_includes_stable_profile_context() -> None:
    user = UserState(
        profile=UserProfile(
            target_language="Spanish",
            native_language="English",
            learning_goal="travel",
            preferences={"avoid": "grammar jargon"},
        )
    )

    message = build_assessment_system_prompt(user)
    rendered = message.content

    assert message.role is Role.SYSTEM
    assert "Spanish" in rendered
    assert "English" in rendered
    assert "travel" in rendered
    assert "grammar jargon" in rendered
    assert "structured output schema" not in rendered
    assert "Ask one question at a time" not in rendered
    assert "retry" not in rendered.lower()


def test_assessment_step_instructions_exclude_profile_and_history_context() -> None:
    message = build_assessment_step_instructions(
        instructions=(
            "Evaluate the latest learner answer from history. Otherwise record "
            "the evidence and ask a follow-up question."
        ),
        usable_evidence_needed=MIN_USABLE_ASSESSMENT_EVIDENCE - 1,
        question_budget_remaining=MAX_ASSESSMENT_QUESTIONS - 1,
    )
    rendered = message.content

    assert message.role is Role.USER
    assert (
        "Additional usable answers targeted by policy: "
        f"{MIN_USABLE_ASSESSMENT_EVIDENCE - 1}"
    ) in rendered
    assert (
        f"Question budget remaining for new questions: {MAX_ASSESSMENT_QUESTIONS - 1}"
    ) in rendered
    assert "Spanish" not in rendered
    assert "English" not in rendered
    assert "travel" not in rendered
    assert "grammar jargon" not in rendered
    assert "ticket answer" not in rendered
    assert "Previous answer from section history." not in rendered
    assert "ask a follow-up question" in rendered


def test_assessment_interviewer_starts_with_system_and_initial_user_message() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient

    llm = ScriptedLLMClient(
        [
            {
                "action": "next_question",
                "text": "Ask for water.",
                "difficulty": "beginner",
                "rationale": "Need travel request evidence.",
            }
        ]
    )
    interviewer = AssessmentInterviewer(llm)
    user = UserState(
        profile=UserProfile(
            target_language="Spanish",
            native_language="English",
            learning_goal="travel",
            preferences={"avoid": "grammar jargon"},
        )
    )

    asyncio.run(
        interviewer.next_action(
            AssessmentState(),
            user,
            AssessmentPhase.INITIAL,
            usable_evidence_needed=MIN_USABLE_ASSESSMENT_EVIDENCE,
            question_budget_remaining=MAX_ASSESSMENT_QUESTIONS,
        )
    )

    assert [message.role for message in llm.calls[0]] == [Role.SYSTEM, Role.USER]
    system_message = llm.calls[0][0].content
    step_message = llm.calls[0][1].content
    assert "structured output schema" not in system_message
    assert "Spanish" in system_message
    assert "English" in system_message
    assert "travel" in system_message
    assert "grammar jargon" in system_message
    assert "Ask one question at a time" not in system_message
    assert "Spanish" not in step_message
    assert "English" not in step_message
    assert "travel" not in step_message
    assert "grammar jargon" not in step_message
    assert "Ask the first assessment question" in step_message
    assert "Step:" not in step_message
    assert "Question budget remaining for new questions" in step_message


def test_assessment_final_step_avoids_repeating_schema_constraints() -> None:
    message = build_assessment_step_instructions(
        instructions=(
            "Provide the best-supported diagnosis from the available evidence."
        ),
        usable_evidence_needed=0,
        question_budget_remaining=0,
    )
    rendered = message.content

    assert "best-supported diagnosis" in rendered
    assert "Step:" not in rendered
    assert "do not ask another question" not in rendered.lower()


def test_assessment_interviewer_sends_history_before_continuation_policy() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient

    llm = ScriptedLLMClient(
        [
            {
                "action": "next_question",
                "text": "Ask for water.",
                "difficulty": "beginner",
                "rationale": "Need travel request evidence.",
            }
        ]
    )
    interviewer = AssessmentInterviewer(llm)
    state = AssessmentState(
        assessment_messages=[
            Message(role=Role.ASSISTANT, content="Say good morning."),
            Message(role=Role.USER, content="Buenos dias."),
        ]
    )

    asyncio.run(
        interviewer.next_action(
            state,
            UserState(),
            AssessmentPhase.COLLECTING,
            usable_evidence_needed=MIN_USABLE_ASSESSMENT_EVIDENCE - 1,
            question_budget_remaining=MAX_ASSESSMENT_QUESTIONS - 1,
        )
    )

    assert [message.role for message in llm.calls[0]] == [
        Role.SYSTEM,
        Role.ASSISTANT,
        Role.USER,
        Role.USER,
    ]
    assert llm.calls[0][1].content == "Say good morning."
    assert llm.calls[0][2].content == "Buenos dias."
    assert "Question budget remaining" in llm.calls[0][3].content


def test_assessment_actions_validate_expected_variants() -> None:
    assert NextQuestion.model_validate(
        {
            "action": "next_question",
            "text": "Ask for water.",
            "difficulty": "beginner",
            "rationale": "Need travel request evidence.",
        }
    )
    assert Retry(
        action="retry",
        retry_reason="No target-language attempt.",
        message="Please try that in Spanish.",
        text="Try that in Spanish: good morning.",
    )
    assert Diagnosis(
        action="diagnosis",
        fluency_level="A1",
        rationale="Can handle basic greetings.",
        confidence="high",
        evidence_summary="Consistent beginner answers.",
    )
    assert NextQuestion(
        action="next_question",
        text="Say hello.",
        difficulty="beginner",
        rationale="Need first answer.",
    )
