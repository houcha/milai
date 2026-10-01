"""Reviewer routing, private context, atomic storage, and transport contracts."""

import asyncio
import json
from dataclasses import replace

import pytest
from agents import OpenAIResponsesModel
from openai import APIConnectionError
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from milai.config import Settings
from milai.exercises import serialize_answers
from milai.observability import Telemetry
from milai.store import InvalidReference
from milai.tools import Context
from milai.tutor import Tutor, prompts
from tests.helpers import MockProvider, say
from tests.test_typed_exercises import add
from tests.test_typed_exercises import learning as learning


def response(lesson, exercise, *, legacy=False):
    return {
        "assessment": {
            "exercise_id": exercise["id"],
            "feedback": "",
            "score": {"correct": 1, "total": 1} if legacy else None,
            "item_results": []
            if legacy
            else [{"item_number": 1, "correct": True, "feedback": ""}],
            "blank_results": [],
            "observations": [
                {
                    "skill_id": lesson["focus_skill_id"],
                    "outcome": "success",
                    "issue_severity": "none",
                    "rationale": "The requested form is correct.",
                }
            ],
        },
        "reply": "Correct.",
        "summary": "The learner used the requested form. Keep the open question.",
        "completion_summary": None,
    }


def tutor_for(store, provider, *, settings=None, telemetry=None):
    return Tutor(
        settings or Settings("https://model.invalid/v1", "chat", "test-only"),
        store,
        telemetry or Telemetry(enabled=False),
        model=OpenAIResponsesModel("chat", provider.client),
        review_model=OpenAIResponsesModel("gpt-6-luna", provider.client),
    )


def test_configured_review_uses_shared_client_and_independent_settings(
    learning, monkeypatch
):
    store, session, scope, lesson = learning
    exercise = add(learning)
    provider = MockProvider([say(json.dumps(response(lesson, exercise)))])
    monkeypatch.setattr(
        "milai.tutor.providers",
        lambda _: (
            OpenAIResponsesModel("chat", provider.client),
            OpenAIResponsesModel("lesson", provider.client),
        ),
    )
    settings = Settings(
        "https://model.invalid/v1",
        "chat",
        "test-only",
        review_model="custom-review",
        review_reasoning_effort="high",
        review_max_output_tokens=6000,
    )
    tutor = Tutor(settings, store, Telemetry(enabled=False))
    assert (
        tutor.model._client
        is tutor.generation_model._client
        is tutor.review_model._client
    )
    asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "ihr habt",
            exercise_id=exercise["id"],
            action="answer",
        )
    )
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request["model"] == "custom-review"
    assert request["reasoning"]["effort"] == "high"
    assert request["max_output_tokens"] == 6000
    asyncio.run(tutor.close())


@pytest.mark.parametrize(
    "kind,answer",
    [
        ("translate", "ihr habt"),
        ("complete_sentence", "habt"),
        ("transform", "Ihr habt Zeit."),
        ("short_response", "Wir haben ein Fahrrad."),
        ("choose_form", "2"),
    ],
)
def test_one_review_request_and_public_history(learning, kind, answer):
    store, session, scope, lesson = learning
    exercise = add(learning, kind)
    # Keep unrelated document/history out of the review request.
    store.db.execute(
        "UPDATE lesson_documents SET sections=? WHERE lesson_id=?",
        (json.dumps([{"id": "secret", "markdown": "DOCUMENT_SENTINEL"}]), lesson["id"]),
    )
    store.db.execute("UPDATE turns SET reply='HISTORY_SENTINEL'")
    provider = MockProvider([say(json.dumps(response(lesson, exercise)))])
    tutor = tutor_for(store, provider)
    result = asyncio.run(
        tutor.respond(
            store.owner, session, answer, exercise_id=exercise["id"], action="answer"
        )
    )
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request["model"] == "gpt-6-luna"
    assert request["reasoning"]["effort"] == "medium"
    assert request["max_output_tokens"] == 8192
    assert request["service_tier"] == "default"
    assert request["store"] is False
    assert request.get("tools", []) == []
    assert request["text"]["format"]["strict"] is True
    encoded = json.dumps(request)
    assert "DOCUMENT_SENTINEL" not in encoded
    assert "HISTORY_SENTINEL" not in encoded
    assert len(request["instructions"]) < len(prompts()[0])
    data = json.loads(request["input"][-1]["content"].split("\n", 1)[1])
    assert data["completion_context"] == {"previous_assessments": []}
    assert data["exercise"]["id"] == exercise["id"]
    assert data["assessment_contract"]["content"]["type"] == kind
    assert result.assessments[0]["score"] == {"correct": 1, "total": 1}
    assert result.assessments[0]["observations"][0]["independent_success"] is (
        kind != "choose_form"
    )
    items = json.loads(
        store.db.execute(
            "SELECT items FROM turns WHERE id=?", (result.turn_id,)
        ).fetchone()[0]
    )
    assert items == [
        {"role": "user", "content": serialize_answers([answer])},
        {"role": "assistant", "content": "Correct."},
    ]
    assert "assessment_contract" not in json.dumps(
        store.model_history(store.owner, session, lesson_id=lesson["id"])
    )
    assert not result.activities
    asyncio.run(tutor.close())


