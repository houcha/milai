"""Assessment prompt builders and response schemas."""

from pydantic import BaseModel, Field

from milai.llm.types import Message, Role
from milai.models.assessment import AssessmentQuestion
from milai.models.user_state import UserState
from milai.state.variants import AssessmentState


class AssessmentQuestionBatch(BaseModel):
    questions: list[AssessmentQuestion] = Field(min_length=1)


class FluencyResult(BaseModel):
    fluency_level: str
    rationale: str


def build_question_prompt(
    state: AssessmentState,
    user: UserState,
) -> list[Message]:
    profile = user.profile
    prior_answers = [
        f"{question.text}: {question.user_answer}"
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
                f"Current question index: {state.current_idx}. "
                f"Prior answers: {prior_answers or 'none'}."
            ),
        ),
    ]


def build_fluency_prompt(
    state: AssessmentState,
    user: UserState,
) -> list[Message]:
    answered = [
        f"{question.difficulty} - {question.text}: {question.user_answer}"
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
