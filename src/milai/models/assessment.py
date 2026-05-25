"""Assessment domain models."""

from typing import Literal

from pydantic import BaseModel, Field


class NextQuestion(BaseModel):
    action: Literal["next_question"]
    text: str = Field(description="One concise assessment question for the learner.")
    difficulty: Literal["beginner", "intermediate", "advanced"] = Field(
        description="Approximate difficulty of the assessment question.",
    )
    rationale: str = Field(
        description="Why this question is useful now and what ability it probes.",
    )


class AssessmentQuestion(BaseModel):
    text: str
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    rationale: str = ""
    user_answer: str | None = None


class Retry(BaseModel):
    action: Literal["retry"]
    retry_reason: str = Field(description="Why the latest answer is unusable.")
    message: str = Field(
        description="Short user-facing explanation of why another answer is needed."
    )
    text: str = Field(description="Replacement question to retry.")
    difficulty: Literal["beginner", "intermediate", "advanced"] = Field(
        default="beginner",
        description="Approximate difficulty of the replacement question.",
    )


class Diagnosis(BaseModel):
    action: Literal["diagnosis"]
    fluency_level: str = Field(description="Estimated current fluency level.")
    rationale: str = Field(description="Concise diagnosis rationale from evidence.")
    confidence: Literal["low", "medium", "high"] = Field(
        description="Confidence in the diagnosis."
    )
    evidence_summary: str = Field(description="Brief summary of evidence used.")