@pytest.mark.parametrize(
    "failure",
    [
        "wrong_exercise",
        "foreign_skill",
        "missing_item",
        "correct_feedback",
        "malformed",
        "blank_reply",
        "provider",
        "timeout",
    ],
)
def test_failed_review_keeps_submission_available(learning, failure):
    store, session, scope, lesson = learning
    exercise = add(learning)
    good = response(lesson, exercise)
    bad = response(lesson, exercise)
    assessment = bad["assessment"]
    if failure == "wrong_exercise":
        assessment["exercise_id"] = "unavailable"
    elif failure == "foreign_skill":
        assessment["observations"][0]["skill_id"] = "unavailable"
    elif failure == "missing_item":
        assessment["item_results"] = []
    elif failure == "correct_feedback":
        assessment["item_results"][0]["feedback"] = "A hidden answer"
    elif failure == "blank_reply":
        bad["reply"] = " \n "

    def first(_):
        if failure == "provider":
            raise RuntimeError("synthetic transport failure")
        return say("malformed JSON" if failure == "malformed" else json.dumps(bad))

    provider = MockProvider([first, say(json.dumps(good))])
    settings = Settings("https://model.invalid/v1", "chat", "test-only")
    tutor = tutor_for(
        store,
        provider,
        settings=replace(settings, timeout=0) if failure == "timeout" else settings,
    )
    baseline = list(store.db.iterdump())
    expected = (
        TimeoutError
        if failure == "timeout"
        else APIConnectionError
        if failure == "provider"
        else (ValueError, InvalidReference)
    )
    with pytest.raises(expected):
        asyncio.run(
            tutor.respond(
                store.owner,
                session,
                "ihr habt",
                exercise_id=exercise["id"],
                action="answer",
            )
        )
    assert list(store.db.iterdump()) == baseline
    assert not store.exercise_status(store.owner, session, exercise["id"])["submitted"]
    # Failure never triggers a Sol fallback or a second request.
    assert len(provider.requests) == (0 if failure == "timeout" else 1)
    if failure == "timeout":
        provider.steps.pop(0)
    tutor.settings = settings
    result = asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "ihr habt",
            exercise_id=exercise["id"],
            action="answer",
        )
    )
    assert result.assessments[0]["score"]["correct"] == 1
    asyncio.run(tutor.close())


@pytest.mark.parametrize("inline", [False, True])
def test_legacy_review_preserves_scoring(learning, inline):
    store, session, scope, lesson = learning
    exercise = store.lesson_detail(store.owner, session, lesson["id"])["exercises"][0]
    task = (
        "Fill in: ihr {{blank}} Zeit."
        if inline
        else "Write the present-tense form of haben for ihr."
    )
    store.db.execute("UPDATE exercises SET task=? WHERE id=?", (task, exercise["id"]))
    output = response(lesson, exercise, legacy=True)
    if inline:
        output["assessment"]["blank_results"] = [
            {"blank_number": 1, "correct": True, "feedback": ""}
        ]
    provider = MockProvider([say(json.dumps(output))])
    tutor = tutor_for(store, provider)
    result = asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "Blank 1: habt" if inline else "habt",
            exercise_id=exercise["id"],
            action="answer",
        )
    )
    assert result.assessments[0]["score"] == {"correct": 1, "total": 1}
    assert (result.assessments[0]["blank_results"] or []) == output["assessment"][
        "blank_results"
    ]
    assert len(provider.requests) == 1
    asyncio.run(tutor.close())


def test_assistance_context_and_trace_privacy(learning, monkeypatch):
    store, session, scope, lesson = learning
    exercise = add(learning)
    ctx = Context(store, scope, session, "help", "Help", "test", lesson_id=lesson["id"])
    with store.transaction():
        store.record_assistance(
            ctx,
            exercise["id"],
            [lesson["focus_skill_id"]],
            "explanation",
            "PRIVATE_HINT_SENTINEL",
        )
        store.save_turn(ctx, "Hint", [])
    monkeypatch.setenv("MILAI_TRACE_CONTENT", "false")
    exporter = InMemorySpanExporter()
    telemetry = Telemetry(exporter=exporter)
    provider = MockProvider([say(json.dumps(response(lesson, exercise)))])
    tutor = tutor_for(store, provider, telemetry=telemetry)
    result = asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "ihr habt",
            exercise_id=exercise["id"],
            action="answer",
        )
    )
    assert not result.assessments[0]["observations"][0]["independent_success"]
    data = json.loads(provider.requests[0]["input"][-1]["content"].split("\n", 1)[1])
    assert data["assistance"] == [
        {"skill_id": lesson["focus_skill_id"], "level": "explanation"}
    ]
    assert "PRIVATE_HINT_SENTINEL" not in json.dumps(data)
    spans = exporter.get_finished_spans()
    assert (
        sum((s.attributes or {}).get("openinference.span.kind") == "LLM" for s in spans)
        == 1
    )
    attrs = next(s.attributes for s in spans if s.name == "tutor-turn")
    assert attrs is not None
    assert attrs["milai.review_requests"] == 1
    assert attrs["milai.review_input_tokens"] == 20
    assert attrs["milai.review_output_tokens"] == 10
    assert attrs["milai.tool_calls"] == 0
    assert "ihr habt" not in str([s.attributes for s in spans])
    asyncio.run(tutor.close())
