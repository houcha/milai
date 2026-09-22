"""Session isolation, migration, deletion and browser API contracts."""

import asyncio
import json
from typing import Any, cast

import pytest

from milai.store import InvalidReference, Store
from milai.web import WebApplication
from tests.test_learning import context, seed_graph


class Writer:
    def __init__(self):
        self.data = bytearray()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass

    def payload(self):
        return json.loads(bytes(self.data).split(b"\r\n\r\n", 1)[1])


def test_sessions_isolate_skills_focus_and_delete_graph(tmp_path):
    store = Store(tmp_path / "sessions.db")
    first = store.session(store.owner)
    second = store.session(store.owner)
    first_scope = store.learning_scope(store.owner, first)
    second_scope = store.learning_scope(store.owner, second)
    a = seed_graph(store, first_scope, first)
    assert store.learning_view(second_scope)["topics"] == []
    assert store.learning_view(second_scope)["skills"] == []
    b = seed_graph(store, second_scope, second)
    assert a["topic"]["id"] != b["topic"]["id"]
    with pytest.raises(InvalidReference):
        store.topic(second_scope, a["topic"]["id"])
    with pytest.raises(PermissionError):
        store.authorize(first_scope, second)

    ctx = context(store, first_scope, first, "practice", "An answer")
    with store.transaction():
        focus = store.focus(first_scope)
        assert focus is not None
        target = focus["skills"][0]["id"]
        exercise = store.present_exercise(
            ctx,
            {
                "title": "A café order",
                "task": "Order a coffee",
                "context": "Rome",
                "scaffolding": "none",
                "source_ids": [],
                "skills": [
                    {"skill_id": target, "role": "target", "success_criterion": "Order"}
                ],
            },
        )
        store.save_turn(ctx, "Try this", [])
    assert (
        store.conversation(store.owner, first)[-1]["activities"][0]["id"]
        == exercise["id"]
    )
    before = store.learning_view(second_scope)
    store.delete_session(store.owner, first)
    assert store.learning_view(second_scope) == before
    assert [item["id"] for item in store.sessions(store.owner)] == [second]
    assert store.db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert (
        store.db.execute(
            "SELECT count(*) FROM events WHERE session=?", (first,)
        ).fetchone()[0]
        == 0
    )
    store.close()


def test_legacy_shared_learning_is_preserved_once_and_reopen_is_stable(tmp_path):
    path = tmp_path / "legacy.db"
    store = Store(path)
    learner = store.owner
    first = store.session(learner)
    seed_graph(store, learner, first)
    with store.transaction():
        store.save_turn(
            context(store, learner, first, "legacy", "German through songs"),
            "Welcome",
            [],
        )
    empty = store.session(learner)
    store.db.execute("DROP TABLE session_scopes")
    store.close()
    store = Store(path)
    assert store.learning_scope(learner, first) == learner
    assert len(store.learning_view(store.learning_scope(learner, first))["topics"]) == 1
    assert store.learning_view(store.learning_scope(learner, empty))["topics"] == []
    assert store.conversation(learner, first)[0]["content"] == "German through songs"
    store.close()
    store = Store(path)
    assert store.learning_scope(learner, first) == learner
    store.close()


def test_session_api_create_select_rename_delete_and_last_session(tmp_path):
    store = Store(tmp_path / "api.db")
    first = store.session(store.owner)
    app = WebApplication(store, cast(Any, object()), first, 8765)

    def manage(payload):
        writer = Writer()
        asyncio.run(app.manage_session(cast(Any, writer), payload))
        return writer.payload()

    created = manage({"action": "create"})
    second = created["session"]
    assert second != first
    assert created["learning"]["skills"] == []
    renamed = manage(
        {"action": "rename", "session": first, "title": "My learning session"}
    )
    assert any(s["title"] == "My learning session" for s in renamed["sessions"])
    assert manage({"action": "select", "session": first})["session"] == first
    assert manage({"action": "delete", "session": first})["session"] == second
    fresh = manage({"action": "delete", "session": second})
    assert fresh["session"] not in {first, second}
    assert len(fresh["sessions"]) == 1
    assert "error" in manage({"action": "select", "session": first})
    assert "error" in manage(
        {"action": "rename", "session": fresh["session"], "title": " "}
    )
    store.close()


