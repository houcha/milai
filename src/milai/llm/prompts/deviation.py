"""Deviation chat prompt builder."""

from milai.llm.types import Message, Role
from milai.models.user_state import UserState
from milai.state.variants import DeviationState


def build_chat_prompt(
    state: DeviationState,
    user: UserState,
    *,
    user_message: str = "",
) -> list[Message]:
    return [
        Message(
            role=Role.SYSTEM,
            content=(
                "Keep the conversation focused on language learning. "
                "Offer to return to the lesson when the learner is ready."
            ),
        ),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Lesson context: {state.lesson_context}. "
                f"Recent context: {state.context_window[-10:]}. "
                f"User message: {user_message}."
            ),
        ),
    ]
