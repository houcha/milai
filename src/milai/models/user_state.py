"""User profile and learning state models."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, field_validator

from milai.models.curriculum import Curriculum


class UserProfile(BaseModel):
    target_language: str | None = None
    native_language: str | None = None
    learning_goal: str | None = None
    minutes_per_day: int | None = Field(default=None, ge=1)
    fluency_level: str | None = None
    preferences: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class Skill(BaseModel):
    topic: str
    strength: float = Field(default=0.0, ge=0.0, le=1.0)
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    streak: NonNegativeInt = 0
    interval_days: float = Field(default=1.0, ge=0.0, le=90.0)
    total_encounters: NonNegativeInt = 0

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        normalized = " ".join(value.strip().lower().split())
        if not normalized:
            msg = "topic must not be empty"
            raise ValueError(msg)
        return normalized


class UserState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: UserProfile = Field(default_factory=UserProfile)
    skills: list[Skill] = Field(default_factory=list)
    curriculum: Curriculum | None = None

    @field_validator("skills")
    @classmethod
    def require_unique_skill_topics(cls, value: list[Skill]) -> list[Skill]:
        topics = [skill.topic for skill in value]
        if len(set(topics)) != len(topics):
            msg = "skill topics must be unique"
            raise ValueError(msg)
        return value


PreferenceValue = str | int | float | bool | None
PreferenceMap = dict[str, PreferenceValue]
JsonObject = dict[str, Any]
