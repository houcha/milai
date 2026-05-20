from milai.llm.prompts.deviation import (
    MAX_DEVIATION_CONTEXT_MESSAGES,
    build_chat_prompt,
)
from milai.llm.types import Message, Role
from milai.models.user_state import UserProfile, UserState
from milai.state.variants import DeviationState


def test_deviation_prompt_includes_bounded_context_return_and_guardrails() -> None:
    context = [
        Message(
            role=Role.USER if index % 2 == 0 else Role.ASSISTANT, content=f"m{index}"
        )
        for index in range(MAX_DEVIATION_CONTEXT_MESSAGES + 4)
    ]
    state = DeviationState(
        context_window=context,
        lesson_context="Travel Basics / Greetings",
    )
    user = UserState(profile=UserProfile(target_language="Spanish", fluency_level="A1"))

    rendered = "\n".join(
        message.content
        for message in build_chat_prompt(
            state,
            user,
            user_message="Why is buenos dias plural?",
        )
    )

    assert "Travel Basics / Greetings" in rendered
    assert "Why is buenos dias plural?" in rendered
    assert "return to the lesson" in rendered.lower()
    assert "off-topic" in rendered.lower()
    assert "m0" not in rendered
    assert f"m{MAX_DEVIATION_CONTEXT_MESSAGES + 3}" in rendered
