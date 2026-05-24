from milai.llm.prompts.assessment import (
    AssessmentQuestionBatch,
    FluencyResult,
    build_fluency_prompt,
    build_question_prompt,
)
from milai.llm.types import Message, Role
from milai.models.assessment import AssessmentQuestion
from milai.models.user_state import UserProfile, UserState
from milai.state.variants import AssessmentState


def test_question_prompt_includes_profile_assessment_hist_and_schema_context() -> None:
    user = UserState(
        profile=UserProfile(
            target_language="Spanish",
            native_language="English",
            learning_goal="travel",
            preferences={"avoid": "grammar jargon"},
        )
    )
    state = AssessmentState(
        current_idx=1,
        questions=[
            AssessmentQuestion(
                text="Translate: I need a ticket",
                user_answer="ticket answer",
                difficulty="beginner",
            )
        ],
        assessment_messages=[
            Message(role=Role.USER, content="Previous answer from section history.")
        ],
    )

    rendered = "\n".join(
        message.content for message in build_question_prompt(state, user)
    )

    assert "Spanish" in rendered
    assert "English" in rendered
    assert "travel" in rendered
    assert "grammar jargon" in rendered
    assert "ticket answer" in rendered
    assert "Previous answer from section history." in rendered
    assert "Current question index" not in rendered
    assert "Follow-up guidance" in rendered
    assert "difficulty" in rendered.lower()
    assert AssessmentQuestionBatch.model_validate(
        {
            "questions": [
                {
                    "text": "Say hello",
                    "difficulty": "beginner",
                },
                {
                    "text": "Say goodbye",
                    "difficulty": "beginner",
                },
            ]
        }
    )


def test_fluency_prompt_includes_answered_questions_and_validates_result() -> None:
    user = UserState(profile=UserProfile(target_language="French"))
    state = AssessmentState(
        current_idx=1,
        questions=[
            AssessmentQuestion(
                text="Introduce yourself",
                user_answer="intro answer",
                difficulty="beginner",
            )
        ],
        assessment_messages=[
            Message(role=Role.ASSISTANT, content="Prior assessment question.")
        ],
    )

    rendered = "\n".join(
        message.content for message in build_fluency_prompt(state, user)
    )

    assert "French" in rendered
    assert "intro answer" in rendered
    assert "Prior assessment question." in rendered
    assert FluencyResult.model_validate(
        {
            "fluency_level": "A1",
            "rationale": "Short but correct.",
            "confidence": "high",
            "follow_up_guidance": "No follow-up needed.",
        }
    )
