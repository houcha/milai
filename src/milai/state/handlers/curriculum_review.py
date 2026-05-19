"""Curriculum review state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import Choice, ContentKind, RichContent
from milai.llm.client import LLMClient
from milai.llm.errors import LLMError
from milai.llm.prompts.curriculum import CurriculumDraft, build_adjustment_prompt
from milai.models.curriculum import Curriculum
from milai.models.user_state import UserState
from milai.state.handlers.curriculum_gen import _merge_skills
from milai.state.variants import AppState, CurriculumReviewState, LessonState


class CurriculumReviewHandler:
    def __init__(self, mediator: IOMediator, llm: LLMClient) -> None:
        self._mediator = mediator
        self._llm = llm

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[CurriculumReviewState | LessonState, UserState] | None:
        if not isinstance(app, CurriculumReviewState):
            raise TypeError(f"CurriculumReviewHandler cannot handle {app.type!r}")
        if user.curriculum is None:
            await self._mediator.show_error("No curriculum draft is available.")
            return None

        await self._show_curriculum(user.curriculum)
        choice = await self._mediator.choose(
            "Review curriculum",
            [
                Choice("Confirm", "confirm", "Start lessons with this curriculum"),
                Choice("Revise", "feedback", "Describe any changes you want"),
            ],
        )

        updated = user.model_copy(deep=True)
        if choice.value == "confirm":
            return LessonState(), updated

        feedback = await self._mediator.prompt("Curriculum feedback")
        draft = await self._adjust_draft(app, updated, feedback=feedback)
        updated.curriculum = draft.curriculum
        updated.skills = _merge_skills(updated.skills, draft.initial_skills)
        return CurriculumReviewState(), updated

    async def _show_curriculum(self, curriculum: Curriculum) -> None:
        await self._mediator.clear()
        await self._mediator.show(RichContent("Curriculum", kind=ContentKind.HEADER))
        for index, module in enumerate(curriculum.modules, start=1):
            lines = [f"{index}. {module.title}"]
            if module.description:
                lines.append(f"   Goal: {module.description}")
                lines.append("")
            if module.lessons:
                lines.extend(
                    f"   {index}.{lesson_index} {lesson.title}"
                    for lesson_index, lesson in enumerate(module.lessons, start=1)
                )
            else:
                lines.append("   No lessons")
            await self._mediator.show(RichContent("\n".join(lines)))

    async def _adjust_draft(
        self,
        state: CurriculumReviewState,
        user: UserState,
        *,
        feedback: str,
    ) -> CurriculumDraft:
        while True:
            try:
                return await self._llm.complete(
                    build_adjustment_prompt(state, user, feedback=feedback),
                    response_model=CurriculumDraft,
                )
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")
