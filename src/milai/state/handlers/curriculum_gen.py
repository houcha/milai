"""Curriculum generation state handler."""

from collections.abc import Iterable

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.llm.client import LLMClient
from milai.llm.errors import LLMError
from milai.llm.prompts.curriculum import CurriculumDraft, build_generation_prompt
from milai.llm.types import Message, Role
from milai.models.session import LearningSession
from milai.models.user_state import Skill, UserState
from milai.state.variants import (
    CurriculumGenerationState,
    CurriculumReviewState,
)

CURRICULUM_GENERATION_TIMEOUT_SECONDS = 180


class CurriculumGenerationHandler:
    def __init__(self, mediator: IOMediator, llm: LLMClient) -> None:
        self._mediator = mediator
        self._llm = llm

    async def step(self, session: LearningSession) -> LearningSession:
        app = session.app
        user = session.user
        if not isinstance(app, CurriculumGenerationState):
            raise TypeError(f"CurriculumGenerationHandler cannot handle {app.type!r}")

        await self._mediator.clear()
        await self._mediator.show(
            RichContent("Generating curriculum", kind=ContentKind.HEADER)
        )
        draft = await self._generate_draft(app, user)

        updated = user.model_copy(deep=True)
        updated.curriculum = draft.curriculum
        updated.skills = _merge_skills(updated.skills, draft.initial_skills)
        return session.model_copy(
            update={
                "app": CurriculumReviewState(
                    curriculum_messages=app.curriculum_messages,
                ),
                "user": updated,
            }
        )

    async def _generate_draft(
        self, state: CurriculumGenerationState, user: UserState
    ) -> CurriculumDraft:
        while True:
            try:
                messages = build_generation_prompt(state, user)
                draft = await self._llm.complete(
                    messages,
                    response_model=CurriculumDraft,
                    timeout=CURRICULUM_GENERATION_TIMEOUT_SECONDS,
                )
                state.curriculum_messages.extend(
                    [
                        messages[-1],
                        Message(
                            role=Role.ASSISTANT,
                            content=draft.model_dump_json(),
                        ),
                    ]
                )
                return draft
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")


def _merge_skills(existing: Iterable[Skill], incoming: Iterable[Skill]) -> list[Skill]:
    merged: list[Skill] = []
    seen: set[str] = set()
    for skill in [*existing, *incoming]:
        if skill.topic in seen:
            continue
        merged.append(skill)
        seen.add(skill.topic)
    return merged
