"""Assessment review state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.models.session import LearningSession
from milai.state.variants import (
    AssessmentReviewState,
    CurriculumGenerationState,
)


class AssessmentReviewHandler:
    def __init__(self, mediator: IOMediator) -> None:
        self._mediator = mediator

    async def step(self, session: LearningSession) -> LearningSession:
        app = session.app
        user = session.user
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
            fluency_rationale: str | None = app.fluency_rationale
        else:
            fluency_level = await self._prompt_override()
            fluency_rationale = None

        updated = user.model_copy(deep=True)
        updated.profile = updated.profile.model_copy(
            update={
                "fluency_level": fluency_level,
                "fluency_rationale": fluency_rationale,
            }
        )
        return session.model_copy(
            update={
                "app": CurriculumGenerationState(
                    assessment_questions=app.assessment_questions,
                    assessment_messages=app.assessment_messages,
                ),
                "user": updated,
            }
        )

    async def _prompt_override(self) -> str:
        while True:
            value = await self._mediator.prompt("Fluency level")
            if value:
                return value
            await self._mediator.show_error("Fluency level is required.")
