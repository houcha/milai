# ruff: noqa: E501
import asyncio
import json
from typing import Any, cast

from milai.store import Store
from milai.tutor import TutorReply
from milai.web import WebApplication, learning_view


def test_learning_view_projects_lessons_and_mastery():
    snapshot = {
        "profile": {"target_language": {"value": "German", "learner_quote": "German"}},
        "lessons": [{"id": "lesson-1", "title": "German · Subject pronouns"}],
        "active_lesson": {"id": "lesson-1", "focus_skill_id": "skill-1"},
        "skills": [
            {
                "id": "skill-1",
                "name": "Subject pronouns",
                "mastered": True,
                "progress": {"independent_successes": 2},
            }
        ],
    }
    view = learning_view(snapshot)
    assert view["profile"] == {"target_language": "German"}
    assert view["lessons"][0]["title"] == "German · Subject pronouns"
    assert view["active_lesson"]["focus_skill_id"] == "skill-1"
    assert view["skills"][0]["mastered"] is True


def test_chat_api_serializes_structured_reply(tmp_path):
    class FakeTutor:
        async def respond(self, learner, session, message):
            return TutorReply(
                text="Try this.",
                activities=[
                    {
                        "id": "exercise-1",
                        "kind": "exercise",
                        "title": "Past form",
                        "task": "Complete the sentence.",
                    }
                ],
            )

    class Writer:
        def __init__(self):
            self.data = bytearray()

        def write(self, value):
            self.data.extend(value)

        async def drain(self):
            return None

    store = Store(tmp_path / "web.db")
    session = store.session(store.owner)
    application = WebApplication(store, cast(Any, FakeTutor()), session, 8765)
    writer = Writer()
    asyncio.run(
        application.chat(cast(asyncio.StreamWriter, writer), {"message": "Practice"})
    )
    body = bytes(writer.data).split(b"\r\n\r\n", 1)[1]
    payload = json.loads(body)
    assert payload["reply"]["text"] == "Try this."
    assert payload["reply"]["activities"][0]["kind"] == "exercise"
    store.close()


def test_chat_stream_sends_draft_then_committed_result(tmp_path):
    class FakeTutor:
        async def respond(self, learner, session, message, on_progress):
            await on_progress({"type": "planner_delta", "text": '{"new_skills":['})
            await on_progress({"type": "reply_delta", "text": "Try this."})
            return TutorReply(text="Try this.", activities=[])

    class Writer:
        def __init__(self):
            self.data = bytearray()

        def write(self, value):
            self.data.extend(value)

        async def drain(self):
            return None

    store = Store(tmp_path / "stream-web.db")
    session = store.session(store.owner)
    app = WebApplication(store, cast(Any, FakeTutor()), session, 8765)
    writer = Writer()
    asyncio.run(
        app.chat_stream(
            cast(asyncio.StreamWriter, writer),
            {"message": "Practice", "session": session},
        )
    )
    headers, body = bytes(writer.data).split(b"\r\n\r\n", 1)
    assert b"application/x-ndjson" in headers
    events = [json.loads(line) for line in body.splitlines()]
    assert [event["type"] for event in events] == [
        "stage",
        "planner_delta",
        "reply_delta",
        "complete",
    ]
    assert events[-1]["result"]["reply"]["text"] == "Try this."
    store.close()


def test_chat_timeout_reports_provider_and_preserves_session(tmp_path):
    class SlowTutor:
        async def respond(self, learner, session, message):
            raise TimeoutError

    class Writer:
        def __init__(self):
            self.data = bytearray()

        def write(self, value):
            self.data.extend(value)

        async def drain(self):
            pass

    store = Store(tmp_path / "timeout.db")
    session = store.session(store.owner)
    app = WebApplication(store, cast(Any, SlowTutor()), session, 8765)
    writer = Writer()
    asyncio.run(app.chat(cast(asyncio.StreamWriter, writer), {"message": "hello"}))
    assert b"504 Gateway Timeout" in writer.data
    assert (
        "not saved" in json.loads(bytes(writer.data).split(b"\r\n\r\n", 1)[1])["error"]
    )
    assert store.conversation(store.owner, session) == []
    store.close()


def test_bootstrap_replays_complete_conversation_and_latest_session(tmp_path):
    store = Store(tmp_path / "web.db")
    learner = store.owner
    assert store.latest_session(learner) is None
    first = store.session(learner)
    second = store.session(learner)
    assert store.latest_session(learner) is None

    for index in range(60):
        store.db.execute(
            "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"turn-{index}",
                second,
                learner,
                f"2026-01-01T00:00:{index:02d}",
                f"question {index}",
                f"answer {index}",
                "[]",
                "test",
            ),
        )
    empty = store.session(learner)
    assert store.latest_session(learner) == second

    application = WebApplication(store, cast(Any, object()), second, 8765)
    content_type, bundle = application.assets["/markdown.bundle.js"]
    assert content_type.startswith("text/javascript")
    assert bundle.read_bytes()
    conversation = application.bootstrap()["conversation"]
    assert len(conversation) == 120
    assert [item["content"] for item in conversation[:2]] == [
        "question 0",
        "answer 0",
    ]
    assert [item["content"] for item in conversation[-2:]] == [
        "question 59",
        "answer 59",
    ]
    assert store.conversation(learner, first) == []
    assert store.conversation(learner, empty) == []
    store.close()


def test_lesson_anchors_follow_committed_session_turns(tmp_path):
    from tests.test_learning import context, seed_graph

    store = Store(tmp_path / "anchors.db")
    learner = store.owner
    session = store.session(learner)
    scope = store.learning_scope(learner, session)
    lesson = seed_graph(store, scope, session)["lesson"]
    assert store.lesson_anchors(learner, session) == {}
    with store.transaction():
        store.save_turn(context(store, scope, session), "First explanation", [])
    history = store.model_history(learner, session)
    assert store.lesson_anchors(learner, session) == {lesson["id"]: "seed"}
    assert "turn_id" not in history[1]
    application = WebApplication(store, cast(Any, object()), session, 8765)
    assert application.bootstrap()["lesson_anchors"] == {lesson["id"]: "seed"}
    store.close()
