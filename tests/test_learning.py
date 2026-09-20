# ruff: noqa: E501, SIM117
import asyncio
import json
import sqlite3

import pytest
from agents.tool_context import ToolContext

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import SCHEMA_VERSION, SchemaMismatch, Store
from milai.tools import (
    Context,
    establish_topic,
    record_learner_facts,
)
from milai.tutor import Tutor
from tests.helpers import MockProvider, call, calls, say


def settings(tmp_path, **kwargs):
    return Settings(
        "https://model.invalid/v1",
        "mock-model",
        "test-only",
        database=tmp_path / "test.db",
        **kwargs,
    )


def context(store, learner, session, turn="seed", message="seed"):
    return Context(store, learner, session, turn, message, "test-prompt")


def skill_specs():
    return [
        {
            "local_key": "gender",
            "key": "german.noun-gender-recognition",
            "name": "German noun gender recognition",
            "definition": "Recognize the grammatical gender of common German nouns.",
            "success_criteria": ["Select der, die, or das for familiar nouns."],
        },
        {
            "local_key": "accusative",
            "key": "german.accusative-indefinite-articles",
            "name": "German accusative indefinite articles",
            "definition": "Choose the accusative form of German indefinite articles.",
            "success_criteria": ["Use einen with a masculine direct object."],
        },
        {
            "local_key": "v2",
            "key": "german.main-clause-verb-second",
            "name": "German main-clause verb-second order",
            "definition": "Place the finite verb in second position in a main clause.",
            "success_criteria": ["Produce a main clause with the finite verb second."],
        },
    ]


def establish_plan():
    return {
        "topic": {
            "language": "German",
            "name": "Ordering food in German",
            "purpose": "Apply foundational German grammar while ordering food.",
        },
        "existing_skill_ids": [],
        "new_skills": skill_specs(),
        "prerequisites": [{"prerequisite": "gender", "dependent": "accusative"}],
        "links": [
            {"skill_ref": "gender", "role": "core", "priority": 1},
            {"skill_ref": "accusative", "role": "core", "priority": 2},
            {"skill_ref": "v2", "role": "core", "priority": 3},
        ],
        "initial_focus": {
            "target_refs": ["accusative"],
            "supporting_refs": ["gender", "v2"],
            "reason": "Start with the minimum article contrast in a complete sentence.",
        },
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
                },
                {
                    "field": "goals",
                    "value": "Order food",
                    "learner_quote": "Order food",
                },
            ],
        )
        result = store.establish_topic(
            ctx,
            **{
                "topic": establish_plan()["topic"],
                "existing_skill_ids": [],
                "new_skills": skill_specs(),
                "prerequisites": establish_plan()["prerequisites"],
                "links": establish_plan()["links"],
                "focus": establish_plan()["initial_focus"],
            },
        )
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
    assert len(archived) == 1
    assert archived[0].exists()
    store = Store(path)
    assert (
        store.db.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()[0]
        == SCHEMA_VERSION
    )
    store.close()


