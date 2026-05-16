"""Assessment domain models."""

from typing import Literal

from pydantic import BaseModel


class AssessmentQuestion(BaseModel):
    text: str
    user_answer: str | None = None
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
