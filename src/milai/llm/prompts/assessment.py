"""Assessment prompt builders and response schemas."""

from pydantic import BaseModel, Field

from milai.llm.types import Message, Role
from milai.models.assessment import AssessmentQuestion
from milai.models.user_state import UserState
from milai.state.variants import AssessmentState

ASSESSMENT_QUESTION_BATCH_SIZE = 2


class AssessmentQuestionBatch(BaseModel):
    # Gemini structured output fails with `500 - Internal error` if min_length > 1
    # and max_length is not specified, so set both to the same value.
    questions: list[AssessmentQuestion] = Field(
        min_length=ASSESSMENT_QUESTION_BATCH_SIZE,
        max_length=ASSESSMENT_QUESTION_BATCH_SIZE,
    )


class FluencyResult(BaseModel):
    fluency_level: str
    rationale: str


def build_question_prompt(
    state: AssessmentState,
    user: UserState,
) -> list[Message]:
    profile = user.profile
    assessment_history = [
        f"{question.difficulty} question: {question.text}: {question.user_answer}"
        for question in state.questions
        if question.user_answer
    ]
    return [
        Message(
            role=Role.SYSTEM,
            content=(
                "You are a language tutor creating adaptive assessment questions. "
                "Return JSON matching the requested schema."
            ),
        ),
        Message(
            role=Role.USER,
            content=(
                f"Target language: {profile.target_language}. "
                f"Native language: {profile.native_language}. "
                f"Goal: {profile.learning_goal}. "
                f"Teaching preferences: {profile.preferences}. "
                f"Assessment history: {assessment_history or 'none'}. "
                "Generate adaptive questions with difficulty."
            ),
        ),
    ]


def build_fluency_prompt(
    state: AssessmentState,
    user: UserState,
) -> list[Message]:
    answered = [
        f"{question.difficulty} question: {question.text}: {question.user_answer}"
        for question in state.questions
        if question.user_answer
    ]
    return [
        Message(
            role=Role.SYSTEM,
            content="You estimate language fluency and return structured JSON.",
        ),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Completed assessment answers: {answered}."
            ),
        ),
    ]
