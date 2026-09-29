import asyncio
from types import SimpleNamespace

import httpx2
import pytest
from openai import RateLimitError

from milai import cli
from milai.config import Settings
from milai.store import SCHEMA_VERSION, Store
from milai.tutor import TutorReply


def test_probe_quota_message_is_sanitized_and_not_retried(monkeypatch, capsys):
    calls = []

    async def limited(*args):
        calls.append(True)
        raise RateLimitError(
            "provider-private-detail",
            response=httpx2.Response(
                429, request=httpx2.Request("POST", "https://model.invalid")
            ),
            body=None,
        )

    monkeypatch.setattr("sys.argv", ["milai", "probe"])
    monkeypatch.setattr(cli, "probe", limited)
    monkeypatch.setattr(cli, "Telemetry", lambda: None)
    monkeypatch.setattr(
        Settings, "load", lambda: Settings("https://model.invalid", "mock", "secret")
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    output = capsys.readouterr().err
    assert "quota" in output and "no automatic retry" in output
    assert "provider-private-detail" not in output
    assert len(calls) == 1


def test_reset_requires_acknowledgement_and_archives_database(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "learning.db"
    original = Store(path)
    original.close()
    monkeypatch.setenv("MILAI_DATABASE", str(path))
    monkeypatch.setattr("sys.argv", ["milai", "reset"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert path.exists()

    monkeypatch.setattr("sys.argv", ["milai", "reset", "--yes"])
    cli.main()
    output = capsys.readouterr().out
    assert "Archived:" in output and f"Created schema {SCHEMA_VERSION}" in output
    assert list(tmp_path.glob("learning.db.legacy-*.bak"))
    reopened = Store(path)
    reopened.close()


def test_cli_renders_free_text_explanation_and_persisted_exercise(capsys):
    cli.print_reply(
        TutorReply(
            text="First the rule, then practice.",
            activities=[
                {
                    "kind": "exercise",
                    "title": "Yesterday",
                    "context": "A trip",
                    "task": "Complete: I {{blank}} to the station (walk).",
                    "skills": [{"name": "Regular past formation"}],
                },
            ],
        )
    )
    output = capsys.readouterr().out
    assert "First the rule, then practice." in output
    assert "[EXERCISE] Yesterday" in output
    assert "Complete: I ___ [blank 1] to the station" in output
    assert "{{blank}}" not in output


def test_cli_renders_open_lesson_card(capsys):
    cli.print_reply(
        TutorReply(
            text="I prepared one skill for your trip.",
            activities=[],
            lesson_cards=[{"id": "lesson-1", "title": "Past tense"}],
        )
    )
    output = capsys.readouterr().out
    assert "I prepared one skill for your trip" in output
    assert "[OPEN LESSON] Past tense · /lesson lesson-1" in output


def test_cli_opens_stored_lesson_and_routes_answer_and_continuation(
    monkeypatch, capsys
):
    calls = []

    class FakeStore:
        owner = "learner"

        def __init__(self, database):
            pass

        def session(self, learner, session=None):
            return "session-1"

        def conversation(self, learner, session, limit=50, *, lesson_id=None):
            return []

        def learning_scope(self, learner, session):
            return session

        def lessons(self, scope):
            return [{"id": "lesson-1", "title": "Past tense"}]

        def lesson_detail(self, learner, session, lesson_id):
            assert (learner, session, lesson_id) == (
                "learner",
                "session-1",
                "lesson-1",
            )
            return {
                "id": lesson_id,
                "title": "Past tense",
                "objective": "Tell someone what happened yesterday.",
                "sections": [
                    {"id": "form", "title": "Form", "markdown": "Use the past form."}
                ],
                "worked_examples": [],
                "recap": "Use went for go.",
                "exercises": [
                    {"id": "exercise-1", "title": "A trip", "task": "I ___ there."}
                ],
            }

        def exercise_status(self, learner, session, exercise_id):
            return {"completed": False}

        def close(self):
            pass

    class FakeTutor:
        def __init__(self, settings, store, telemetry):
            pass

        async def respond(self, learner, session, message, **kwargs):
            calls.append((message, kwargs))
            return SimpleNamespace(text="Okay", activities=[], lesson_cards=[])

        async def close(self):
            pass

    inputs = iter(
        [
            "/lessons",
            "/lesson lesson-1",
            "Why use went?",
            "/answer exercise-1 I went there.",
            "/back",
            "Continue learning from that lesson.",
            "/quit",
        ]
    )

    async def read_input(func, prompt):
        return func(prompt)

    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    monkeypatch.setattr(cli.asyncio, "to_thread", read_input)
    monkeypatch.setattr(cli, "Store", FakeStore)
    monkeypatch.setattr(cli, "Tutor", FakeTutor)
    monkeypatch.setattr(cli, "Telemetry", lambda: None)
    settings = Settings("https://model.invalid", "mock", "secret")
    asyncio.run(cli.chat(settings, None))

    assert calls == [
        ("Why use went?", {"lesson_id": "lesson-1", "origin_lesson_id": None}),
        (
            "I went there.",
            {"lesson_id": "lesson-1", "exercise_id": "exercise-1", "action": "answer"},
        ),
        (
            "Continue learning from that lesson.",
            {"lesson_id": None, "origin_lesson_id": "lesson-1"},
        ),
    ]
    output = capsys.readouterr().out
    assert "Objective: Tell someone what happened yesterday" in output
    assert "Use the past form" in output
    assert "I ___ there" in output