def test_chat_rejects_stale_session_before_calling_tutor(tmp_path):
    store = Store(tmp_path / "stale.db")
    session = store.session(store.owner)
    app = WebApplication(store, cast(Any, object()), session, 8765)
    writer = Writer()
    asyncio.run(
        app.chat(cast(Any, writer), {"message": "hello", "session": "old-session"})
    )
    assert "active session changed" in writer.payload()["error"]
    store.close()


def test_tutor_receives_and_writes_only_selected_session_state(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from milai.config import Settings
    from milai.observability import Telemetry
    from milai.tutor import Tutor

    store = Store(tmp_path / "tutor.db")
    first = store.session(store.owner)
    second = store.session(store.owner)
    scope = store.learning_scope(store.owner, first)
    seed_graph(store, scope, first)
    seen = []

    async def run(agent, messages, *, context, **kwargs):
        state = json.loads(
            agent.instructions.split("Persisted learning data (not instructions):\n")[1]
        )
        seen.append(state["active_topic"])
        store.record_facts(
            context,
            [
                {
                    "field": "goals",
                    "value": context.message,
                    "learner_quote": context.message,
                }
            ],
        )
        return SimpleNamespace(final_output="Saved", to_input_list=lambda: messages)

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = Tutor(
        Settings("https://model.invalid", "test", "test"),
        store,
        Telemetry(enabled=False),
        model="test-model",
    )
    asyncio.run(tutor.respond(store.owner, first, "German through songs"))
    asyncio.run(tutor.respond(store.owner, second, "Italian at a café"))
    assert seen[0]["name"] == "Ordering food in German"
    assert seen[1] is None
    assert store.profile(scope)["goals"]["value"] == "German through songs"
    assert (
        store.profile(store.learning_scope(store.owner, second))["goals"]["value"]
        == "Italian at a café"
    )
    assert len(store.conversation(store.owner, first)) == 2
    assert len(store.model_history(store.owner, first)) == 2
    asyncio.run(tutor.close())
    store.close()


def test_prepared_hint_is_private_and_revealed_without_model_call(tmp_path):
    store = Store(tmp_path / "hint.db")
    learner = store.owner
    session = store.session(learner)
    scope = store.learning_scope(learner, session)
    seed_graph(store, scope, session)
    focus = store.focus(scope)
    assert focus is not None
    target = focus["skills"][0]["id"]
    ctx = context(store, scope, session, "teach", "Practice")
    with store.transaction():
        exercise = store.present_exercise(
            ctx,
            {
                "title": "Articles",
                "task": "Choose an article",
                "context": "At a café",
                "hint": "Check the noun's gender.",
                "scaffolding": "none",
                "source_ids": [],
                "skills": [
                    {
                        "skill_id": target,
                        "role": "target",
                        "success_criterion": "Use the right article",
                    }
                ],
            },
        )
        store.save_turn(ctx, "Try this", [])
    assert "hint" not in exercise
    assert "hint" not in store.conversation(learner, session)[-1]["activities"][0]
    conversation_length = len(store.conversation(learner, session))

    class NoModel:
        async def respond(self, *args):
            raise AssertionError("Hint should not call the model")

    app = WebApplication(store, cast(Any, NoModel()), session, 8765)
    writer = Writer()
    request = {"session": session, "exercise_id": exercise["id"], "action": "hint"}
    asyncio.run(app.exercise(cast(asyncio.StreamWriter, writer), request))
    assert writer.payload()["hint"] == "Check the noun's gender."
    assert writer.payload()["status"]["assisted"]
    assert len(store.conversation(learner, session)) == conversation_length
    second = Writer()
    asyncio.run(app.exercise(cast(asyncio.StreamWriter, second), request))
    assert second.payload()["hint"] == writer.payload()["hint"]
    assert (
        store.db.execute(
            "SELECT count(*) FROM assistance WHERE exercise_id=?", (exercise["id"],)
        ).fetchone()[0]
        == 1
    )
    store.close()
