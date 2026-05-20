"""Deviation state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.llm.client import LLMClient
from milai.llm.errors import LLMError
from milai.llm.prompts.deviation import (
    MAX_DEVIATION_CONTEXT_MESSAGES,
    build_chat_prompt,
)
from milai.llm.types import Message, Role
from milai.models.user_state import UserState
from milai.state.variants import AppState, DeviationState, LessonState

DEVIATION_LLM_TIMEOUT_SECONDS = 60
RETURN_COMMANDS = {"return", "back", "lesson", "/return", "/back"}


class DeviationHandler:
    def __init__(self, mediator: IOMediator, llm: LLMClient) -> None:
        self._mediator = mediator
        self._llm = llm

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[DeviationState | LessonState, UserState]:
        if not isinstance(app, DeviationState):
            raise TypeError(f"DeviationHandler cannot handle {app.type!r}")

        await self._mediator.show(
            RichContent("Ask about this lesson", kind=ContentKind.HEADER)
        )
        user_message = await self._mediator.prompt(
            "Question",
            placeholder="type return to resume the lesson",
        )
        if user_message.strip().lower() in RETURN_COMMANDS:
            return LessonState(), user

        reply = await self._chat(app, user, user_message=user_message)
        await self._mediator.show(RichContent(reply, kind=ContentKind.MARKDOWN))
        next_state = app.model_copy(
            update={
                "context_window": _cap_context(
                    [
                        *app.context_window,
                        Message(role=Role.USER, content=user_message),
                        Message(role=Role.ASSISTANT, content=reply),
                    ]
                )
            }
        )
        return next_state, user

    async def _chat(
        self,
        state: DeviationState,
        user: UserState,
        *,
        user_message: str,
    ) -> str:
        while True:
            try:
                return await self._llm.chat(
                    build_chat_prompt(state, user, user_message=user_message),
                    timeout=DEVIATION_LLM_TIMEOUT_SECONDS,
                )
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")


def _cap_context(messages: list[Message]) -> list[Message]:
    return messages[-MAX_DEVIATION_CONTEXT_MESSAGES:]
