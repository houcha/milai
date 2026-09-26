"""Persisted lesson discussions and explicit exercise selection."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import InvalidReference, Store
from milai.tools import Context
from milai.tutor import LessonTurnOutput, Tutor


def _document(label: str) -> dict:
    return {
        "objective": f"Use {label} in a short exchange.",
        "sections": [
            {
                "id": "meaning",
                "title": "Meaning",
                "markdown": f"**{label}** changes the sentence meaning.",
            }
        ],
        "worked_examples": [
            {"id": "worked", "title": "Worked example", "markdown": "**ich** bin hier."}
        ],
        "recap": f"Choose {label} by its role in the sentence.",
    }


def _exercises(criterion: str) -> list[dict]:
    return [
        {
            "title": f"Apply the skill {number}",
            "task": f"Write a short answer for item {number}.",
            "context": "At a café",
            "scaffolding": "none",
            "skills": [
                {
                    "skill_id": "@focus",
                    "role": "target",
                    "success_criterion": criterion,
                }
            ],
            "source_ids": [],
        }
        for number in range(3)
    ]


def _seed_lesson(store: Store, session: str, turn_id: str, key: str, name: str) -> dict:
    scope = store.learning_scope(store.owner, session)
    ctx = Context(store, scope, session, turn_id, "Teach me German", "test")
    criterion = f"Use {name.lower()} correctly"
    with store.transaction():
        if "target_language" not in store.profile(scope):
            store.record_facts(
                ctx,
                [
                    {
                        "field": "target_language",
                        "value": "German",
                        "learner_quote": "German",
                    }
                ],
            )
        lesson = store.start_lesson(
            ctx,
            "German",
            None,
            {
                "key": key,
                "name": name,
                "definition": f"Use {name.lower()}",
                "success_criteria": [criterion],
            },
            [],
            "Requested lesson",
            document=_document(name),
            exercises=_exercises(criterion),
        )
        ctx.lesson_ids.append(lesson["id"])
        store.save_turn(ctx, "Open lesson", [])
    return lesson


def _tutor(store: Store) -> Tutor:
    return Tutor(
        Settings("https://model.invalid", "chat", "test"),
        store,
        Telemetry(enabled=False),
        model="interactive-test-model",
        generation_model="generation-test-model",
    )


@pytest.mark.parametrize("reference", [None, "section", "worked", "exercise"])
def test_selected_text_is_saved_replayed_and_keeps_the_complete_lesson(
    tmp_path, monkeypatch, reference
):
    path = tmp_path / "selection.db"
    store = Store(path)
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "first", "pronouns", "Subject pronouns")
    detail = store.lesson_detail(store.owner, session, lesson["id"])
    options: dict[str, Any] = {"lesson_id": lesson["id"]}
    if reference in {"section", "worked"}:
        options["section_id"] = "meaning" if reference == "section" else "worked"
    elif reference == "exercise":
        options["exercise_id"] = detail["exercises"][0]["id"]
    quote = "ich — 主語 😀"
    calls = []

    async def run(agent, messages, *, context, **kwargs):
        calls.append((agent, messages, context))
        current_detail = store.lesson_detail(store.owner, session, lesson["id"])
        assert json.dumps(current_detail, ensure_ascii=False) in agent.instructions
        return SimpleNamespace(
            final_output=LessonTurnOutput(
                reply="Explanation", summary="Discussed a quote."
            ),
            to_input_list=lambda: messages,
        )

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    asyncio.run(
        tutor.respond(store.owner, session, "Why?", selected_text=quote, **options)
    )
    assert quote in calls[0][1][-1]["content"]
    assert calls[0][2].selected_text == quote
    assert (
        store.conversation(store.owner, session, lesson_id=lesson["id"])[0]["content"]
        == "Why?"
    )
    asyncio.run(
        tutor.respond(store.owner, session, "What else?", lesson_id=lesson["id"])
    )
    assert quote in calls[1][1][0]["content"]
    assert calls[1][1][-1]["content"] == "What else?"
    assert calls[1][2].selected_text is None
    assert calls[1][2].section_id is None
    assert calls[1][2].selected_exercise_id is None
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM assistance").fetchone()[0] == 0
    asyncio.run(tutor.close())
    store.close()

    reopened = Store(path)
    local = reopened.conversation(reopened.owner, session, lesson_id=lesson["id"])
    assert local[0]["selected_text"] == quote
    assert local[2]["selected_text"] is None
    assert all(
        not entry.get("selected_text")
        for entry in reopened.conversation(reopened.owner, session)
    )
    scope = reopened.learning_scope(reopened.owner, session)
    excerpt = reopened.discussion_excerpt(scope, lesson["id"])
    assert excerpt["turns"][0]["selected_text"] == quote
    history = reopened.model_history(reopened.owner, session, lesson_id=lesson["id"])
    assert quote in history[0]["content"]
    bounded = reopened.model_history(
        reopened.owner, session, lesson_id=lesson["id"], max_chars=30
    )
    assert sum(len(entry["content"]) for entry in bounded) <= 30
    other = reopened.session(reopened.owner)
    with pytest.raises(InvalidReference):
        reopened.conversation(reopened.owner, other, lesson_id=lesson["id"])
    reopened.close()


def test_invalid_selected_text_is_rejected_before_model_execution(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "invalid-selection.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "first", "pronouns", "Subject pronouns")
    other = store.session(store.owner)
    other_lesson = _seed_lesson(store, other, "other", "verbs", "Verbs")
    foreign_exercise = store.lesson_detail(store.owner, other, other_lesson["id"])[
        "exercises"
    ][0]["id"]

    async def run(*args, **kwargs):
        pytest.fail("Invalid selections must be rejected before model execution")

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    for selected_text in ["", "  ", "x" * 4001, 42]:
        with pytest.raises(ValueError):
            asyncio.run(
                tutor.respond(
                    store.owner,
                    session,
                    "Why?",
                    lesson_id=lesson["id"],
                    selected_text=cast(Any, selected_text),
                )
            )
    cases: list[dict[str, Any]] = [
        {},
        {"lesson_id": lesson["id"], "action": "answer", "exercise_id": "anything"},
        {"lesson_id": lesson["id"], "section_id": "missing"},
        {"lesson_id": lesson["id"], "exercise_id": foreign_exercise},
        {"lesson_id": other_lesson["id"]},
    ]
    for references in cases:
        with pytest.raises(ValueError):
            asyncio.run(
                tutor.respond(
                    store.owner, session, "Why?", selected_text="quote", **references
                )
            )
    assert store.conversation(store.owner, session, lesson_id=lesson["id"]) == []
    asyncio.run(tutor.close())
    store.close()


def test_failed_selected_question_saves_neither_quote_nor_summary(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "failed-selection.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "first", "pronouns", "Subject pronouns")

    async def run(*args, **kwargs):
        raise RuntimeError("Model failed")

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    with pytest.raises(RuntimeError, match="Model failed"):
        asyncio.run(
            tutor.respond(
                store.owner,
                session,
                "Why?",
                lesson_id=lesson["id"],
                selected_text="quote",
            )
        )
    assert store.conversation(store.owner, session, lesson_id=lesson["id"]) == []
    assert (
        store.discussion_summary(
            store.learning_scope(store.owner, session), lesson["id"]
        )
        is None
    )
    asyncio.run(tutor.close())
    store.close()


def test_lesson_scope_summary_and_current_focus_survive_reopen(tmp_path, monkeypatch):
    path = Path(tmp_path) / "state.db"
    store = Store(path)
    session = store.session(store.owner)
    old = _seed_lesson(store, session, "first", "pronouns", "Subject pronouns")
    current = _seed_lesson(store, session, "second", "verbs", "Verb forms")
    calls = []

    async def run(agent, messages, *, context, **kwargs):
        calls.append((agent, messages, context))
        return SimpleNamespace(
            final_output=LessonTurnOutput(
                reply="Use **ich** when you are the subject.",
                summary="Asked how to choose ich; next, try a short answer.",
            ),
            to_input_list=lambda: messages,
        )

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    reply = asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "Why ich?",
            lesson_id=old["id"],
            section_id="meaning",
        )
    )
    assert reply.text.startswith("Use **ich**")
    focus = store.active_lesson(store.learning_scope(store.owner, session))
    assert focus is not None and focus["id"] == current["id"]
    assert len(store.conversation(store.owner, session)) == 4
    local = store.conversation(store.owner, session, lesson_id=old["id"])
    assert len(local) == 2
    assert local[0]["section_id"] == "meaning"
    assert local[0]["action"] == "message"
    assert len(calls[0][1]) == 1  # Main-chat turns are absent from lesson replay.
    assert "Complete lesson document" in calls[0][0].instructions
    summary = store.discussion_summary(
        store.learning_scope(store.owner, session), old["id"]
    )
    assert summary is not None and summary["updating_turn_id"] == reply.turn_id
    excerpt = store.lesson_excerpt(
        store.learning_scope(store.owner, session), old["id"], length=25
    )
    assert len(excerpt["text"]) == 25 and excerpt["has_more"]
    discussion = store.discussion_excerpt(
        store.learning_scope(store.owner, session), old["id"], max_chars=180
    )
    assert (
        len(json.dumps(discussion["turns"], ensure_ascii=False, separators=(",", ":")))
        <= 180
    )
    assert (
        store.discussion_excerpt(
            store.learning_scope(store.owner, session), old["id"], max_chars=10
        )["turns"]
        == []
    )
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM assistance").fetchone()[0] == 0
    asyncio.run(tutor.close())
    store.close()

    reopened = Store(path)
    detail = reopened.lesson_detail(reopened.owner, session, old["id"])
    assert detail["sections"][0]["id"] == "meaning"
    assert detail["discussion_summary"]["summary"].startswith("Asked how")
    reopened_focus = reopened.active_lesson(
        reopened.learning_scope(reopened.owner, session)
    )
    assert reopened_focus is not None and reopened_focus["id"] == current["id"]
    reopened.close()


def test_references_are_rejected_before_model_and_completed_task_can_be_discussed(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "refs.db")
    first = store.session(store.owner)
    second = store.session(store.owner)
    lesson = _seed_lesson(store, first, "first", "pronouns", "Subject pronouns")
    scope = store.learning_scope(store.owner, first)
    exercise = store.lesson_detail(store.owner, first, lesson["id"])["exercises"][0]

    async def run(agent, messages, *, context, **kwargs):
        return SimpleNamespace(
            final_output=LessonTurnOutput(
                reply="It is a subject form.", summary="Explained the completed task."
            ),
            to_input_list=lambda: messages,
        )

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    with pytest.raises(InvalidReference):
        asyncio.run(tutor.respond(store.owner, second, "Why?", lesson_id=lesson["id"]))
    with pytest.raises(ValueError, match="Section"):
        asyncio.run(
            tutor.respond(
                store.owner, first, "Why?", lesson_id=lesson["id"], section_id="missing"
            )
        )
    with store.transaction():
        answer_ctx = Context(store, scope, first, "answer", "ich", "test")
        store.assess_attempt(
            answer_ctx,
            exercise["id"],
            "Correct",
            [
                {
                    "skill_id": lesson["focus_skill_id"],
                    "outcome": "success",
                    "issue_severity": "none",
                    "rationale": "Correct subject form",
                }
            ],
        )
        store.save_turn(answer_ctx, "Correct", [])
    assert store.exercise_status(store.owner, first, exercise["id"])["completed"]
    assert (
        store.exercise_status(store.owner, first, exercise["id"])["latest_assessment"][
            "turn_id"
        ]
        == "answer"
    )
    reply = asyncio.run(
        tutor.respond(
            store.owner,
            first,
            "Why was ich correct?",
            lesson_id=lesson["id"],
            exercise_id=exercise["id"],
            action="message",
        )
    )
    assert reply.text.startswith("It is")
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
    with pytest.raises(ValueError, match="already been submitted"):
        asyncio.run(
            tutor.respond(
                store.owner,
                first,
                "ich",
                lesson_id=lesson["id"],
                exercise_id=exercise["id"],
                action="answer",
            )
        )
    asyncio.run(tutor.close())
    store.close()


def test_failed_summary_rolls_back_lesson_turn(tmp_path, monkeypatch):
    store = Store(tmp_path / "rollback.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "first", "pronouns", "Subject pronouns")

    async def run(agent, messages, *, context, **kwargs):
        return SimpleNamespace(
            final_output="Malformed structured output",
            to_input_list=lambda: messages,
        )

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    with pytest.raises(RuntimeError, match="incomplete"):
        asyncio.run(tutor.respond(store.owner, session, "Why?", lesson_id=lesson["id"]))
    assert store.conversation(store.owner, session, lesson_id=lesson["id"]) == []
    assert (
        store.discussion_summary(
            store.learning_scope(store.owner, session), lesson["id"]
        )
        is None
    )
    asyncio.run(tutor.close())
    store.close()


def test_assessing_older_lesson_recommends_review_without_changing_focus(tmp_path):
    store = Store(tmp_path / "older.db")
    session = store.session(store.owner)
    old = _seed_lesson(store, session, "first", "pronouns", "Subject pronouns")
    current = _seed_lesson(store, session, "second", "verbs", "Verb forms")
    scope = store.learning_scope(store.owner, session)
    prepared = store.lesson_detail(store.owner, session, old["id"])["exercises"]
    for number, task in enumerate(prepared[:2]):
        ctx = Context(
            store,
            scope,
            session,
            f"attempt-{number}",
            "wrong form",
            "test",
            lesson_id=old["id"],
            selected_exercise_id=task["id"],
            action="answer",
        )
        with store.transaction():
            assessment = store.assess_attempt(
                ctx,
                task["id"],
                "Try choosing the subject form again.",
                [
                    {
                        "skill_id": old["focus_skill_id"],
                        "outcome": "needs_work",
                        "issue_severity": "substantial",
                        "rationale": "Used an object form for a subject",
                    }
                ],
            )
            store.save_turn(ctx, "Try again", [])
    assert assessment["lesson_id"] == old["id"]
    assert not assessment["focus_mastered"]
    assert assessment["review_recommendations"] == [
        {
            "skill_id": old["focus_skill_id"],
            "name": "Subject pronouns",
            "reason": "repeated_difficulty",
        }
    ]
    focus = store.active_lesson(scope)
    assert focus is not None and focus["id"] == current["id"]
    assert len(store.lessons(scope)) == 2
    store.close()


def test_minor_slip_keeps_prepared_exercises_but_defers_new_drill(tmp_path):
    store = Store(tmp_path / "minor.db")
    session = store.session(store.owner)
    lesson = _seed_lesson(store, session, "first", "pronouns", "Subject pronouns")
    scope = store.learning_scope(store.owner, session)
    prepared = store.lesson_detail(store.owner, session, lesson["id"])["exercises"]
    answer = Context(
        store,
        scope,
        session,
        "minor-answer",
        "ich, with a typo elsewhere",
        "test",
        lesson_id=lesson["id"],
        selected_exercise_id=prepared[0]["id"],
        action="answer",
    )
    with store.transaction():
        store.assess_attempt(
            answer,
            prepared[0]["id"],
            "Mostly correct; fix the typo.",
            [
                {
                    "skill_id": lesson["focus_skill_id"],
                    "outcome": "success",
                    "issue_severity": "minor",
                    "rationale": "Subject pronoun chosen correctly",
                }
            ],
        )
        store.save_turn(answer, "Mostly correct", [])
    assert not store.exercise_status(store.owner, session, prepared[1]["id"])[
        "completed"
    ]
    assert (
        len(store.lesson_detail(store.owner, session, lesson["id"])["exercises"]) == 3
    )
    extra = _exercises("Use subject pronouns correctly")[0]
    extra["skills"][0]["skill_id"] = lesson["focus_skill_id"]
    with pytest.raises(ValueError, match="minor error"), store.transaction():
        store.present_exercise(
            Context(store, scope, session, "extra", "More practice", "test"),
            extra,
        )
    store.close()


def test_main_chat_help_uses_selected_exercise_and_its_actual_skill(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "main-help.db")
    session = store.session(store.owner)
    older = _seed_lesson(store, session, "older", "pronouns", "Subject pronouns")
    newer = _seed_lesson(store, session, "newer", "verbs", "Verb forms")
    exercise = store.lesson_detail(store.owner, session, older["id"])["exercises"][0]

    async def run(agent, messages, *, context, **kwargs):
        assert context.lesson_id is None
        assert context.selected_exercise_id == exercise["id"]
        assert '"selected_exercise"' in agent.instructions
        with pytest.raises(InvalidReference, match="belong to the exercise"):
            store.record_assistance(
                context,
                exercise["id"],
                [newer["focus_skill_id"]],
                "explanation",
                "Wrong skill",
            )
        store.record_assistance(
            context,
            exercise["id"],
            [older["focus_skill_id"]],
            "explanation",
            "Look at who acts in the sentence.",
        )
        return SimpleNamespace(
            final_output="Look at who acts in the sentence.",
            to_input_list=lambda: messages,
        )

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "Can I have a hint for this exercise?",
            exercise_id=exercise["id"],
        )
    )
    row = store.db.execute(
        "SELECT a.exercise_id, x.skill_id FROM assistance a "
        "JOIN assistance_skills x ON x.assistance_id=a.id"
    ).fetchone()
    assert tuple(row) == (exercise["id"], older["focus_skill_id"])
    assert store.conversation(store.owner, session)[-2]["exercise_id"] == exercise["id"]
    assert store.conversation(store.owner, session, lesson_id=older["id"]) == []
    asyncio.run(tutor.close())
    store.close()
