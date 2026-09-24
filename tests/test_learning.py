"""Lesson focus, prerequisite gating, mastery, and tutor persistence."""

import asyncio
import json
import sqlite3

import pytest
from agents.testing import ModelStep, ScriptedModel, assistant_message
from agents.tool_context import ToolContext

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import SCHEMA_VERSION, InvalidReference, SchemaMismatch, Store
from milai.tools import Context, record_learner_facts, start_lesson
from milai.tutor import Tutor


def context(store, learner, session, turn="seed", message="seed"):
    return Context(store, learner, session, turn, message, "test-prompt")


def skill_spec(key="subject-pronouns", name="Subject pronouns"):
    return {
        "key": key,
        "name": name,
        "definition": f"Use German {name.lower()} in a sentence.",
        "success_criteria": [f"Choose the correct {name.lower()} for a subject."],
    }


def seed_graph(store, learner, session):
    ctx = context(store, learner, session)
    with store.transaction():
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
            ctx, "German", None, skill_spec(), [], "Start with pronouns"
        )
    return {"lesson": lesson}


def exercise(
    store, learner, session, skill_id, turn, scaffolding="none", supporting=None
):
    ctx = context(store, learner, session, turn, "Practice")
    with store.transaction():
        result = store.present_exercise(
            ctx,
            {
                "title": "Pronouns",
                "task": "Choose the subject pronoun.",
                "context": "A simple sentence",
                "scaffolding": scaffolding,
                "source_ids": [],
                "skills": [
                    {
                        "skill_id": skill_id,
                        "role": "target",
                        "success_criterion": "Choose correctly",
                    },
                    *[
                        {
                            "skill_id": item,
                            "role": "supporting",
                            "success_criterion": "Use earlier skill",
                        }
                        for item in (supporting or [])
                    ],
                ],
            },
        )
        store.save_turn(ctx, "Try this", [])
    return result


def observe(
    store,
    learner,
    session,
    exercise_id,
    skill_id,
    turn,
    outcome="success",
    helped=False,
):
    ctx = context(store, learner, session, turn, "Answer")
    with store.transaction():
        if helped:
            store.record_assistance(ctx, exercise_id, [skill_id], "explanation", "Help")
        result = store.assess_attempt(
            ctx,
            exercise_id,
            "Feedback",
            [
                {
                    "skill_id": skill_id,
                    "outcome": outcome,
                    "rationale": "Observed answer",
                }
            ],
        )
        store.save_turn(ctx, "Feedback", [])
    return result


async def invoke(tool, ctx, arguments):
    raw = json.dumps(arguments)
    return await tool.on_invoke_tool(
        ToolContext(ctx, tool_name=tool.name, tool_call_id="test", tool_arguments=raw),
        raw,
    )


