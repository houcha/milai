"""Curriculum prompt builders and response schemas."""

from pydantic import BaseModel, Field

from milai.llm.types import Message, Role
from milai.models.curriculum import Curriculum
from milai.models.user_state import Skill, UserState
from milai.state.variants import (
    CurriculumCompleteState,
    CurriculumGenerationState,
    CurriculumReviewState,
)


class CurriculumDraft(BaseModel):
    curriculum: Curriculum
    initial_skills: list[Skill] = Field(default_factory=list)


def build_generation_prompt(
    state: CurriculumGenerationState,
    user: UserState,
) -> list[Message]:
    assessment_answers = [
        (f"{question.difficulty} question: {question.text}: {question.user_answer}")
        for question in state.assessment_questions
        if question.user_answer
    ]
    return [
        Message(
            role=Role.SYSTEM,
            content=(
                "Create a language-learning curriculum as JSON. "
                "Infer exact initial skill topics from the completed assessment "
                "answers and include them as initial_skills."
            ),
        ),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Completed assessment answers: {assessment_answers or 'none'}. "
                f"Existing skills: {[skill.model_dump() for skill in user.skills]}."
            ),
        ),
    ]


def build_adjustment_prompt(
    state: CurriculumReviewState,
    user: UserState,
    *,
    feedback: str = "",
) -> list[Message]:
    _ = state
    return [
        Message(role=Role.SYSTEM, content="Revise the curriculum draft as JSON."),
        Message(
            role=Role.USER,
            content=f"Current curriculum: {user.curriculum}. Feedback: {feedback}.",
        ),
    ]


def build_extension_prompt(
    state: CurriculumCompleteState,
    user: UserState,
    *,
    completed_skills: list[Skill] | None = None,
) -> list[Message]:
    _ = state
    skills = completed_skills if completed_skills is not None else user.skills
    return [
        Message(role=Role.SYSTEM, content="Extend the completed curriculum as JSON."),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Completed curriculum: {user.curriculum}. "
                f"Skill strengths: {[skill.model_dump() for skill in skills]}."
            ),
        ),
    ]
