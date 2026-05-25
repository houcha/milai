"""Assessment state handler."""

import logging

from pydantic import BaseModel

from milai.agents.assessment import AssessmentInterviewer, AssessmentPhase
from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.llm.errors import LLMError
from milai.llm.types import Message, Role
from milai.models.assessment import AssessmentQuestion, Diagnosis, NextQuestion, Retry
from milai.models.user_state import UserState
from milai.state.variants import (
    AppState,
    AssessmentReviewState,
    AssessmentState,
)

MIN_USABLE_ASSESSMENT_EVIDENCE = 6
MAX_ASSESSMENT_QUESTIONS = 20
logger = logging.getLogger(__name__)


class AssessmentHandler:
    def __init__(
        self, mediator: IOMediator, interviewer: AssessmentInterviewer
    ) -> None:
        self._mediator = mediator
        self._interviewer = interviewer

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[AssessmentState | AssessmentReviewState, UserState]:
        if not isinstance(app, AssessmentState):
            raise TypeError(f"AssessmentHandler cannot handle {app.type!r}")
        state = app.model_copy(deep=True)
        updated_user = user.model_copy(deep=True)

        if state.questions and state.questions[-1].user_answer is None:
            await self._capture_latest_answer(state)
            return state, updated_user

        return await self._advance_assessment(state, updated_user), updated_user

    async def _advance_assessment(
        self, state: AssessmentState, user: UserState
    ) -> AssessmentState | AssessmentReviewState:
        while True:
            try:
                usable_evidence = sum(
                    question.user_answer is not None for question in state.questions
                )
                usable_evidence_needed = max(
                    MIN_USABLE_ASSESSMENT_EVIDENCE - usable_evidence, 0
                )
                question_budget_remaining = max(
                    MAX_ASSESSMENT_QUESTIONS - len(state.questions), 0
                )
                phase = self._assessment_phase(state, usable_evidence=usable_evidence)
                logger.info(
                    "Assessment is continuing in the %s phase. Evidence: %s/%s. "
                    "Questions asked: %s/%s.",
                    phase,
                    usable_evidence,
                    MIN_USABLE_ASSESSMENT_EVIDENCE,
                    len(state.questions),
                    MAX_ASSESSMENT_QUESTIONS,
                )

                result = await self._interviewer.next_action(
                    state,
                    user,
                    phase,
                    usable_evidence_needed=usable_evidence_needed,
                    question_budget_remaining=question_budget_remaining,
                )
                return await self._apply_continuation_result(
                    state,
                    result,
                )
            except LLMError as exc:
                if not await self._handle_llm_error(exc):
                    raise

    async def _apply_continuation_result(
        self,
        state: AssessmentState,
        action: NextQuestion | Retry | Diagnosis,
    ) -> AssessmentState | AssessmentReviewState:
        match action:
            case Diagnosis():
                self._record_interviewer_reply(state, action)
                logger.info(
                    "Assessment finished with %s fluency at %s confidence. "
                    "Evidence: %s/%s. Questions asked: %s.",
                    action.fluency_level,
                    action.confidence,
                    sum(
                        question.user_answer is not None for question in state.questions
                    ),
                    MIN_USABLE_ASSESSMENT_EVIDENCE,
                    len(state.questions),
                )
                return AssessmentReviewState(
                    fluency_level=action.fluency_level,
                    fluency_rationale=action.rationale,
                    assessment_questions=state.questions,
                    assessment_messages=state.assessment_messages,
                )

            case NextQuestion():
                self._record_interviewer_reply(state, action)
                state.questions.append(self._to_assessment_question(action))
                logger.info(
                    "Assessment asked question %s at %s difficulty.",
                    len(state.questions),
                    action.difficulty,
                )
                return state

            case Retry():
                self._record_interviewer_reply(state, action)
                await self._mediator.show(RichContent(action.message))
                state.questions.pop()
                state.questions.append(self._retry_to_assessment_question(action))
                logger.info(
                    "Assessment asked the learner to retry question %s at %s "
                    "difficulty. Reason: %s",
                    sum(
                        question.user_answer is not None for question in state.questions
                    )
                    + 1,
                    action.difficulty,
                    action.retry_reason,
                )
                return state

            case _:
                raise LLMError("assessment interviewer returned incomplete result")

    def _record_interviewer_reply(
        self, state: AssessmentState, result: BaseModel
    ) -> None:
        state.assessment_messages.append(
            Message(role=Role.ASSISTANT, content=result.model_dump_json())
        )

    def _assessment_phase(
        self, state: AssessmentState, *, usable_evidence: int
    ) -> AssessmentPhase:
        if not state.questions:
            return AssessmentPhase.INITIAL
        if len(state.questions) >= MAX_ASSESSMENT_QUESTIONS:
            return AssessmentPhase.FORCED_DIAGNOSIS
        if usable_evidence < MIN_USABLE_ASSESSMENT_EVIDENCE:
            return AssessmentPhase.COLLECTING
        return AssessmentPhase.DIAGNOSING

    def _to_assessment_question(self, action: NextQuestion) -> AssessmentQuestion:
        return AssessmentQuestion(
            text=action.text,
            difficulty=action.difficulty,
            rationale=action.rationale,
        )

    def _retry_to_assessment_question(self, action: Retry) -> AssessmentQuestion:
        return AssessmentQuestion(
            text=action.text,
            difficulty=action.difficulty,
            rationale=action.retry_reason,
        )

    async def _capture_latest_answer(self, state: AssessmentState) -> None:
        question = state.questions[-1]
        question_number = (
            sum(item.user_answer is not None for item in state.questions) + 1
        )
        await self._mediator.show(
            RichContent(
                f"Question {question_number}",
                kind=ContentKind.PROGRESS,
                current=question_number,
                total=0,
            )
        )
        question.user_answer = await self._mediator.prompt(question.text)
        logger.info(
            "Assessment captured an answer for question %s. Answer length: %s.",
            question_number,
            len(question.user_answer),
        )
        if (
            not state.assessment_messages
            or state.assessment_messages[-1].role is not Role.ASSISTANT
        ):
            state.assessment_messages.append(
                Message(role=Role.ASSISTANT, content=question.text)
            )
        state.assessment_messages.append(
            Message(role=Role.USER, content=question.user_answer)
        )

    async def _handle_llm_error(self, exc: LLMError) -> bool:
        await self._mediator.show_error(str(exc))
        return exc.retryable and await self._mediator.confirm("Try again?")
