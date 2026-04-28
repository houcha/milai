"""Exercise feedback prompt builder and response schema."""

from pydantic import BaseModel

from milai.llm.types import Message, Role
from milai.models.curriculum import Exercise
from milai.models.user_state import UserState


class ExerciseFeedback(BaseModel):
    feedback: str
    is_correct: bool | None = None
    skill_topics: list[str] = []


def build_feedback_prompt(
    exercise: Exercise,
    user: UserState,
    *,
    answer: str = "",
    lesson_context: str = "",
) -> list[Message]:
    return [
        Message(role=Role.SYSTEM, content="Evaluate the learner answer as JSON."),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Lesson context: {lesson_context}. "
                f"Exercise: {exercise.model_dump()}. Answer: {answer}."
            ),
        ),
    ]
