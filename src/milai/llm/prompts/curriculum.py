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


CURRICULUM_DISPLAY_STYLE = (
    "Use short module titles, usually 1-4 words. Put explanatory detail in "
    "Module.description, not Module.title. Treat Module.description as the "
    "module goal. Use concise, specific lesson titles that are individually "
    "scannable in a numbered curriculum review."
)


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
                "You are designing a self-paced language-learning curriculum. "
                "Return strict JSON matching the CurriculumDraft schema. "
                "Infer durable initial skill topics from the completed assessment "
                "answers at curriculum-level granularity, normalize topic names, "
                "and include them as initial_skills. Do not attach skills to "
                "individual assessment questions."
            ),
        ),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Target language: {user.profile.target_language}. "
                f"Confirmed fluency: {user.profile.fluency_level}. "
                f"Learning goal: {user.profile.learning_goal}. "
                f"Minutes per day: {user.profile.minutes_per_day}. "
                f"Teaching preferences: {user.profile.preferences}. "
                f"Completed assessment answers: {assessment_answers or 'none'}. "
                "Create 3 to 20 modules with concise lesson placeholders that can "
                "later be expanded into full lessons. "
                f"{CURRICULUM_DISPLAY_STYLE}"
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
        Message(
            role=Role.SYSTEM,
            content=(
                "Revise the learner's curriculum draft as strict JSON matching "
                "the CurriculumDraft schema. Preserve useful existing structure, "
                "apply the learner's feedback, and return only new initial_skills "
                "if the revision introduces new durable skill topics."
            ),
        ),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Current curriculum: {user.curriculum}. "
                f"Learner feedback: {feedback}. "
                f"{CURRICULUM_DISPLAY_STYLE}"
            ),
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
                f"Skill strengths: {[skill.model_dump() for skill in skills]}. "
                f"{CURRICULUM_DISPLAY_STYLE}"
            ),
        ),
    ]