def test_schema_mismatch_requires_explicit_archiving_reset(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE records(id TEXT PRIMARY KEY)")
    db.close()
    with pytest.raises(SchemaMismatch, match="milai reset --yes"):
        Store(path)
    archived = Store.reset(path)
    assert len(archived) == 1 and archived[0].exists()
    store = Store(path)
    assert (
        store.db.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()[0]
        == SCHEMA_VERSION
    )
    assert {
        row[0]
        for row in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    } >= {"lessons", "skills"}
    store.close()


def test_one_skill_per_lesson_and_prerequisites_gate_progression(tmp_path):
    store = Store(tmp_path / "lesson.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    first = seed_graph(store, scope, session)["lesson"]
    first_id = first["focus_skill_id"]
    assert first["title"] == "German · Subject pronouns"
    with pytest.raises(ValueError, match="already the active lesson"):
        store.start_lesson(
            context(store, scope, session, "repeat"),
            "German",
            first_id,
            None,
            [],
            "Same focus",
        )
    with pytest.raises(ValueError, match="master"), store.transaction():
        store.start_lesson(
            context(store, scope, session, "blocked"),
            "German",
            None,
            skill_spec("verb-agreement", "Verb agreement"),
            [first_id],
            "Next",
        )
    assert len(store.lessons(scope)) == 1
    assert len(store.search_skills(scope, "German", "", 20)) == 1
    for number in range(2):
        task = exercise(store, scope, session, first_id, f"task-{number}")
        observe(store, scope, session, task["id"], first_id, f"answer-{number}")
    assert store.mastered(scope, first_id)
    with store.transaction():
        next_lesson = store.start_lesson(
            context(store, scope, session, "next"),
            "German",
            None,
            skill_spec("verb-agreement", "Verb agreement"),
            [first_id],
            "Build sentences",
        )
    assert next_lesson["focus_skill_id"] != first_id
    assert store.prerequisites(scope, next_lesson["focus_skill_id"]) == [first_id]
    with pytest.raises(ValueError, match="exactly one target"), store.transaction():
        store.present_exercise(
            context(store, scope, session, "wrong"),
            {
                "title": "Wrong",
                "task": "Wrong target",
                "context": "",
                "scaffolding": "none",
                "source_ids": [],
                "skills": [
                    {
                        "skill_id": first_id,
                        "role": "target",
                        "success_criterion": "Use pronouns",
                    }
                ],
            },
        )
    task = exercise(
        store,
        scope,
        session,
        next_lesson["focus_skill_id"],
        "complex",
        supporting=[first_id],
    )
    assert [item["role"] for item in task["skills"]] == ["target", "supporting"]
    assert store.db.execute("PRAGMA foreign_key_check").fetchall() == []
    store.close()


def test_mastery_requires_distinct_unassisted_exercises_since_last_difficulty(tmp_path):
    store = Store(tmp_path / "mastery.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    skill_id = seed_graph(store, scope, session)["lesson"]["focus_skill_id"]
    task = exercise(store, scope, session, skill_id, "one")
    observe(store, scope, session, task["id"], skill_id, "one-a")
    observe(store, scope, session, task["id"], skill_id, "one-b")
    assert not store.mastered(scope, skill_id)
    task = exercise(store, scope, session, skill_id, "two", scaffolding="cues")
    observe(store, scope, session, task["id"], skill_id, "two-a")
    assert not store.mastered(scope, skill_id)
    task = exercise(store, scope, session, skill_id, "three")
    observe(store, scope, session, task["id"], skill_id, "three-a", helped=True)
    assert not store.mastered(scope, skill_id)
    task = exercise(store, scope, session, skill_id, "four")
    observe(store, scope, session, task["id"], skill_id, "four-a")
    assert store.mastered(scope, skill_id)
    task = exercise(store, scope, session, skill_id, "five")
    observe(store, scope, session, task["id"], skill_id, "five-a", outcome="needs_work")
    assert not store.mastered(scope, skill_id)
    for number in (6, 7):
        task = exercise(store, scope, session, skill_id, f"task-{number}")
        observe(store, scope, session, task["id"], skill_id, f"answer-{number}")
    assert store.mastered(scope, skill_id)
    with store.transaction():
        store.start_lesson(
            context(store, scope, session, "other"),
            "German",
            None,
            skill_spec("verb-forms", "Verb forms"),
            [],
            "A different skill",
        )
    with store.transaction():
        review = store.start_lesson(
            context(store, scope, session, "review"),
            "German",
            skill_id,
            None,
            [],
            "Requested review",
        )
    assert review["review"] and review["title"].startswith("Review: German ·")
    assert len(store.lessons(scope)) == 3
    store.close()


def test_start_lesson_tool_uses_private_one_skill_plan(tmp_path, monkeypatch):
    store = Store(tmp_path / "planner.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    missing = context(store, scope, session, message="Start German")
    assert (
        json.loads(
            asyncio.run(
                invoke(start_lesson, missing, {"lesson": {"intent": "Pronouns"}})
            )
        )["error"]
        == "invalid_operation"
    )
    plan = {
        "existing_skill_key": None,
        "new_skill": skill_spec(),
        "prerequisite_keys": [],
        "reason": "Begin with subject pronouns",
    }
    from types import SimpleNamespace

    from milai.tools import _LessonPlan

    requests = []

    async def planned(agent, planner_input, **kwargs):
        requests.append(planner_input)
        return SimpleNamespace(final_output=_LessonPlan.model_validate(plan))

    monkeypatch.setattr("milai.tools.Runner.run", planned)
    ctx = context(store, scope, session, message="German from scratch")
    ctx.model = "test-model"
    ctx.planner_instructions = "Choose one skill"
    with store.transaction():
        asyncio.run(
            invoke(
                record_learner_facts,
                ctx,
                {
                    "facts": [
                        {
                            "field": "target_language",
                            "value": "German",
                            "learner_quote": "German",
                        }
                    ]
                },
            )
        )
        result = asyncio.run(
            invoke(start_lesson, ctx, {"lesson": {"intent": "Begin learning"}})
        )
    assert result["title"] == "German · Subject pronouns"
    assert len(store.lessons(scope)) == 1
    assert len(requests) == 1
    assert "reusable_active_skills" in requests[0]
    store.close()


def test_tutor_streams_reply_before_committing_turn(tmp_path):
    store = Store(tmp_path / "stream.db")
    session = store.session(store.owner)
    events = []

    async def progress(event):
        events.append(event)
        assert store.conversation(store.owner, session) == []

    tutor = Tutor(
        Settings(
            "https://model.invalid/v1",
            "mock-model",
            "test-only",
            database=tmp_path / "stream.db",
        ),
        store,
        Telemetry(enabled=False),
        ScriptedModel([ModelStep(output=[assistant_message("Hello, learner.")])]),
    )
    reply = asyncio.run(tutor.respond(store.owner, session, "Hi", on_progress=progress))
    assert reply.text == "Hello, learner."
    assert (
        "".join(event["text"] for event in events if event["type"] == "reply_delta")
        == reply.text
    )
    assert len(store.conversation(store.owner, session)) == 2
    asyncio.run(tutor.close())
    store.close()


def test_lesson_anchors_only_link_committed_turns(tmp_path):
    store = Store(tmp_path / "anchors.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    first = seed_graph(store, scope, session)["lesson"]
    assert store.lesson_anchors(store.owner, session) == {}
    with store.transaction():
        store.save_turn(context(store, scope, session), "First lesson", [])
    assert store.lesson_anchors(store.owner, session) == {first["id"]: "seed"}
    with store.transaction():
        store.start_lesson(
            context(store, scope, session, "other"),
            "German",
            None,
            skill_spec("verb-forms", "Verb forms"),
            [],
            "Different skill",
        )
        store.save_turn(context(store, scope, session, "other"), "Another lesson", [])
    with store.transaction():
        second = store.start_lesson(
            context(store, scope, session, "review"),
            "German",
            first["focus_skill_id"],
            None,
            [],
            "Review",
        )
        store.save_turn(context(store, scope, session, "review"), "Review lesson", [])
    assert store.lesson_anchors(store.owner, session)[second["id"]] == "review"
    assert [item["id"] for item in store.lessons(scope)][::2] == [
        first["id"],
        second["id"],
    ]
    store.close()


def test_cross_session_skill_reference_is_rejected(tmp_path):
    store = Store(tmp_path / "isolation.db")
    first = store.session(store.owner)
    second = store.session(store.owner)
    a = seed_graph(store, store.learning_scope(store.owner, first), first)["lesson"]
    b_scope = store.learning_scope(store.owner, second)
    assert store.lessons(b_scope) == []
    with pytest.raises(InvalidReference):
        store.start_lesson(
            context(store, b_scope, second),
            "German",
            a["focus_skill_id"],
            None,
            [],
            "Wrong scope",
        )
    store.close()


def test_turn_rollback_removes_lesson_skill_and_events(tmp_path):
    store = Store(tmp_path / "rollback.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    with pytest.raises(RuntimeError, match="failed turn"), store.transaction():
        store.start_lesson(
            context(store, scope, session), "German", None, skill_spec(), [], "Start"
        )
        raise RuntimeError("failed turn")
    assert store.lessons(scope) == []
    assert store.search_skills(scope, "German", "", 20) == []
    assert (
        store.db.execute(
            "SELECT count(*) FROM events WHERE learner=?", (scope,)
        ).fetchone()[0]
        == 0
    )
    store.close()


def test_supersession_keeps_historical_lesson_and_evidence(tmp_path):
    store = Store(tmp_path / "supersede.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    lesson = seed_graph(store, scope, session)["lesson"]
    old = lesson["focus_skill_id"]
    task = exercise(store, scope, session, old, "practice")
    observe(store, scope, session, task["id"], old, "answer")
    replacement = skill_spec("personal-subject-pronouns", "Personal subject pronouns")
    with store.transaction():
        change = store.supersede_skills(
            context(store, scope, session, "correction"),
            [old],
            [replacement],
            [
                {
                    "old_skill_id": old,
                    "new_skill_ref": replacement["key"],
                    "relation": "redefined",
                }
            ],
            [{"old_skill_id": old, "replacement_ref": replacement["key"]}],
            "Clarify the skill definition",
        )
    new_id = change["new_skills"][0]["id"]
    assert store.lesson(scope, lesson["id"])["focus_skill_id"] == old
    assert store.skill(scope, old)["status"] == "superseded"
    assert store.progress(scope, [old])[0]["observations"] == 1
    with store.transaction():
        new_lesson = store.start_lesson(
            context(store, scope, session, "new"),
            "German",
            new_id,
            None,
            [],
            "Use the corrected definition",
        )
    assert not new_lesson["review"]
    assert [item["focus_skill_id"] for item in store.lessons(scope)] == [old, new_id]
    store.close()


def test_exercise_status_and_lesson_survive_reopen(tmp_path):
    path = tmp_path / "reload.db"
    store = Store(path)
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    lesson = seed_graph(store, scope, session)["lesson"]
    task = exercise(store, scope, session, lesson["focus_skill_id"], "task")
    observe(store, scope, session, task["id"], lesson["focus_skill_id"], "answer")
    store.close()
    store = Store(path)
    active = store.active_lesson(scope)
    assert active is not None and active["id"] == lesson["id"]
    assert store.exercise_status(store.owner, session, task["id"])["completed"]
    assert (
        store.progress(scope, [lesson["focus_skill_id"]])[0][
            "independent_since_difficulty"
        ]
        == 1
    )
    store.close()


def test_prompt_state_excludes_full_source_bodies(tmp_path):
    store = Store(tmp_path / "source.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    seed_graph(store, scope, session)
    secret_text = "source-body-sentinel" * 50
    with store.transaction():
        saved = store.save_source(
            context(store, scope, session),
            {
                "status": "available",
                "title": "Learner passage",
                "text": secret_text,
                "provenance": "learner_pasted_unverified",
                "url": None,
            },
        )
    state = store.prompt_state(scope)
    assert secret_text not in json.dumps(state)
    assert state["sources"][0]["id"] == saved["id"]
    store.close()


def test_repeated_difficulty_starts_review_lesson_atomically(tmp_path):
    store = Store(tmp_path / "review.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    first_id = seed_graph(store, scope, session)["lesson"]["focus_skill_id"]
    with store.transaction():
        current = store.start_lesson(
            context(store, scope, session, "next"),
            "German",
            None,
            skill_spec("verb-forms", "Verb forms"),
            [],
            "Next skill",
        )
    current_id = current["focus_skill_id"]
    assert store.review_due(scope) == []
    for number in (1, 2):
        task = exercise(
            store,
            scope,
            session,
            current_id,
            f"review-task-{number}",
            supporting=[first_id],
        )
        result = observe(
            store,
            scope,
            session,
            task["id"],
            first_id,
            f"review-answer-{number}",
            outcome="needs_work",
        )
        if number == 1:
            assert store.review_due(scope) == []
            assert "review_lesson" not in result
            retry = observe(
                store,
                scope,
                session,
                task["id"],
                first_id,
                "retry-same-exercise",
                outcome="needs_work",
            )
            assert "review_lesson" not in retry
    review = result["review_lesson"]
    assert review["review"] and review["focus_skill_id"] == first_id
    active = store.active_lesson(scope)
    assert active is not None and active["id"] == review["id"]
    assert len(store.lessons(scope)) == 3
    assert store.lesson_anchors(store.owner, session)[review["id"]] == "review-answer-2"
    assert store.review_due(scope) == []
    store.close()