def test_graph_is_topic_independent_and_rejects_cycles_and_duplicates(tmp_path):
    store = Store(tmp_path / "graph.db")
    learner = store.owner
    session = store.session(learner)
    result = seed_graph(store, learner, session)
    topic = result["topic"]
    ids = {skill["key"]: skill["id"] for skill in topic["skills"]}

    second = context(store, learner, session, "second")
    with store.transaction():
        reused = store.establish_topic(
            second,
            {
                "language": "German",
                "name": "Talking about a trip",
                "purpose": "Narrate travel.",
            },
            list(ids.values()),
            [],
            [],
            [
                {
                    "skill_ref": ids["german.noun-gender-recognition"],
                    "role": "core",
                    "priority": 1,
                },
                {
                    "skill_ref": ids["german.accusative-indefinite-articles"],
                    "role": "core",
                    "priority": 2,
                },
                {
                    "skill_ref": ids["german.main-clause-verb-second"],
                    "role": "core",
                    "priority": 3,
                },
            ],
            {
                "target_refs": [ids["german.main-clause-verb-second"]],
                "supporting_refs": [],
                "reason": "Reuse sentence order in a new application context.",
            },
        )
    assert {skill["id"] for skill in reused["topic"]["skills"]} == set(ids.values())
    assert len(store.search_skills(learner, "German", "", 20)) == 3

    with pytest.raises(ValueError, match="acyclic"):
        store._validate_edges(
            learner,
            [
                (
                    ids["german.accusative-indefinite-articles"],
                    ids["german.noun-gender-recognition"],
                )
            ],
        )

    duplicate_ctx = context(store, learner, session, "duplicate")
    duplicate = skill_specs()
    duplicate[1]["key"] = duplicate[0]["key"]
    with pytest.raises(ValueError, match="already exists"):
        with store.transaction():
            store.establish_topic(
                duplicate_ctx,
                {"language": "German", "name": "Duplicate", "purpose": "Test."},
                [],
                duplicate,
                [],
                establish_plan()["links"],
                establish_plan()["initial_focus"],
            )
    assert len(store.search_skills(learner, "German", "", 20)) == 3
    store.close()


def test_required_planner_precondition_is_runtime_validated(tmp_path):
    store = Store(tmp_path / "visibility.db")
    learner = store.owner
    session = store.session(learner)
    ctx = context(store, learner, session, message="German for work")
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
                        },
                        {"field": "goals", "value": "work", "learner_quote": "work"},
                    ]
                },
            )
        )
    with store.transaction():
        result = asyncio.run(invoke(establish_topic, ctx, {"plan": establish_plan()}))
    assert json.loads(result)["error"] == "invalid_operation"
    assert store.topics(learner) == []
    ctx.topic_plan_consulted = True
    with store.transaction():
        result = asyncio.run(invoke(establish_topic, ctx, {"plan": establish_plan()}))
    assert result["topic"]["name"] == "Ordering food in German"
    store.close()


def test_structured_activity_order_attempt_evidence_and_replay(tmp_path):
    store = Store(tmp_path / "activities.db")
    learner = store.owner
    session = store.session(learner)
    seeded = seed_graph(store, learner, session)
    skills = {skill["key"]: skill["id"] for skill in seeded["topic"]["skills"]}
    target = skills["german.accusative-indefinite-articles"]
    support = skills["german.main-clause-verb-second"]

    teach = context(store, learner, session, "teach", "Teach me")
    with store.transaction():
        theory = store.present_theory(
            teach,
            {
                "title": "Accusative einen",
                "skill_ids": [target],
                "explanation": "A masculine direct object changes ein to einen.",
                "examples": [
                    {
                        "example": "Ich möchte einen Tee.",
                        "explanation": "Tee is masculine.",
                    }
                ],
                "source_ids": [],
            },
        )
        exercise = store.present_exercise(
            teach,
            {
                "title": "Choose the article",
                "task": "Complete: Ich möchte ___ Tee.",
                "context": "Ordering a drink",
                "scaffolding": "none",
                "skills": [
                    {
                        "skill_id": target,
                        "role": "target",
                        "success_criterion": "Use einen.",
                    },
                    {
                        "skill_id": support,
                        "role": "supporting",
                        "success_criterion": "Keep the verb second.",
                    },
                ],
                "source_ids": [],
            },
        )
        store.save_turn(
            teach,
            "Here is the rule and one practice item.",
            [{"private": "tool traffic"}],
        )

    reply = store.conversation(learner, session)[-1]
    assert [item["kind"] for item in reply["activities"]] == ["theory", "exercise"]
    assert reply["activities"][0] == theory
    assert reply["activities"][1] == exercise
    assert "tool traffic" not in json.dumps(store.model_history(learner, session))

    attempt = context(store, learner, session, "attempt", "Ich möchte einen Tee.")
    with store.transaction():
        store.record_assistance(
            attempt, exercise["id"], [target], "hint", "Use the masculine ending."
        )
        assessed = store.assess_attempt(
            attempt,
            exercise["id"],
            "The sentence is correct.",
            [
                {"skill_id": target, "outcome": "success", "rationale": "Used einen."},
                {
                    "skill_id": support,
                    "outcome": "success",
                    "rationale": "Finite verb is second.",
                },
            ],
        )
        store.save_turn(attempt, "Correct.", [])
    assert assessed["learner_response"] == "Ich möchte einen Tee."
    observed = {item["skill_id"]: item for item in assessed["observations"]}
    assert not observed[target]["independent_success"]
    assert observed[support]["independent_success"]

    same_turn = context(store, learner, session, "same", "answer")
    with pytest.raises(ValueError, match="before the learner"):
        with store.transaction():
            new_exercise = store.present_exercise(
                same_turn,
                {
                    "title": "Fresh item",
                    "task": "Write one sentence.",
                    "context": "Practice",
                    "scaffolding": "none",
                    "skills": [
                        {
                            "skill_id": target,
                            "role": "target",
                            "success_criterion": "Use einen.",
                        }
                    ],
                    "source_ids": [],
                },
            )
            store.assess_attempt(
                same_turn,
                new_exercise["id"],
                "Premature",
                [
                    {
                        "skill_id": target,
                        "outcome": "uncertain",
                        "rationale": "No attempt yet.",
                    }
                ],
            )
    store.close()


