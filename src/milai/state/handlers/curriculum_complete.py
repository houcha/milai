"""Curriculum completion state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import Choice, ContentKind, RichContent
from milai.llm.client import LLMClient
from milai.llm.errors import LLMError
from milai.llm.prompts.curriculum import CurriculumDraft, build_extension_prompt
from milai.models.user_state import UserState
from milai.state.handlers.curriculum_gen import _merge_skills
from milai.state.variants import (
    AppState,
    CurriculumCompleteState,
    LessonState,
    OnboardingState,
)

CURRICULUM_EXTENSION_TIMEOUT_SECONDS = 180


class CurriculumCompleteHandler:
    def __init__(self, mediator: IOMediator, llm: LLMClient) -> None:
        self._mediator = mediator
        self._llm = llm

    async def step(
        self, app: AppState, user: UserState
    ) -> (
        tuple[LessonState | OnboardingState | CurriculumCompleteState, UserState] | None
    ):
        if not isinstance(app, CurriculumCompleteState):
            raise TypeError(f"CurriculumCompleteHandler cannot handle {app.type!r}")

        await self._mediator.show(
            RichContent("Curriculum complete", kind=ContentKind.HEADER)
        )
        choice = await self._mediator.choose(
            "Next step",
            [
                Choice("Extend", "extend", "Generate more lessons"),
                Choice("Start new", "start_new", "Replace this local session"),
                Choice("Finish", "finish", "Keep the completed session"),
            ],
        )
        if choice.value == "finish":
            return None
        if choice.value == "start_new":
            return OnboardingState(), UserState()

        if user.curriculum is None:
            await self._mediator.show_error("No completed curriculum is available.")
            return None

        draft = await self._extend(app, user)
        updated = user.model_copy(deep=True)
        if updated.curriculum is None:
            raise RuntimeError("user has no curriculum")
        start_index = len(updated.curriculum.modules)
        updated.curriculum.modules.extend(draft.curriculum.modules)
        updated.curriculum.current_module_idx = start_index
        updated.curriculum.modules[start_index].current_lesson_idx = 0
        updated.skills = _merge_skills(updated.skills, draft.initial_skills)
        return LessonState(), updated

    async def _extend(
        self, state: CurriculumCompleteState, user: UserState
    ) -> CurriculumDraft:
        while True:
            try:
                return await self._llm.complete(
                    build_extension_prompt(state, user, completed_skills=user.skills),
                    response_model=CurriculumDraft,
                    timeout=CURRICULUM_EXTENSION_TIMEOUT_SECONDS,
                )
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")
