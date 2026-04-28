from datetime import UTC, datetime, timedelta


def _skill(**overrides):
    from milai.models.user_state import Skill

    values = {
        "topic": "articles",
        "strength": 0.5,
        "last_seen": datetime(2026, 4, 20, tzinfo=UTC),
        "streak": 1,
        "interval_days": 2.0,
        "total_encounters": 3,
    }
    values.update(overrides)
    return Skill(**values)


def test_update_skill_success_increases_strength_streak_interval_and_encounters() -> (
    None
):
    from milai.srs.scheduler import update_skill

    now = datetime(2026, 4, 28, tzinfo=UTC)
    updated = update_skill(
        _skill(strength=0.95, interval_days=80.0), success=True, now=now
    )

    assert updated.strength == 1.0
    assert updated.streak == 2
    assert updated.interval_days == 90.0
    assert updated.total_encounters == 4
    assert updated.last_seen == now


def test_update_skill_failure_decreases_strength_and_resets_interval() -> None:
    from milai.srs.scheduler import update_skill

    now = datetime(2026, 4, 28, tzinfo=UTC)
    updated = update_skill(_skill(strength=0.1), success=False, now=now)

    assert updated.strength == 0.0
    assert updated.streak == 0
    assert updated.interval_days == 1.0
    assert updated.total_encounters == 4
    assert updated.last_seen == now


def test_due_skills_and_top_review_skills_rank_weak_overdue_topics() -> None:
    from milai.srs.scheduler import due_skills, top_review_skills

    now = datetime(2026, 4, 28, tzinfo=UTC)
    weak_overdue = _skill(
        topic="articles", strength=0.1, last_seen=now - timedelta(days=8)
    )
    strong_overdue = _skill(
        topic="greetings", strength=0.9, last_seen=now - timedelta(days=8)
    )
    not_due = _skill(
        topic="future tense", strength=0.2, interval_days=10, last_seen=now
    )

    due = due_skills([not_due, strong_overdue, weak_overdue], now=now)
    ranked = top_review_skills(
        [not_due, strong_overdue, weak_overdue], limit=2, now=now
    )

    assert due == [strong_overdue, weak_overdue]
    assert [skill.topic for skill in ranked] == ["articles", "greetings"]
