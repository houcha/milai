"""Deviation chat prompt builder."""

from milai.llm.types import Message, Role
from milai.models.user_state import UserState
from milai.state.variants import DeviationState

MAX_DEVIATION_CONTEXT_MESSAGES = 20


def build_chat_prompt(
    state: DeviationState,
    user: UserState,
    *,
    user_message: str = "",
) -> list[Message]:
    recent_context = state.context_window[-MAX_DEVIATION_CONTEXT_MESSAGES:]
    return [
        Message(
            role=Role.SYSTEM,
            content=(
                "You are a helpful language tutor in a temporary deviation from "
                "the active lesson. Keep the conversation focused on language "
                "learning, politely set off-topic boundaries, and offer to return "
                "to the lesson when the learner is ready."
            ),
        ),
        Message(
            role=Role.USER,
            content=(
                f"Profile: {user.profile.model_dump()}. "
                f"Lesson context: {state.lesson_context}. "
                f"Recent bounded context: {recent_context}. "
                f"User message: {user_message}. "
                "Answer the question directly, then make the next lesson step easy."
            ),
        ),
    ]
