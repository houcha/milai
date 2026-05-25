"""Concrete adaptive assessment agent."""

import json
import logging
from dataclasses import asdict
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, RootModel

from milai.llm.client import LLMClient
from milai.llm.errors import LLMParseError
from milai.llm.types import Message, Role
from milai.models.assessment import Diagnosis, NextQuestion, Retry
from milai.models.user_state import UserState
from milai.state.variants import AssessmentState


class AssessmentPhase(StrEnum):
    INITIAL = "initial"
    COLLECTING = "collecting"
    DIAGNOSING = "diagnosing"
    FORCED_DIAGNOSIS = "forced_diagnosis"


class _CollectingAction(
    RootModel[Annotated[NextQuestion | Retry, Field(discriminator="action")]]
):
    pass


class _AfterMinimumAction(
    RootModel[
        Annotated[NextQuestion | Retry | Diagnosis, Field(discriminator="action")]
    ]
):
    pass


logger = logging.getLogger(__name__)

_PHASE_INSTRUCTIONS = {
    AssessmentPhase.INITIAL: "Ask the first assessment question.",
    AssessmentPhase.COLLECTING: (
        "Evaluate the latest learner answer from history. If it is blank, "
        "off-topic, refusal-only, or impossible to assess, retry with clearer "
        "wording. Otherwise record the evidence and ask a follow-up question."
    ),
    AssessmentPhase.DIAGNOSING: (
        "Evaluate the latest learner answer from history. If it is unusable, "
        "retry with clearer wording. If the evidence supports placement, "
        "provide a diagnosis. Otherwise ask a follow-up question to reduce the "
        "main uncertainty."
    ),
    AssessmentPhase.FORCED_DIAGNOSIS: (
        "Provide the best-supported diagnosis from the available evidence."
    ),
}


def build_assessment_system_prompt(user: UserState) -> Message:
    profile = user.profile
    return Message(
        role=Role.SYSTEM,
        content=(
            "You are a language assessment interviewer. Estimate the learner's "
            f"current ability in {profile.target_language}; their native language "
            f"is {profile.native_language}. Treat the assessment history as the "
            "evidence record. Prefer practical language tasks aligned with the "
            f"learning goal: {profile.learning_goal}. Teaching preferences: "
            f"{profile.preferences}. Keep the exchange focused on assessment, "
            "not teaching or correction."
        ),
    )


def build_assessment_step_instructions(
    *,
    instructions: str,
    usable_evidence_needed: int,
    question_budget_remaining: int,
) -> Message:
    return Message(
        role=Role.USER,
        content=(
            f"Additional usable answers targeted by policy: {usable_evidence_needed}. "
            "Question budget remaining for new questions: "
            f"{question_budget_remaining}. "
            f"{instructions}"
        ),
    )


class AssessmentInterviewer:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def next_action(
        self,
        state: AssessmentState,
        user: UserState,
        phase: AssessmentPhase,
        *,
        usable_evidence_needed: int,
        question_budget_remaining: int,
    ) -> NextQuestion | Retry | Diagnosis:
        messages = [
            build_assessment_system_prompt(user),
            *state.assessment_messages,
            build_assessment_step_instructions(
                instructions=_PHASE_INSTRUCTIONS[phase],
                usable_evidence_needed=usable_evidence_needed,
                question_budget_remaining=question_budget_remaining,
            ),
        ]

        match phase:
            case AssessmentPhase.INITIAL:
                return await self._complete_assessment_action(
                    messages, phase=phase, response_model=NextQuestion
                )
            case AssessmentPhase.COLLECTING:
                collecting = await self._complete_assessment_action(
                    messages, phase=phase, response_model=_CollectingAction
                )
                return collecting.root
            case AssessmentPhase.DIAGNOSING:
                diagnosing = await self._complete_assessment_action(
                    messages, phase=phase, response_model=_AfterMinimumAction
                )
                return diagnosing.root
            case AssessmentPhase.FORCED_DIAGNOSIS:
                return await self._complete_assessment_action(
                    messages, phase=phase, response_model=Diagnosis
                )

    async def _complete_assessment_action[T: BaseModel](
        self,
        messages: list[Message],
        *,
        phase: AssessmentPhase,
        response_model: type[T],
    ) -> T:
        try:
            return await self._llm.complete(messages, response_model=response_model)
        except LLMParseError as exc:
            logger.error(
                "Assessment LLM response could not be parsed as %s.\n"
                "Phase: %s\n"
                "Messages sent: %s\n"
                "Content:\n"
                "%s\n"
                "Validation error:\n"
                "%s\n"
                "Raw response:\n"
                "%s",
                response_model.__name__,
                phase,
                len(messages),
                json.dumps(
                    {"messages": [asdict(message) for message in messages]},
                    indent=4,
                ),
                str(exc),
                json.dumps(json.loads(exc.raw_response), indent=4),
            )
            raise
