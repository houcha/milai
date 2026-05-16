"""Assessment state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.llm.client import LLMClient
from milai.llm.errors import LLMError
from milai.llm.prompts.assessment import (
    AssessmentQuestionBatch,
    FluencyResult,
    build_fluency_prompt,
    build_question_prompt,
)
from milai.models.assessment import AssessmentQuestion
from milai.models.user_state import UserState
from milai.state.variants import AppState, AssessmentReviewState, AssessmentState


class AssessmentHandler:
    def __init__(self, mediator: IOMediator, llm: LLMClient) -> None:
        self._mediator = mediator
        self._llm = llm

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[AssessmentState | AssessmentReviewState, UserState]:
        if not isinstance(app, AssessmentState):
            raise TypeError(f"AssessmentHandler cannot handle {app.type!r}")
        state = app.model_copy(deep=True)
        updated_user = user.model_copy(deep=True)

        if not state.questions:
            state.questions = await self._generate_questions(state, updated_user)
            return state, updated_user

        if state.current_idx < len(state.questions):
            await self._capture_next_answer(state)
            return state, updated_user

        fluency = await self._calculate_fluency(state, updated_user)
        return (
            AssessmentReviewState(
                fluency_level=fluency.fluency_level,
                fluency_rationale=fluency.rationale,
                assessment_questions=state.questions,
            ),
            updated_user,
        )

    async def _generate_questions(
        self, state: AssessmentState, user: UserState
    ) -> list[AssessmentQuestion]:
        while True:
            try:
                batch = await self._llm.complete(
                    build_question_prompt(state, user),
                    response_model=AssessmentQuestionBatch,
                )
                return batch.questions
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _capture_next_answer(self, state: AssessmentState) -> None:
        question = state.questions[state.current_idx]
        await self._mediator.show(
            RichContent(
                f"Question {state.current_idx + 1} of {len(state.questions)}",
                kind=ContentKind.PROGRESS,
                current=state.current_idx + 1,
                total=len(state.questions),
            )
        )
        question.user_answer = await self._mediator.prompt(question.text)
        state.current_idx += 1

    async def _calculate_fluency(
        self, state: AssessmentState, user: UserState
    ) -> FluencyResult:
        while True:
            try:
                return await self._llm.complete(
                    build_fluency_prompt(state, user),
                    response_model=FluencyResult,
                )
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")
