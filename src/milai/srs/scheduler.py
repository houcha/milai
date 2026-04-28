"""Small topic-level spaced repetition scheduler."""

from datetime import UTC, datetime
from math import log2

from milai.models.user_state import Skill


def update_skill(
    skill: Skill,
    *,
    success: bool,
    now: datetime | None = None,
) -> Skill:
    timestamp = now or datetime.now(UTC)
    if success:
        return skill.model_copy(
            update={
                "strength": min(1.0, round(skill.strength + 0.1, 4)),
                "streak": skill.streak + 1,
                "interval_days": min(90.0, skill.interval_days * 2.0),
                "total_encounters": skill.total_encounters + 1,
                "last_seen": timestamp,
            }
        )
    return skill.model_copy(
        update={
            "strength": max(0.0, round(skill.strength - 0.2, 4)),
            "streak": 0,
            "interval_days": 1.0,
            "total_encounters": skill.total_encounters + 1,
            "last_seen": timestamp,
        }
    )


def due_skills(skills: list[Skill], *, now: datetime | None = None) -> list[Skill]:
    timestamp = now or datetime.now(UTC)
    return [
        skill
        for skill in skills
        if (timestamp - skill.last_seen).days >= skill.interval_days
    ]


def _priority(skill: Skill, now: datetime) -> float:
    days_since_seen = max(0, (now - skill.last_seen).days)
    return (1.0 - skill.strength) * log2(days_since_seen + 1)


def top_review_skills(
    skills: list[Skill],
    *,
    limit: int = 3,
    now: datetime | None = None,
) -> list[Skill]:
    timestamp = now or datetime.now(UTC)
    due = due_skills(skills, now=timestamp)
    return sorted(due, key=lambda skill: _priority(skill, timestamp), reverse=True)[
        :limit
    ]
