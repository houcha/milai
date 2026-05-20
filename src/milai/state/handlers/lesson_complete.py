"""Lesson completion state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.models.user_state import UserState
from milai.state.variants import (
    AppState,
    CurriculumCompleteState,
    LessonCompleteState,
    LessonState,
)


class LessonCompleteHandler:
    def __init__(self, mediator: IOMediator) -> None:
        self._mediator = mediator

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[LessonState | CurriculumCompleteState, UserState] | None:
        if not isinstance(app, LessonCompleteState):
            raise TypeError(f"LessonCompleteHandler cannot handle {app.type!r}")
        if user.curriculum is None:
            await self._mediator.show_error("No curriculum is available.")
            return None

        updated = user.model_copy(deep=True)
        curriculum = updated.curriculum
        if curriculum is None:
            raise RuntimeError("user has no curriculum")
        module = curriculum.modules[curriculum.current_module_idx]
        lesson = module.lessons[module.current_lesson_idx]
        await self._mediator.show(
            RichContent(f"Completed: {lesson.title}", kind=ContentKind.HEADER)
        )

        if module.current_lesson_idx + 1 < len(module.lessons):
            module.current_lesson_idx += 1
            return LessonState(), updated

        if curriculum.current_module_idx + 1 < len(curriculum.modules):
            curriculum.current_module_idx += 1
            next_module = curriculum.modules[curriculum.current_module_idx]
            next_module.current_lesson_idx = 0
            return LessonState(), updated

        return CurriculumCompleteState(), updated
