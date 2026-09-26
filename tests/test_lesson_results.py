"""Final submissions, first-attempt accuracy, and separate review practice sets."""

from datetime import datetime, timedelta

import pytest

from milai.store import Store
from milai.tools import Context
from tests.test_lesson_conversations import _exercises, _seed_lesson


def assess(
    store, session, lesson, task, turn, score, outcome="success", severity="none"
):
    scope = store.learning_scope(store.owner, session)
    ctx = Context(
        store,
        scope,
        session,
        turn,
        "An answer",
        "test",
        lesson_id=lesson["id"],
        selected_exercise_id=task["id"],
        action="answer",
    )
    with store.transaction():
        assessment = store.assess_attempt(
            ctx,
            task["id"],
            "Feedback",
            [
                {
                    "skill_id": lesson["focus_skill_id"],
                    "outcome": outcome,
                    "issue_severity": severity,
                    "rationale": "Observed answer",
                }
            ],
            score=score,
        )
        store.save_turn(ctx, "Feedback", [])
    return assessment


def test_accuracy_waits_for_all_answers_and_preserves_separate_practice_sets(tmp_path):
    path = tmp_path / "results.db"
    store = Store(path)
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "pronouns", "Subject pronouns")
    scope = store.learning_scope(store.owner, session)
    tasks = store.lesson_detail(store.owner, session, lesson["id"])["exercises"]
    assess(store, session, lesson, tasks[0], "one", {"correct": 4, "total": 4})
    assess(
        store,
        session,
        lesson,
        tasks[1],
        "two",
        {"correct": 1, "total": 2},
        severity="minor",
    )
    result = store.lesson(scope, lesson["id"])["practice_results"][0]
    assert result["submitted"] == 2 and not result["finished"]
    assert result["percentage"] is None
    assert result["review_at"] is None
    status = store.exercise_status(store.owner, session, tasks[1]["id"])
    assert status["submitted"] and status["completed"] and not status["correct"]
    # A minor slip can still be evidence of understanding while losing accuracy credit.
    assert status["first_assessment"]["observations"][0]["independent_success"]
    with pytest.raises(ValueError, match="already been submitted"):
        assess(store, session, lesson, tasks[1], "retry", {"correct": 2, "total": 2})
    assess(
        store,
        session,
        lesson,
        tasks[2],
        "three",
        {"correct": 1, "total": 2},
        "needs_work",
        "substantial",
    )
    original = store.lesson(scope, lesson["id"])["practice_results"][0]
    assert original["finished"]
    assert (original["correct"], original["total"], original["percentage"]) == (
        6,
        8,
        75,
    )
    assert original["scoring"] == "parts"
    assert datetime.fromisoformat(original["review_at"]) - datetime.fromisoformat(
        original["last_submitted_at"]
    ) == timedelta(days=1)
    assert not store.mastered(scope, lesson["focus_skill_id"])
    # Explicit fresh practice is allowed before the advisory review time.
    ctx = Context(
        store,
        scope,
        session,
        "fresh",
        "More exercises please",
        "test",
        lesson_id=lesson["id"],
    )
    new_task = _exercises("Use the subject form")[0]
    new_task["skills"][0]["skill_id"] = lesson["focus_skill_id"]
    with store.transaction():
        fresh = store.present_exercise(ctx, new_task)
        store.save_turn(ctx, "Fresh practice", [])
    rounds = store.lesson(scope, lesson["id"])["practice_results"]
    assert rounds[0] == original
    assert rounds[1]["number"] == 2 and rounds[1]["percentage"] is None
    assess(store, session, lesson, fresh, "review", {"correct": 2, "total": 2})
    store.close()
    reopened = Store(path)
    rounds = reopened.lesson(scope, lesson["id"])["practice_results"]
    assert [result["percentage"] for result in rounds] == [75, 100]
    assert rounds[0] == original
    reopened.close()


@pytest.mark.parametrize(
    "score",
    [
        {"correct": 3, "total": 2},
        {"correct": 0, "total": 0},
        {"correct": True, "total": 2},
        {"correct": -1, "total": 2},
    ],
)
def test_invalid_scores_do_not_consume_submission(tmp_path, score):
    store = Store(tmp_path / "invalid.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "pronouns", "Subject pronouns")
    task = store.lesson_detail(store.owner, session, lesson["id"])["exercises"][0]
    with pytest.raises(ValueError, match="Score"):
        assess(store, session, lesson, task, "bad", score)
    assert not store.exercise_status(store.owner, session, task["id"])["submitted"]
    assess(store, session, lesson, task, "valid", {"correct": 1, "total": 2})
    store.close()


def test_schema_six_upgrade_preserves_legacy_first_result(tmp_path):
    path = tmp_path / "legacy.db"
    store = Store(path)
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "pronouns", "Subject pronouns")
    scope = store.learning_scope(store.owner, session)
    tasks = store.lesson_detail(store.owner, session, lesson["id"])["exercises"]
    for index, task in enumerate(tasks):
        assess(
            store,
            session,
            lesson,
            task,
            f"answer-{index}",
            None,
            "success" if index else "needs_work",
            "none" if index else "substantial",
        )
    # Preserve an old correction without letting it replace the original score.
    store.db.execute(
        "INSERT INTO attempts SELECT 'legacy-retry', learner, exercise_id, "
        "'legacy-turn', 'Correction', feedback, created, score "
        "FROM attempts WHERE exercise_id=?",
        (tasks[0]["id"],),
    )
    store.db.execute(
        "INSERT INTO skill_observations SELECT 'legacy-observation', learner, "
        "'legacy-retry', ?, skill_id, 'success', rationale, 0, 'none', created "
        "FROM skill_observations WHERE exercise_id=?",
        (tasks[0]["id"], tasks[1]["id"]),
    )
    store.save_turn(
        Context(store, scope, session, "legacy-turn", "Correction", "test"),
        "Correct",
        [],
    )
    store.db.execute("ALTER TABLE attempts DROP COLUMN score")
    store.db.execute("UPDATE metadata SET value='6' WHERE key='schema_version'")
    store.close()
    upgraded = Store(path)
    result = upgraded.lesson(scope, lesson["id"])["practice_results"][0]
    assert result["scoring"] == "exercises"
    assert (result["correct"], result["total"], result["percentage"]) == (2, 3, 66)
    assert upgraded.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 4
    assert upgraded.exercise_status(upgraded.owner, session, tasks[0]["id"])[
        "submitted"
    ]
    upgraded.close()


def test_legacy_missing_assessment_has_no_invented_accuracy(tmp_path):
    store = Store(tmp_path / "unassessed.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "pronouns", "Subject pronouns")
    scope = store.learning_scope(store.owner, session)
    tasks = store.lesson_detail(store.owner, session, lesson["id"])["exercises"]
    for number, task in enumerate(tasks):
        store.save_turn(
            Context(
                store,
                scope,
                session,
                f"answer-{number}",
                "An answer",
                "test",
                lesson_id=lesson["id"],
                selected_exercise_id=task["id"],
                action="answer",
            ),
            "Please clarify",
            [],
        )
    result = store.lesson(scope, lesson["id"])["practice_results"][0]
    assert result["finished"]
    assert result["percentage"] is None
    assert result["assessed"] == 0
    assert all(
        store.exercise_status(store.owner, session, task["id"])["submitted"]
        for task in tasks
    )
    store.close()
