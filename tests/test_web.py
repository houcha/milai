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