def test_prompt_state_and_history_are_bounded_and_omit_source_bodies(tmp_path):
    store = Store(tmp_path / "bounded.db")
    learner = store.owner
    session = store.session(learner)
    seed_graph(store, learner, session)
    ctx = context(store, learner, session, "source", "source")
    with store.transaction():
        source = store.save_source(
            ctx,
            {
                "status": "available",
                "title": "Private source",
                "url": None,
                "provenance": "learner_pasted_unverified",
                "text": "SECRET_BODY" * 500,
            },
        )
    encoded = json.dumps(store.prompt_state(learner), ensure_ascii=False)
    assert len(encoded) <= 16_000
    assert "SECRET_BODY" not in encoded
    assert source["id"] in encoded
    excerpt = store.source_excerpt(learner, source["id"], 0, 20)
    assert excerpt["text"].startswith("SECRET_BODY")
    store.close()


def test_tutor_returns_structured_activities_and_failed_run_rolls_back(tmp_path):
    config = settings(tmp_path)
    store = Store(config.database)
    learner = store.owner
    session = store.session(learner)
    seeded = seed_graph(store, learner, session)
    ids = {skill["key"]: skill["id"] for skill in seeded["topic"]["skills"]}
    target = ids["german.accusative-indefinite-articles"]
    provider = MockProvider(
        [
            calls(
                (
                    "present_theory",
                    {
                        "lesson": {
                            "title": "Accusative articles",
                            "skill_ids": [target],
                            "explanation": "Use einen for a masculine direct object.",
                            "examples": [],
                            "source_ids": [],
                        }
                    },
                ),
                (
                    "present_exercise",
                    {
                        "exercise": {
                            "title": "One article",
                            "task": "Complete: Ich nehme ___ Kaffee.",
                            "context": "At a café",
                            "scaffolding": "none",
                            "skills": [
                                {
                                    "skill_id": target,
                                    "role": "target",
                                    "success_criterion": "Use einen.",
                                }
                            ],
                            "source_ids": [],
                        }
                    },
                ),
            ),
            say("Read the rule, then complete the exercise."),
        ]
    )
    tutor = Tutor(config, store, Telemetry(enabled=False), provider.model)
    reply = asyncio.run(tutor.respond(learner, session, "Teach me now"))
    assert reply.text == "Read the rule, then complete the exercise."
    assert [item["kind"] for item in reply.activities] == ["theory", "exercise"]
    assert store.conversation(learner, session)[-1]["activities"] == reply.activities
    asyncio.run(tutor.close())

    failed_config = settings(tmp_path, max_turns=1)
    failed_provider = MockProvider(
        [
            call(
                "present_theory",
                lesson={
                    "title": "Rolled back",
                    "skill_ids": [target],
                    "explanation": "This must not survive.",
                    "examples": [],
                    "source_ids": [],
                },
            )
        ]
    )
    failed_tutor = Tutor(
        failed_config, store, Telemetry(enabled=False), failed_provider.model
    )
    before = store.db.execute("SELECT count(*) FROM theory_lessons").fetchone()[0]
    with pytest.raises(Exception, match="Max turns"):
        asyncio.run(failed_tutor.respond(learner, session, "Fail this turn"))
    assert (
        store.db.execute("SELECT count(*) FROM theory_lessons").fetchone()[0] == before
    )
    assert all(
        item["content"] != "Fail this turn"
        for item in store.conversation(learner, session)
    )
    asyncio.run(failed_tutor.close())
    store.close()


