# ruff: noqa: E501
"""Complete lesson generation contracts and serialized planner settings."""

import asyncio
import json
from types import SimpleNamespace

import httpx2 as httpx
import pytest
from agents import OpenAIResponsesModel
from agents.tool_context import ToolContext
from openai import BadRequestError

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import Store
from milai.tools import Context, _LessonPlan, _validated_lesson_draft, start_lesson
from milai.tutor import Tutor
from tests.helpers import MockProvider, say


def draft():
    criterion = "Choose the matching subject pronoun for a named subject."
    return {
        "existing_skill_key": None,
        "new_skill": {
            "key": "subject-pronouns",
            "name": "Subject pronouns",
            "definition": "Choose subject pronouns to match person and number.",
            "success_criteria": [criterion],
        },
        "prerequisite_keys": [],
        "reason": "Begin with a reusable sentence-building skill.",
        "document": {
            "objective": "Choose a subject pronoun that matches the person and number of a named subject.",
            "sections": [
                {
                    "id": "person",
                    "title": "Person",
                    "markdown": "Subject pronouns name who performs an action. Start by identifying whether the subject is the speaker, listener, or someone else.",
                },
                {
                    "id": "number",
                    "title": "Number",
                    "markdown": "Next decide whether the subject is one person or a group. Choose a form that matches both person and number.",
                },
            ],
            "worked_examples": [
                {
                    "id": "one-speaker",
                    "title": "One speaker",
                    "markdown": "**Ich lerne.** means *I am learning*. The subject is the speaker alone, so **ich** fits.",
                },
                {
                    "id": "speaker-group",
                    "title": "Speaker with others",
                    "markdown": "**Wir lernen.** means *We are learning*. The subject includes the speaker and others, so **wir** fits.",
                },
            ],
            "recap": "Identify the subject's person and number, then choose the matching subject pronoun.",
        },
        "exercises": [
            {
                "title": f"Choose a subject pronoun {index}",
                "task": f"Write a matching pronoun for the stated subject in situation {index}.",
                "context": "A short sentence",
                "scaffolding": "cues" if index == 1 else "none",
                "skills": [
                    {
                        "skill_key": "subject-pronouns",
                        "role": "target",
                        "success_criterion": criterion,
                    }
                ],
                "source_ids": [],
            }
            for index in range(1, 4)
        ],
    }


async def invoke(ctx):
    arguments = json.dumps({"lesson": {"intent": "Begin German"}})
    return await start_lesson.on_invoke_tool(
        ToolContext(
            ctx,
            tool_name=start_lesson.name,
            tool_call_id="lesson-test",
            tool_arguments=arguments,
        ),
        arguments,
    )


def test_planner_request_uses_separate_sol_settings_and_commits_document(tmp_path):
    store = Store(tmp_path / "generation.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    mock = MockProvider([say(json.dumps(draft()))])
    ctx = Context(
        store,
        scope,
        session,
        "lesson-turn",
        "German please",
        "prompt-v1",
        generation_model=OpenAIResponsesModel("gpt-6-sol", mock.client),
        planner_instructions="Make a complete German lesson.",
    )
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
        saved = asyncio.run(invoke(ctx))
        store.save_turn(ctx, "Open the lesson card.", [])
    assert saved["id"] == ctx.lesson_ids[0]
    detail = store.lesson_detail(store.owner, session, saved["id"])
    assert detail["sections"][0]["id"] == "person"
    assert len(detail["exercises"]) == 3
    assert len(mock.requests) == 1
    request = mock.requests[0]
    assert request["model"] == "gpt-6-sol"
    assert request["reasoning"]["effort"] == "low"
    assert request["service_tier"] == "fast"
    assert request["max_output_tokens"] == 32768
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["store"] is False
    assert "validated_source_excerpts" in request["input"][0]["content"]
    asyncio.run(mock.client.close())
    store.close()


def test_interactive_request_keeps_chat_model_and_low_effort(tmp_path):
    store = Store(tmp_path / "interactive.db")
    session = store.session(store.owner)
    mock = MockProvider([say("Hello, learner.")])
    tutor = Tutor(
        Settings("https://model.invalid/v1", "gpt-6-sol", "test"),
        store,
        Telemetry(enabled=False),
        model=OpenAIResponsesModel("gpt-6-sol", mock.client),
        generation_model=OpenAIResponsesModel("gpt-6-sol", mock.client),
    )
    reply = asyncio.run(tutor.respond(store.owner, session, "Hello"))
    assert reply.text == "Hello, learner."
    assert len(mock.requests) == 1
    request = mock.requests[0]
    assert request["model"] == "gpt-6-sol"
    assert request["reasoning"]["effort"] == "low"
    assert request["max_output_tokens"] == 4096
    assert "service_tier" not in request
    asyncio.run(tutor.close())
    store.close()


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["document"].update({"recap": ""}),
        lambda value: value["exercises"][1].update({"scaffolding": "cues"}),
        lambda value: value["exercises"][2].update({"scaffolding": "cues"}),
        lambda value: value["exercises"][0]["skills"][0].update(
            {"skill_key": "invented"}
        ),
        lambda value: value["exercises"][0].update({"source_ids": ["invented"]}),
        lambda value: value["document"]["sections"][1].update({"id": "person"}),
    ],
)
def test_incomplete_or_invalid_draft_is_rejected(change):
    value = draft()
    change(value)
    try:
        plan = _LessonPlan.model_validate(value)
    except ValueError:
        return
    with pytest.raises(RuntimeError):
        _validated_lesson_draft(plan, {}, set())


