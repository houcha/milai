"""Assessment state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.llm.client import LLMClient
from milai.llm.errors import LLMError
from milai.llm.prompts.assessment import (
    MAX_ASSESSMENT_QUESTIONS,
    MIN_ASSESSMENT_QUESTIONS,
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
        if self._should_stop_assessment(state, fluency):
            return self._to_review_state(state, fluency), updated_user

        follow_up_questions = await self._generate_questions(
            state,
            updated_user,
            follow_up_guidance=fluency.follow_up_guidance,
        )
        state.questions.extend(follow_up_questions)
        return state, updated_user

    def _should_stop_assessment(
        self, state: AssessmentState, fluency: FluencyResult
    ) -> bool:
        answered_count = len(state.questions)
        if answered_count >= MAX_ASSESSMENT_QUESTIONS:
            return True
        return (
            answered_count >= MIN_ASSESSMENT_QUESTIONS and fluency.confidence == "high"
        )

    def _to_review_state(
        self, state: AssessmentState, fluency: FluencyResult
    ) -> AssessmentReviewState:
        return AssessmentReviewState(
            fluency_level=fluency.fluency_level,
            fluency_rationale=fluency.rationale,
            assessment_questions=state.questions,
        )

    async def _generate_questions(
        self,
        state: AssessmentState,
        user: UserState,
        *,
        follow_up_guidance: str | None = None,
    ) -> list[AssessmentQuestion]:
        while True:
            try:
                batch = await self._llm.complete(
                    build_question_prompt(
                        state,
                        user,
                        follow_up_guidance=follow_up_guidance,
                    ),
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
