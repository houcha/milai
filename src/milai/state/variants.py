"""Pydantic app-state variants for the workflow machine."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, NonNegativeInt

from milai.llm.types import Message
from milai.models.assessment import AssessmentQuestion


class OnboardingState(BaseModel):
    type: Literal["onboarding"] = "onboarding"


class AssessmentState(BaseModel):
    type: Literal["assessment"] = "assessment"
    questions: list[AssessmentQuestion] = Field(default_factory=list)
    current_idx: NonNegativeInt = 0


class AssessmentReviewState(BaseModel):
    type: Literal["assessment_review"] = "assessment_review"
    fluency_level: str
    fluency_rationale: str = ""
    assessment_questions: list[AssessmentQuestion] = Field(default_factory=list)


class CurriculumGenerationState(BaseModel):
    type: Literal["curriculum_gen"] = "curriculum_gen"
    assessment_questions: list[AssessmentQuestion] = Field(default_factory=list)


class CurriculumReviewState(BaseModel):
    type: Literal["curriculum_review"] = "curriculum_review"


class LessonState(BaseModel):
    type: Literal["lesson"] = "lesson"


class DeviationState(BaseModel):
    type: Literal["deviation"] = "deviation"
    context_window: list[Message] = Field(default_factory=list)
    lesson_context: str = ""


class LessonCompleteState(BaseModel):
    type: Literal["lesson_complete"] = "lesson_complete"


class CurriculumCompleteState(BaseModel):
    type: Literal["curriculum_complete"] = "curriculum_complete"


AppState = Annotated[
    OnboardingState
    | AssessmentState
    | AssessmentReviewState
    | CurriculumGenerationState
    | CurriculumReviewState
    | LessonState
    | DeviationState
    | LessonCompleteState
    | CurriculumCompleteState,
    Field(discriminator="type"),
]