def test_incomplete_structured_output_rolls_back_generation_turn(tmp_path):
    store = Store(tmp_path / "incomplete.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    mock = MockProvider([say("{}")])
    ctx = Context(
        store,
        scope,
        session,
        "incomplete-turn",
        "German please",
        "prompt-v1",
        generation_model=OpenAIResponsesModel("gpt-6-sol", mock.client),
        planner_instructions="Make a complete lesson.",
    )
    with pytest.raises(RuntimeError, match="structured output"), store.transaction():
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
        asyncio.run(invoke(ctx))
    assert store.lessons(scope) == []
    assert store.profile(scope) == {}
    assert len(mock.requests) == 1
    asyncio.run(mock.client.close())
    store.close()


def test_rejected_generation_request_rolls_back_without_retry(tmp_path):
    class RejectingProvider(MockProvider):
        async def handle(self, request):
            self.requests.append(json.loads(request.content))
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Unsupported generation configuration",
                        "type": "invalid_request_error",
                    }
                },
            )

    store = Store(tmp_path / "rejected.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    mock = RejectingProvider([])
    ctx = Context(
        store,
        scope,
        session,
        "rejected-turn",
        "German please",
        "prompt-v1",
        generation_model=OpenAIResponsesModel("gpt-6-sol", mock.client),
        planner_instructions="Make a complete lesson.",
    )
    with pytest.raises(BadRequestError), store.transaction():
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
        asyncio.run(invoke(ctx))
    assert store.lessons(scope) == []
    assert store.profile(scope) == {}
    assert len(mock.requests) == 1
    asyncio.run(mock.client.close())
    store.close()


def test_generation_timeout_rolls_back_document_exercises_and_turn(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "timed-out.db")
    session = store.session(store.owner)
    source = draft()
    exercises = [
        {
            **item,
            "skills": [{**skill, "skill_id": "@focus"} for skill in item["skills"]],
        }
        for item in source["exercises"]
    ]

    async def slow_run(agent, messages, *, context, **kwargs):
        store.record_facts(
            context,
            [
                {
                    "field": "target_language",
                    "value": "German",
                    "learner_quote": "German",
                }
            ],
        )
        store.start_lesson(
            context,
            "German",
            None,
            source["new_skill"],
            [],
            source["reason"],
            document=source["document"],
            exercises=exercises,
        )
        await asyncio.sleep(0.05)
        return SimpleNamespace(
            final_output="Open lesson", to_input_list=lambda: messages
        )

    monkeypatch.setattr("milai.tutor.Runner.run", slow_run)
    tutor = Tutor(
        Settings("https://model.invalid", "chat", "test", timeout=0.005),
        store,
        Telemetry(enabled=False),
        model="interactive-test-model",
        generation_model="generation-test-model",
    )
    with pytest.raises(TimeoutError):
        asyncio.run(tutor.respond(store.owner, session, "Create a German lesson"))
    scope = store.learning_scope(store.owner, session)
    assert store.profile(scope) == {}
    assert store.lessons(scope) == []
    assert store.db.execute("SELECT count(*) FROM lesson_documents").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM exercises").fetchone()[0] == 0
    assert store.conversation(store.owner, session) == []
    asyncio.run(tutor.close())
    store.close()
