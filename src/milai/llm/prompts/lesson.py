"""Lesson prompt builders and response schemas."""

from pydantic import BaseModel

from milai.llm.types import Message, Role
from milai.models.curriculum import Lesson
from milai.models.user_state import Skill, UserState
from milai.state.variants import LessonState


class LessonContent(BaseModel):
    lesson: Lesson


def build_lesson_prompt(
    state: LessonState,
    user: UserState,
    *,
    review_skills: list[Skill] | None = None,
) -> list[Message]:
    _ = state
    return [
        Message(
            role=Role.SYSTEM,
            content="Generate lesson content as structured JSON.",
        ),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Curriculum: {user.curriculum}. "
                f"Review skills: {[skill.topic for skill in review_skills or []]}."
            ),
        ),
    ]


def build_dynamic_change_prompt(
    state: LessonState,
    user: UserState,
    *,
    requested_change: str = "",
) -> list[Message]:
    _ = state
    return [
        Message(
            role=Role.SYSTEM,
            content="Adjust the active lesson as structured JSON.",
        ),
        Message(
            role=Role.USER,
            content=(
                f"Current curriculum: {user.curriculum}. "
                f"Requested change: {requested_change}."
            ),
        ),
    ]
