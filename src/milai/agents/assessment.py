"""Concrete adaptive assessment agent."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field, RootModel

from milai.llm.client import LLMClient
from milai.llm.prompts.assets import render_prompt_template
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
        content=render_prompt_template(
            "assessment/system.txt.j2",
            {
                "target_language": profile.target_language,
                "native_language": profile.native_language,
                "learning_goal": profile.learning_goal,
                "preferences": profile.preferences,
            },
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
        content=render_prompt_template(
            "assessment/step_instructions.txt.j2",
            {
                "instructions": instructions,
                "usable_evidence_needed": usable_evidence_needed,
                "question_budget_remaining": question_budget_remaining,
            },
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
                return await self._llm.complete(
                    messages,
                    response_model=NextQuestion,
                )
            case AssessmentPhase.COLLECTING:
                collecting = await self._llm.complete(
                    messages,
                    response_model=_CollectingAction,
                )
                return collecting.root
            case AssessmentPhase.DIAGNOSING:
                diagnosing = await self._llm.complete(
                    messages,
                    response_model=_AfterMinimumAction,
                )
                return diagnosing.root
            case AssessmentPhase.FORCED_DIAGNOSIS:
                return await self._llm.complete(
                    messages,
                    response_model=Diagnosis,
                )
