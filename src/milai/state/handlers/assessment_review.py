"""Assessment review state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.models.user_state import UserState
from milai.state.variants import (
    AppState,
    AssessmentReviewState,
    CurriculumGenerationState,
)


class AssessmentReviewHandler:
    def __init__(self, mediator: IOMediator) -> None:
        self._mediator = mediator

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[CurriculumGenerationState, UserState]:
        if not isinstance(app, AssessmentReviewState):
            raise TypeError(f"AssessmentReviewHandler cannot handle {app.type!r}")
        await self._mediator.clear()
        await self._mediator.show(
            RichContent("Fluency snapshot", kind=ContentKind.HEADER)
        )
        await self._mediator.show(
            RichContent(f"{app.fluency_level}: {app.fluency_rationale}")
        )

        if await self._mediator.confirm("Use this fluency level?"):
            fluency_level = app.fluency_level
        else:
            fluency_level = await self._prompt_override()

        updated = user.model_copy(deep=True)
        updated.profile = updated.profile.model_copy(
            update={"fluency_level": fluency_level}
        )
        return (
            CurriculumGenerationState(
                assessment_questions=app.assessment_questions,
            ),
            updated,
        )

    async def _prompt_override(self) -> str:
        while True:
            value = await self._mediator.prompt("Fluency level")
            if value:
                return value
            await self._mediator.show_error("Fluency level is required.")
