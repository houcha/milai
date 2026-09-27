"""Per-blank assessment contracts, persistence, and legacy upgrades."""

import asyncio
import json
from copy import deepcopy

import pytest

from milai.store import SCHEMA_VERSION, InvalidReference, Store
from milai.tools import Context, assess_attempt
from tests.test_learning import invoke
from tests.test_lesson_conversations import _seed_lesson
from tests.test_lesson_results import assess


@pytest.fixture
def inline_attempt(tmp_path):
    store = Store(tmp_path / "blanks.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "forms", "Present-tense forms")
    task = store.lesson_detail(store.owner, session, lesson["id"])["exercises"][0]
    store.db.execute(
        "UPDATE exercises SET task=? WHERE id=?",
        ("Fill in haben.\n\n1. ich {{blank}}\n2. ihr {{blank}}", task["id"]),
    )
    ctx = Context(
        store,
        store.learning_scope(store.owner, session),
        session,
        "answer",
        "Blank 1: habe\nBlank 2: haben",
        "test",
        lesson_id=lesson["id"],
        selected_exercise_id=task["id"],
        action="answer",
    )
    assessment = {
        "exercise_id": task["id"],
        "feedback": "",
        "score": {"correct": 1, "total": 2},
        "blank_results": [
            {"blank_number": 1, "correct": True, "feedback": ""},
            {
                "blank_number": 2,
                "correct": False,
                "feedback": "Use **habt** with ihr, meaning ‘you (plural) have.’",
            },
        ],
        "observations": [
            {
                "skill_id": lesson["focus_skill_id"],
                "outcome": "success",
                "issue_severity": "minor",
                "rationale": "One local conjugation slip.",
            }
        ],
    }
    yield store, ctx, assessment
    store.close()


@pytest.mark.parametrize("all_correct", [False, True])
def test_blank_assessment_tool_persists_results_and_isolates_sessions(
    inline_attempt, all_correct
):
    store, ctx, assessment = inline_attempt
    if all_correct:
        ctx.message = "Blank 1: habe\nBlank 2: habt"
        assessment["score"]["correct"] = 2
        assessment["blank_results"][1].update(correct=True, feedback="")
        assessment["observations"][0]["issue_severity"] = "none"
    with store.transaction():
        result = asyncio.run(invoke(assess_attempt, ctx, {"assessment": assessment}))
        assert "error" not in result
        assert ctx.assessments[0]["blank_results"] == assessment["blank_results"]
        store.save_turn(ctx, "Saved", [])
    with store.read_snapshot() as reopened:
        saved = reopened.exercise_status(
            reopened.owner, ctx.session, assessment["exercise_id"]
        )
        assert saved["first_assessment"]["blank_results"] == assessment["blank_results"]
        assert saved["first_assessment"]["feedback"] == ""
        assert saved["first_assessment"]["learner_response"] == ctx.message
        assert saved["submitted"]
        assert saved["correct"] is all_correct
        # Skill evidence stays independent of per-blank accuracy.
        assert saved["first_assessment"]["observations"][0]["independent_success"]
    other_session = store.session(store.owner)
    with pytest.raises(InvalidReference):
        store.exercise_status(store.owner, other_session, assessment["exercise_id"])


@pytest.mark.parametrize(
    "invalid",
    [
        "missing",
        "duplicate",
        "reordered",
        "out_of_range",
        "not_boolean",
        "correct_feedback",
        "missing_correction",
        "long_correction",
        "wrong_total",
        "wrong_correct",
        "overall_feedback",
        "no_markers",
    ],
)
def test_invalid_blank_results_cannot_consume_submission(inline_attempt, invalid):
    store, ctx, original = inline_attempt
    assessment = deepcopy(original)
    results = assessment["blank_results"]
    if invalid == "missing":
        results.pop()
    elif invalid == "duplicate":
        results[1]["blank_number"] = 1
    elif invalid == "reordered":
        results.reverse()
    elif invalid == "out_of_range":
        results[1]["blank_number"] = 3
    elif invalid == "not_boolean":
        results[0]["correct"] = "true"
    elif invalid == "correct_feedback":
        results[0]["feedback"] = "Correct!"
    elif invalid == "missing_correction":
        results[1]["feedback"] = " "
    elif invalid == "long_correction":
        results[1]["feedback"] = "x" * 601
    elif invalid == "wrong_total":
        assessment["score"]["total"] = 3
    elif invalid == "wrong_correct":
        assessment["score"]["correct"] = 2
    elif invalid == "overall_feedback":
        assessment["feedback"] = "The first fill is correct."
    elif invalid == "no_markers":
        store.db.execute(
            "UPDATE exercises SET task='Write a sentence.' WHERE id=?",
            (assessment["exercise_id"],),
        )
    # Validation must happen before writes, even without a wrapping transaction.
    with pytest.raises(ValueError):
        store.assess_attempt(ctx, **assessment)
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    assert (
        store.db.execute("SELECT count(*) FROM skill_observations").fetchone()[0] == 0
    )
    assert not store.exercise_status(
        store.owner, ctx.session, assessment["exercise_id"]
    )["submitted"]


def test_missing_blank_results_return_recoverable_tool_guidance(inline_attempt):
    store, ctx, assessment = inline_attempt
    assessment["blank_results"] = []
    result = asyncio.run(invoke(assess_attempt, ctx, {"assessment": assessment}))
    error = json.loads(result)
    assert error["error"] == "invalid_operation"
    assert "blank_results" in error["guidance"]
    assert not ctx.assessments
    assert not store.exercise_status(
        store.owner, ctx.session, assessment["exercise_id"]
    )["submitted"]


def test_schema_seven_upgrade_preserves_scores_and_leaves_old_blanks_ungraded(tmp_path):
    path = tmp_path / "legacy.db"
    store = Store(path)
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "forms", "Present-tense forms")
    task = store.lesson_detail(store.owner, session, lesson["id"])["exercises"][0]
    assess(store, session, lesson, task, "answer", {"correct": 1, "total": 2})
    store.db.execute(
        "UPDATE exercises SET task='1. {{blank}}\n2. {{blank}}' WHERE id=?",
        (task["id"],),
    )
    before = store.exercise_status(store.owner, session, task["id"])
    store.db.execute("ALTER TABLE attempts DROP COLUMN blank_results")
    store.db.execute("UPDATE metadata SET value='7' WHERE key='schema_version'")
    store.close()
    upgraded = Store(path)
    assert upgraded.exercise_status(upgraded.owner, session, task["id"]) == before
    assert before["first_assessment"]["blank_results"] is None
    assert (
        upgraded.db.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()[0]
        == SCHEMA_VERSION
    )
    upgraded.close()
