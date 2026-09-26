"""Final exercise submissions and failed assessment rollback."""

import asyncio
from types import SimpleNamespace

import pytest

from milai.store import Store
from milai.tools import Context
from milai.tutor import LessonTurnOutput
from tests.test_lesson_conversations import _seed_lesson, _tutor


def test_unassessed_answer_rolls_back_and_incorrect_submission_is_final(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "tutor.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "lesson", "pronouns", "Subject pronouns")
    task = store.lesson_detail(store.owner, session, lesson["id"])["exercises"][0]
    calls = []

    async def run(agent, messages, *, context, **kwargs):
        calls.append(context)
        return SimpleNamespace(
            final_output=LessonTurnOutput(
                reply="A clarification", summary="Discussed an answer"
            ),
            to_input_list=lambda: messages,
        )

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    with pytest.raises(ValueError, match="could not be assessed"):
        asyncio.run(
            tutor.respond(
                store.owner,
                session,
                "An answer",
                lesson_id=lesson["id"],
                exercise_id=task["id"],
                action="answer",
            )
        )
    assert not store.exercise_status(store.owner, session, task["id"])["submitted"]
    scope = store.learning_scope(store.owner, session)
    ctx = Context(store, scope, session, "assessed", "Wrong answer", "test")
    with store.transaction():
        store.assess_attempt(
            ctx,
            task["id"],
            "Incorrect",
            [
                {
                    "skill_id": lesson["focus_skill_id"],
                    "outcome": "needs_work",
                    "issue_severity": "substantial",
                    "rationale": "Wrong answer",
                }
            ],
        )
        store.save_turn(ctx, "Incorrect", [])
    with pytest.raises(ValueError, match="already been submitted"):
        asyncio.run(
            tutor.respond(
                store.owner,
                session,
                "A correction",
                lesson_id=lesson["id"],
                exercise_id=task["id"],
                action="answer",
            )
        )
    assert len(calls) == 1  # Rejected before another model request.
    asyncio.run(tutor.close())
    store.close()
