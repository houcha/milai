import asyncio

import pytest

from milai.llm.errors import LLMError
from milai.llm.prompts.deviation import MAX_DEVIATION_CONTEXT_MESSAGES
from milai.llm.types import Message, Role
from milai.models.session import LearningSession
from milai.models.user_state import UserProfile, UserState
from milai.state.handlers.deviation import DeviationHandler
from milai.state.variants import DeviationState, LessonState


def test_deviation_handler_chats_and_caps_context_window() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    old_context = [
        Message(
            role=Role.USER if index % 2 == 0 else Role.ASSISTANT, content=f"m{index}"
        )
        for index in range(MAX_DEVIATION_CONTEXT_MESSAGES)
    ]
    llm = ScriptedLLMClient(["Because it is an idiomatic greeting."])
    handler = DeviationHandler(ScriptedMediator(["Why plural?"]), llm)

    result = asyncio.run(
        handler.step(
            LearningSession(
                app=DeviationState(
                    context_window=old_context,
                    lesson_context="Basics / Greetings",
                ),
                user=UserState(profile=UserProfile(target_language="Spanish")),
            )
        )
    )
    app = result.app

    assert isinstance(app, DeviationState)
    assert len(app.context_window) == MAX_DEVIATION_CONTEXT_MESSAGES
    assert app.context_window[-2].content == "Why plural?"
    assert app.context_window[-1].content == "Because it is an idiomatic greeting."
    assert app.context_window[0].content == "m2"


def test_deviation_handler_retry_and_return_to_lesson() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    llm = ScriptedLLMClient([LLMError("timeout"), "retry answer"])
    mediator = ScriptedMediator(["Explain hola", True])
    handler = DeviationHandler(mediator, llm)

    result = asyncio.run(
        handler.step(
            LearningSession(
                app=DeviationState(lesson_context="Basics"), user=UserState()
            )
        )
    )
    app = result.app

    assert isinstance(app, DeviationState)
    assert mediator.errors == ["timeout"]
    assert len(llm.calls) == 2

    result = asyncio.run(
        DeviationHandler(ScriptedMediator(["return"]), ScriptedLLMClient([])).step(
            LearningSession(app=app, user=UserState())
        )
    )
    app = result.app
    assert isinstance(app, LessonState)


def test_deviation_handler_declined_retry_preserves_context() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator

    state = DeviationState(
        context_window=[Message(role=Role.USER, content="old")],
        lesson_context="Basics",
    )
    handler = DeviationHandler(
        ScriptedMediator(["new question", False]),
        ScriptedLLMClient([LLMError("timeout")]),
    )

    with pytest.raises(LLMError, match="timeout"):
        asyncio.run(handler.step(LearningSession(app=state, user=UserState())))

    assert [message.content for message in state.context_window] == ["old"]