def test_skill_split_preserves_old_evidence_and_repoints_topic_and_focus(tmp_path):
    store = Store(tmp_path / "supersede.db")
    learner = store.owner
    session = store.session(learner)
    seeded = seed_graph(store, learner, session)
    old_id = next(
        skill["id"]
        for skill in seeded["topic"]["skills"]
        if "accusative" in skill["key"]
    )
    support = next(
        skill["id"]
        for skill in seeded["topic"]["skills"]
        if "verb-second" in skill["key"]
    )
    teach = context(store, learner, session, "teach-old")
    with store.transaction():
        exercise = store.present_exercise(
            teach,
            {
                "title": "Old definition evidence",
                "task": "Use einen.",
                "context": "Test",
                "scaffolding": "none",
                "skills": [
                    {
                        "skill_id": old_id,
                        "role": "target",
                        "success_criterion": "Use einen.",
                    },
                    {
                        "skill_id": support,
                        "role": "supporting",
                        "success_criterion": "Verb second.",
                    },
                ],
                "source_ids": [],
            },
        )
        store.save_turn(teach, "Try it.", [])
    attempt = context(store, learner, session, "old-attempt", "einen")
    with store.transaction():
        assessed = store.assess_attempt(
            attempt,
            exercise["id"],
            "Observed.",
            [{"skill_id": old_id, "outcome": "success", "rationale": "Used einen."}],
        )
        store.save_turn(attempt, "Good.", [])

    change = context(store, learner, session, "change")
    with store.transaction():
        result = store.supersede_skills(
            change,
            [old_id],
            [
                {
                    "local_key": "acc_specific",
                    "key": "german.accusative-indefinite-articles",
                    "name": "German masculine accusative einen",
                    "definition": "Use einen for a masculine singular direct object.",
                    "success_criteria": [
                        "Use einen with masculine singular direct objects."
                    ],
                },
                {
                    "local_key": "acc_other",
                    "key": "german.accusative-nonmasculine-indefinite-articles",
                    "name": "German non-masculine accusative indefinite articles",
                    "definition": "Keep eine or ein for non-masculine direct objects.",
                    "success_criteria": [
                        "Use eine or ein with the matching direct object."
                    ],
                },
            ],
            [
                {
                    "old_skill_id": old_id,
                    "new_skill_ref": "acc_specific",
                    "relation": "split",
                },
                {
                    "old_skill_id": old_id,
                    "new_skill_ref": "acc_other",
                    "relation": "split",
                },
            ],
            [
                {"old_skill_id": old_id, "replacement_ref": "acc_specific"},
                {"old_skill_id": old_id, "replacement_ref": "acc_other"},
            ],
            "The original definition mixed several article cases.",
        )
    new_id, other_id = result["replacements"][old_id]
    assert store.skill(learner, new_id)["version"] == 2
    assert store.skill(learner, old_id)["status"] == "superseded"
    assert (
        store.observations(learner, [old_id], 5)[0]["id"]
        == assessed["observations"][0]["id"]
    )
    topic_skill_ids = {
        skill["id"] for skill in store.topic(learner, seeded["topic"]["id"])["skills"]
    }
    assert {new_id, other_id} <= topic_skill_ids
    focus = store.focus(learner)
    assert focus is not None
    assert {new_id, other_id} <= {skill["id"] for skill in focus["skills"]}
    store.close()
