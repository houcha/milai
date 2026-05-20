"""Curriculum and lesson domain models."""

from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt, field_validator


class Exercise(BaseModel):
    instruction: str
    exercise_type: Literal["translation", "fill_blank", "multiple_choice", "open"]
    options: list[str] | None = None
    user_answer: str | None = None
    feedback: str | None = None
    is_correct: bool | None = None
    skill_topics: list[str] = Field(default_factory=list)


class ExerciseEvaluation(BaseModel):
    feedback: str
    is_correct: bool | None = None
    skill_topics: list[str] = Field(default_factory=list)

    @field_validator("skill_topics")
    @classmethod
    def normalize_topics(cls, value: list[str]) -> list[str]:
        return [
            normalized
            for topic in value
            if (normalized := " ".join(topic.strip().lower().split()))
        ]


class Lesson(BaseModel):
    title: str
    theory: str = ""
    current_exercise_idx: NonNegativeInt = 0
    exercises: list[Exercise] = Field(default_factory=list)


class Module(BaseModel):
    title: str
    current_lesson_idx: NonNegativeInt = 0
    lessons: list[Lesson] = Field(min_length=1)


class Curriculum(BaseModel):
    current_module_idx: NonNegativeInt = 0
    modules: list[Module] = Field(min_length=1)
