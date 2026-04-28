"""Assessment domain models."""

from typing import Literal

from pydantic import BaseModel, Field


class AssessmentQuestion(BaseModel):
    text: str
    expected_topics: list[str] = Field(default_factory=list)
    user_answer: str | None = None
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
