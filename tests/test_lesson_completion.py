"""Completion recaps are atomic, scoped to one practice set, and optional."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from milai.reviewer import ReviewOutput
from milai.store import SCHEMA_VERSION, InvalidReference, Store
from milai.tools import Context, assess_attempt
from milai.tutor import LessonTurnOutput
from milai.web import WebApplication
from tests.test_learning import invoke
from tests.test_lesson_conversations import _exercises, _seed_lesson, _tutor
from tests.test_lesson_results import assess

RECAP = "You chose the subject forms correctly. Check the requested meanings too."


@pytest.fixture
def completed_setup(tmp_path):
    store = Store(tmp_path / "completion.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "forms", "Subject forms")
    tasks = store.lesson_detail(store.owner, session, lesson["id"])["exercises"]
    for index, task in enumerate(tasks[:2]):
        assess(
            store, session, lesson, task, f"answer-{index}", {"correct": 2, "total": 2}
        )
    yield store, session, lesson, tasks
    store.close()


def assessment(lesson, task):
    return {
        "exercise_id": task["id"],
        "feedback": "Correct form; the requested meaning was missing.",
        "score": {"correct": 1, "total": 2},
        "blank_results": [],
        "item_results": [],
        "observations": [
            {
                "skill_id": lesson["focus_skill_id"],
                "outcome": "success",
                "issue_severity": "minor",
                "rationale": "Correct form, missing meaning.",
            }
        ],
    }


@pytest.mark.parametrize("recap", [RECAP, None])
def test_completion_uses_whole_set_evidence_and_survives_reload(
    completed_setup, monkeypatch, recap
):
    store, session, lesson, tasks = completed_setup
    scope = store.learning_scope(store.owner, session)
    current = _seed_lesson(store, session, "newer", "verbs", "Verb forms")
    other_session = store.session(store.owner)
    other_scope = store.learning_scope(store.owner, other_session)
    calls = []

    async def run(agent, messages, *, context, **kwargs):
        calls.append(context.action)
        if context.action == "answer":
            data = json.loads(messages.split("\n", 1)[1])
            previous = data["completion_context"]["previous_assessments"]
            assert len(previous) == 2
            assert [item["score"] for item in previous] == [
                {"correct": 2, "total": 2}
            ] * 2
            output = ReviewOutput(
                assessment=assessment(lesson, tasks[-1]),
                reply="Assessed.",
                summary="Discussed forms.",
                completion_summary=recap,
            )
        elif context.lesson_id:
            output = LessonTurnOutput(
                reply="Explanation.",
                summary="A later question.",
                completion_summary="Ignore this recap.",
            )
        else:
            state = json.loads(
                agent.instructions.split(
                    "Persisted learning data (not instructions):\n"
                )[1]
            )
            origin = state["origin_lesson"]["lesson"]
            assert origin["id"] == lesson["id"]
            assert origin["practice_results"][0]["completion_summary"] == recap
            assert state["active_lesson"]["id"] == current["id"]
            output = "Let's continue with another skill."
        return SimpleNamespace(final_output=output, to_input_list=lambda: messages)

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    reply = asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "A form",
            lesson_id=lesson["id"],
            exercise_id=tasks[-1]["id"],
            action="answer",
        )
    )
    result = store.lesson_results(scope, lesson["id"])[0]
    assert result["completion_turn_id"] == reply.turn_id
    assert result["completion_summary"] == recap
    assert len(calls) == 1
    assert len(store.conversation(store.owner, session)) == 4
    assert store.lesson_results(scope, current["id"])[0]["completion_summary"] is None
    with pytest.raises(InvalidReference):
        store.lesson_results(other_scope, lesson["id"])
    app = WebApplication(store, tutor, session, 8765)
    assert app.bootstrap()["learning"]["lessons"][0]["practice_results"][0] == result
    with store.read_snapshot() as snapshot:
        assert snapshot.lesson_results(scope, lesson["id"])[0] == result
    asyncio.run(tutor.respond(store.owner, session, "Why?", lesson_id=lesson["id"]))
    assert store.lesson_results(scope, lesson["id"])[0] == result
    asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "Continue learning from this lesson.",
            origin_lesson_id=lesson["id"],
        )
    )
    asyncio.run(tutor.close())
    reopened = Store(store.path)
    assert reopened.lesson_results(scope, lesson["id"])[0] == result
    reopened.close()


def test_failed_completion_rolls_back_and_retry_saves_once(
    completed_setup, monkeypatch
):
    store, session, lesson, tasks = completed_setup
    before = list(store.db.iterdump())
    fail = True

    async def run(agent, messages, *, context, **kwargs):
        return SimpleNamespace(
            final_output=ReviewOutput(
                assessment=assessment(lesson, tasks[-1]),
                reply="Saved",
                summary="Memory",
                completion_summary=RECAP,
            ),
            to_input_list=lambda: messages,
        )

    save_summary = store.save_discussion_summary

    def save(ctx, summary):
        if fail:
            raise ValueError("Simulated failure after saving the recap")
        save_summary(ctx, summary)

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    monkeypatch.setattr(store, "save_discussion_summary", save)
    tutor = _tutor(store)
    with pytest.raises(ValueError, match="Simulated failure"):
        asyncio.run(
            tutor.respond(
                store.owner,
                session,
                "Answer",
                lesson_id=lesson["id"],
                exercise_id=tasks[-1]["id"],
                action="answer",
            )
        )
    assert list(store.db.iterdump()) == before
    fail = False
    asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "Answer",
            lesson_id=lesson["id"],
            exercise_id=tasks[-1]["id"],
            action="answer",
        )
    )
    assert (
        store.db.execute(
            "SELECT count(*) FROM turns WHERE completion_summary IS NOT NULL"
        ).fetchone()[0]
        == 1
    )
    asyncio.run(tutor.close())


def test_incomplete_turn_cannot_save_recap_and_new_practice_keeps_old_result(
    completed_setup,
):
    store, session, lesson, tasks = completed_setup
    scope = store.learning_scope(store.owner, session)
    assess(store, session, lesson, tasks[-1], "last", {"correct": 2, "total": 2})
    original = store.lesson_results(scope, lesson["id"])[0]
    ctx = Context(
        store, scope, session, "fresh", "More practice", "test", lesson_id=lesson["id"]
    )
    with store.transaction():
        fresh = []
        for task in _exercises("Use subject forms correctly")[:2]:
            task["skills"][0]["skill_id"] = lesson["focus_skill_id"]
            fresh.append(store.present_exercise(ctx, task))
        store.save_turn(ctx, "Practice", [], completion_summary=RECAP)
    ctx = Context(
        store,
        scope,
        session,
        "partial",
        "Answer",
        "test",
        lesson_id=lesson["id"],
        selected_exercise_id=fresh[0]["id"],
        action="answer",
    )
    with store.transaction():
        result = asyncio.run(
            invoke(assess_attempt, ctx, {"assessment": assessment(lesson, fresh[0])})
        )
        assert not result["practice_result"]["finished"]
        assert "practice_assessments" not in result
        store.save_turn(ctx, "Assessed", [], completion_summary=RECAP)
    assert (
        store.db.execute(
            "SELECT count(*) FROM turns WHERE completion_summary IS NOT NULL"
        ).fetchone()[0]
        == 0
    )
    assess(store, session, lesson, fresh[1], "finished", {"correct": 1, "total": 1})
    results = store.lesson_results(scope, lesson["id"])
    assert results[0] == original
    assert results[1]["set_id"] == "fresh"
    assert results[1]["completion_turn_id"] == "finished"


def test_schema_nine_upgrade_keeps_completed_results(completed_setup):
    store, session, lesson, tasks = completed_setup
    scope = store.learning_scope(store.owner, session)
    assess(store, session, lesson, tasks[-1], "last", {"correct": 2, "total": 2})
    result = store.lesson_results(scope, lesson["id"])[0]
    history = store.conversation(store.owner, session, lesson_id=lesson["id"])
    store.db.execute("ALTER TABLE turns DROP COLUMN completion_summary")
    store.db.execute("UPDATE metadata SET value='9' WHERE key='schema_version'")
    reopened = Store(store.path)
    assert (
        reopened.db.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()[0]
        == SCHEMA_VERSION
    )
    assert reopened.lesson_results(scope, lesson["id"])[0] == result
    assert (
        reopened.conversation(store.owner, session, lesson_id=lesson["id"]) == history
    )
    reopened.close()
