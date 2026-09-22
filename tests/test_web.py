# ruff: noqa: E501
import asyncio
import json
from typing import Any, cast

from milai.store import Store
from milai.tutor import TutorReply
from milai.web import WebApplication, learning_view


def test_learning_view_projects_topics_focus_and_cross_topic_evidence():
    snapshot = {
        "profile": {
            "target_language": {"value": "German", "learner_quote": "private"},
            "goals": {"value": "Prepare for work in Berlin"},
        },
        "topics": [
            {
                "id": "topic-1",
                "name": "Berlin work conversations",
                "purpose": "Speak with colleagues",
                "skills": [
                    {
                        "id": "skill-1",
                        "name": "German accusative articles",
                        "role": "core",
                    }
                ],
                "prerequisites": [],
            }
        ],
        "focus": {
            "id": "focus-1",
            "topic_id": "topic-1",
            "reason": "Current target",
            "skills": [
                {
                    "id": "skill-1",
                    "name": "German accusative articles",
                    "role": "target",
                }
            ],
        },
        "skills": [
            {
                "id": "skill-1",
                "name": "German accusative articles",
                "progress": {
                    "observations": 3,
                    "independent_successes": 1,
                    "assistance_events": 1,
                    "needs_work": 1,
                    "contexts": ["Berlin work conversations", "Ordering food"],
                },
            }
        ],
    }

    view = learning_view(snapshot)

    assert view["profile"] == {
        "target_language": "German",
        "goals": "Prepare for work in Berlin",
    }
    assert view["topics"][0]["id"] == "topic-1"
    assert view["focus"]["skills"][0]["role"] == "target"
    assert view["skills"][0]["progress"]["contexts"] == [
        "Berlin work conversations",
        "Ordering food",
    ]


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


def test_topic_anchors_follow_committed_session_turns_without_changing_history(
    tmp_path,
):
    from tests.test_learning import context, seed_graph

    store = Store(tmp_path / "anchors.db")
    learner = store.owner
    session = store.session(learner)
    scope = store.learning_scope(learner, session)
    topic = seed_graph(store, scope, session)["topic"]
    # A topic event without its committed conversation is not a usable link.
    assert store.topic_anchors(learner, session) == {}
    with store.transaction():
        store.save_turn(context(store, scope, session), "First explanation", [])
    history = store.model_history(learner, session)
    assert store.topic_anchors(learner, session) == {topic["id"]: "seed"}
    assert store.conversation(learner, session)[1]["turn_id"] == "seed"
    assert "turn_id" not in history[1]

    other = store.session(learner)
    other_scope = store.learning_scope(learner, other)
    other_topic = seed_graph(store, other_scope, other)["topic"]
    # The fixture's uncommitted event reuses a turn ID from a different session.
    assert store.topic_anchors(learner, other) == {}
    assert other_topic["id"] not in store.topic_anchors(learner, session)

    ctx = context(store, scope, session, "next", "Next topic")
    skill_ids = [skill["id"] for skill in topic["skills"]]
    with store.transaction():
        second = store.establish_topic(
            ctx,
            topic={
                "name": "Another context",
                "purpose": "Reuse skills",
                "language": "German",
            },
            existing_skill_ids=skill_ids,
            new_skills=[],
            prerequisites=[],
            links=[
                {"skill_ref": sid, "role": "core", "priority": i}
                for i, sid in enumerate(skill_ids, 1)
            ],
            focus={
                "target_refs": skill_ids[:1],
                "supporting_refs": [],
                "reason": "Reuse",
            },
        )["topic"]
        store.save_turn(ctx, "Next explanation", [])
        store.db.execute(
            "UPDATE topics SET created='same-time' WHERE learner=?", (scope,)
        )
    assert [item["id"] for item in store.topics(scope)] == [topic["id"], second["id"]]
    application = WebApplication(store, cast(Any, object()), session, 8765)
    payload = application.bootstrap()
    assert payload["topic_anchors"] == {topic["id"]: "seed", second["id"]: "next"}
    assert payload["conversation"][-1]["turn_id"] == "next"
    assert store.model_history(learner, session)[:2] == history
    store.close()
