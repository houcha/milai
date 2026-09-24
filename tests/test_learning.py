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
from tests.helpers import MockProvider, call, say


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
            "key": "german.noun-gender-recognition",
            "name": "German noun gender recognition",
            "definition": "Recognize the grammatical gender of common German nouns.",
            "success_criteria": ["Select der, die, or das for familiar nouns."],
        },
        {
            "key": "german.accusative-indefinite-articles",
            "name": "German accusative indefinite articles",
            "definition": "Choose the accusative form of German indefinite articles.",
            "success_criteria": ["Use einen with a masculine direct object."],
        },
        {
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
        "prerequisites": [
            {
                "prerequisite": "german.noun-gender-recognition",
                "dependent": "german.accusative-indefinite-articles",
            }
        ],
        "links": [
            {
                "skill_ref": "german.noun-gender-recognition",
                "role": "core",
                "priority": 1,
            },
            {
                "skill_ref": "german.accusative-indefinite-articles",
                "role": "core",
                "priority": 2,
            },
            {
                "skill_ref": "german.main-clause-verb-second",
                "role": "core",
                "priority": 3,
            },
        ],
        "initial_focus": {
            "target_refs": ["german.accusative-indefinite-articles"],
            "supporting_refs": [
                "german.noun-gender-recognition",
                "german.main-clause-verb-second",
            ],
            "reason": "Start with the minimum article contrast in a complete sentence.",
        },
    }


def planner_plan():
    plan = establish_plan().copy()
    plan.pop("topic")
    plan["existing_skill_keys"] = plan.pop("existing_skill_ids")
    return plan


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


@pytest.mark.parametrize(
    "level", [None, "Starting from scratch", "Comfortable reading simpler texts"]
)
def test_establish_topic_uses_private_structured_planner_and_derived_language(
    tmp_path, level
):
    store = Store(tmp_path / "visibility.db")
    learner = store.owner
    session = store.session(learner)
    missing_profile = context(store, learner, session, message="Start a work topic")
    with store.transaction():
        result = asyncio.run(
            invoke(
                establish_topic,
                missing_profile,
                {"topic": {"name": "Work", "purpose": "Speak with colleagues"}},
            )
        )
    assert json.loads(result)["error"] == "invalid_operation"

    provider = MockProvider([say(json.dumps(planner_plan()))])
    ctx = context(
        store,
        learner,
        session,
        message="German for work" + (f". {level}" if level else ""),
    )
    ctx.model = provider.model
    ctx.planner_instructions = "Return the minimum reusable skill graph."
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
    if level is not None:
        with store.transaction():
            store.record_facts(
                ctx, [{"field": "level", "value": level, "learner_quote": level}]
            )
    with store.transaction():
        result = asyncio.run(
            invoke(
                establish_topic,
                ctx,
                {
                    "topic": {
                        "name": "Ordering food in German",
                        "purpose": "Apply foundational German grammar while ordering food.",
                    }
                },
            )
        )
    assert result["topic"]["name"] == "Ordering food in German"
    assert result["topic"]["language"] == "German"
    planner_input = json.loads(
        provider.requests[0]["messages"][-1]["content"].split("\n", 1)[1]
    )
    assert planner_input["learner_profile"].get("level") == level
    assert planner_input["learner_profile"]["target_language"] == "German"
    assert planner_input["skill_evidence"] == []
    assert planner_input["reusable_active_skills"] == []
    assert provider.requests[0]["reasoning_effort"] == "high"
    assert provider.requests[0]["response_format"]["type"] == "json_schema"
    with store.transaction():
        repeated = asyncio.run(
            invoke(
                establish_topic,
                ctx,
                {
                    "topic": {
                        "name": "Repeated topic",
                        "purpose": "Must not run the private planner again.",
                    }
                },
            )
        )
    assert json.loads(repeated)["error"] == "invalid_operation"
    assert len(provider.requests) == 1
    store.close()


def test_establish_topic_accepts_reused_skill_keys_from_planner(tmp_path):
    store = Store(tmp_path / "reuse-keys.db")
    learner = store.owner
    session = store.session(learner)
    seeded = seed_graph(store, learner, session)
    skills = seeded["topic"]["skills"]
    practiced_skill = next(
        skill
        for skill in skills
        if skill["key"] == "german.accusative-indefinite-articles"
    )
    teach = context(store, learner, session, "teach-evidence", "Practice")
    with store.transaction():
        exercise = store.present_exercise(
            teach,
            {
                "title": "Article practice",
                "task": "Choose an article",
                "context": "Food",
                "scaffolding": "none",
                "source_ids": [],
                "skills": [
                    {
                        "skill_id": practiced_skill["id"],
                        "role": "target",
                        "success_criterion": "Choose correctly",
                    }
                ],
            },
        )
        store.save_turn(teach, "Try this.", [])
    attempt = context(store, learner, session, "attempt-evidence", "ein")
    with store.transaction():
        store.record_assistance(
            attempt,
            exercise["id"],
            [practiced_skill["id"]],
            "explanation",
            "Check gender.",
        )
        store.assess_attempt(
            attempt,
            exercise["id"],
            "Correct with help.",
            [
                {
                    "skill_id": practiced_skill["id"],
                    "outcome": "success",
                    "rationale": "Correct article.",
                }
            ],
        )
        store.save_turn(attempt, "Correct with help.", [])
    # A different language must never enter the German planner's evidence.
    with store.transaction():
        other_skills = [
            {**skill, "key": skill["key"].replace("german.", "english.")}
            for skill in skill_specs()
        ]
        store.establish_topic(
            context(store, learner, session, "other"),
            topic={
                "language": "English",
                "name": "English food",
                "purpose": "Read menus",
            },
            existing_skill_ids=[],
            new_skills=other_skills,
            prerequisites=[],
            links=[
                {"skill_ref": skill["key"], "role": "core", "priority": index}
                for index, skill in enumerate(other_skills, 1)
            ],
            focus={
                "target_refs": [other_skills[0]["key"]],
                "supporting_refs": [],
                "reason": "Read",
            },
        )
    plan = {
        "existing_skill_keys": [skill["key"] for skill in skills],
        "new_skills": [],
        "prerequisites": [],
        "links": [
            {"skill_ref": skill["key"], "role": "core", "priority": position}
            for position, skill in enumerate(skills, 1)
        ],
        "initial_focus": {
            "target_refs": [skills[0]["key"]],
            "supporting_refs": [skill["key"] for skill in skills[1:]],
            "reason": "Reuse the established foundations in a new context.",
        },
    }
    provider = MockProvider([say(json.dumps(plan))])
    ctx = context(store, learner, session, "reuse", "German for travel")
    ctx.model = provider.model
    ctx.planner_instructions = "Return the minimum reusable skill graph."

    with store.transaction():
        result = asyncio.run(
            invoke(
                establish_topic,
                ctx,
                {
                    "topic": {
                        "name": "German travel conversations",
                        "purpose": "Reuse foundational German while travelling.",
                    }
                },
            )
        )

    assert {skill["id"] for skill in result["topic"]["skills"]} == {
        skill["id"] for skill in skills
    }
    planner_input = json.loads(
        provider.requests[0]["messages"][-1]["content"].split("\n", 1)[1]
    )
    evidence = {item["skill_key"]: item for item in planner_input["skill_evidence"]}
    assert set(evidence) == {skill["key"] for skill in skills}
    practiced = evidence[practiced_skill["key"]]
    assert practiced["observations"] == 1
    assert practiced["successes"] == 1
    assert practiced["independent_successes"] == 0
    assert practiced["assistance_events"] == 1
    assert all("id" not in item for item in evidence.values())
    assert all(
        evidence[skill["key"]]["observations"] == 0
        for skill in skills
        if skill["id"] != practiced_skill["id"]
    )
    store.close()


def test_free_text_explanation_structured_exercise_attempt_and_replay(tmp_path):
    store = Store(tmp_path / "activities.db")
    learner = store.owner
    session = store.session(learner)
    seeded = seed_graph(store, learner, session)
    skills = {skill["key"]: skill["id"] for skill in seeded["topic"]["skills"]}
    target = skills["german.accusative-indefinite-articles"]
    support = skills["german.main-clause-verb-second"]

    teach = context(store, learner, session, "teach", "Teach me")
    with store.transaction():
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
            "A masculine direct object changes ein to einen. "
            "For example: Ich möchte einen Tee. Now try the exercise.",
            [{"private": "tool traffic"}],
        )

    reply = store.conversation(learner, session)[-1]
    assert reply["activities"] == [exercise]
    replay = json.dumps(store.model_history(learner, session))
    assert "masculine direct object" in replay
    assert "tool traffic" not in replay
    assert "Presented activities" not in replay
    assert exercise["id"] not in replay
    assert "active_exercise" in store.prompt_state(learner)
    assert store.prompt_state(learner)["active_exercise"]["id"] == exercise["id"]

    attempt = context(store, learner, session, "attempt", "Ich möchte einen Tee.")
    with store.transaction():
        store.record_assistance(
            attempt,
            exercise["id"],
            [target],
            "explanation",
            "Use the masculine ending.",
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


def test_model_history_does_not_replay_an_existing_leaked_exercise(tmp_path):
    store = Store(tmp_path / "leaked-activity.db")
    learner = store.owner
    session = store.session(learner)
    leaked = (
        'Try this exercise.\n\nPresented activities:\n[{"id":"old","kind":"exercise"}]'
    )
    with store.transaction():
        store.save_turn(context(store, learner, session), leaked, [])

    assert store.conversation(learner, session)[-1]["content"] == leaked
    assert store.model_history(learner, session)[-1]["content"] == "Try this exercise."
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
    seeded = seed_graph(store, store.learning_scope(learner, session), session)
    ids = {skill["key"]: skill["id"] for skill in seeded["topic"]["skills"]}
    target = ids["german.accusative-indefinite-articles"]
    provider = MockProvider(
        [
            call(
                "present_exercise",
                exercise={
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
                },
            ),
            say(
                "Use einen for a masculine direct object. "
                "Now complete the exercise below."
            ),
        ]
    )
    tutor = Tutor(config, store, Telemetry(enabled=False), provider.model)
    reply = asyncio.run(tutor.respond(learner, session, "Teach me now"))
    assert reply.turn_id == store.conversation(learner, session)[-1]["turn_id"]
    assert reply.text.startswith("Use einen for a masculine direct object.")
    assert [item["kind"] for item in reply.activities] == ["exercise"]
    assert store.conversation(learner, session)[-1]["activities"] == reply.activities
    asyncio.run(tutor.close())

    exercise_id = reply.activities[0]["id"]
    answer_provider = MockProvider(
        [
            call(
                "assess_attempt",
                assessment={
                    "exercise_id": exercise_id,
                    "feedback": "Use einen with masculine Kaffee.",
                    "observations": [
                        {
                            "skill_id": target,
                            "outcome": "needs_work",
                            "rationale": "Used ein instead of einen.",
                        }
                    ],
                },
            ),
            say("Use einen with masculine Kaffee. Try again."),
        ]
    )
    answer_tutor = Tutor(config, store, Telemetry(enabled=False), answer_provider.model)
    answer = asyncio.run(
        answer_tutor.respond(learner, session, "Ich nehme ein Kaffee.", exercise_id)
    )
    assert answer.assessments[0]["exercise_id"] == exercise_id
    assert (
        store.db.execute(
            "SELECT level FROM assistance WHERE exercise_id=?", (exercise_id,)
        ).fetchone()[0]
        == "explanation"
    )
    assert "Selected exercise answer" in json.dumps(answer_provider.requests[0])
    asyncio.run(answer_tutor.close())

    failed_config = settings(tmp_path, max_turns=1)
    failed_provider = MockProvider(
        [
            call(
                "present_exercise",
                exercise={
                    "title": "Rolled back",
                    "task": "This must not survive.",
                    "context": "Rollback test",
                    "scaffolding": "none",
                    "skills": [
                        {
                            "skill_id": target,
                            "role": "target",
                            "success_criterion": "Complete the task.",
                        }
                    ],
                    "source_ids": [],
                },
            )
        ]
    )
    failed_tutor = Tutor(
        failed_config, store, Telemetry(enabled=False), failed_provider.model
    )
    before = store.db.execute("SELECT count(*) FROM exercises").fetchone()[0]
    with pytest.raises(Exception, match="Max turns"):
        asyncio.run(failed_tutor.respond(learner, session, "Fail this turn"))
    assert store.db.execute("SELECT count(*) FROM exercises").fetchone()[0] == before
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
                    "key": "german.accusative-indefinite-articles",
                    "name": "German masculine accusative einen",
                    "definition": "Use einen for a masculine singular direct object.",
                    "success_criteria": [
                        "Use einen with masculine singular direct objects."
                    ],
                },
                {
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
                    "new_skill_ref": "german.accusative-indefinite-articles",
                    "relation": "split",
                },
                {
                    "old_skill_id": old_id,
                    "new_skill_ref": "german.accusative-nonmasculine-indefinite-articles",
                    "relation": "split",
                },
            ],
            [
                {
                    "old_skill_id": old_id,
                    "replacement_ref": "german.accusative-indefinite-articles",
                },
                {
                    "old_skill_id": old_id,
                    "replacement_ref": "german.accusative-nonmasculine-indefinite-articles",
                },
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


def test_exercise_status_is_session_scoped_without_an_attempt(tmp_path):
    store = Store(tmp_path / "exercise-status.db")
    learner = store.owner
    session = store.session(learner)
    scope = store.learning_scope(learner, session)
    seed_graph(store, scope, session)
    focus = store.focus(scope)
    assert focus is not None
    skill_id = focus["skills"][0]["id"]
    teach = context(store, scope, session, "teach", "Teach")
    with store.transaction():
        exercise = store.present_exercise(
            teach,
            {
                "title": "Practice",
                "task": "Say it",
                "context": "A cafe",
                "scaffolding": "none",
                "skills": [
                    {
                        "skill_id": skill_id,
                        "role": "target",
                        "success_criterion": "Say it correctly",
                    }
                ],
                "source_ids": [],
            },
        )
        store.save_turn(teach, "Explanation", [])
    status = store.exercise_status(learner, session, exercise["id"])
    assert status["assessments"] == []
    assert not status["assisted"]
    assert not status["completed"]
    other = store.session(learner)
    with pytest.raises(ValueError):
        store.exercise_status(learner, other, exercise["id"])
    store.close()


@pytest.mark.parametrize("help_first", [False, True])
def test_exercise_status_rebuilds_success_after_reload(tmp_path, help_first):
    path = tmp_path / "exercise-reload.db"
    store = Store(path)
    learner = store.owner
    session = store.session(learner)
    scope = store.learning_scope(learner, session)
    seed_graph(store, scope, session)
    focus = store.focus(scope)
    assert focus is not None
    skill_id = focus["skills"][0]["id"]
    teach = context(store, scope, session, "teach", "Teach")
    with store.transaction():
        exercise = store.present_exercise(
            teach,
            {
                "title": "Practice",
                "task": "Say it",
                "context": "A cafe",
                "scaffolding": "none",
                "skills": [
                    {
                        "skill_id": skill_id,
                        "role": "target",
                        "success_criterion": "Say it correctly",
                    }
                ],
                "source_ids": [],
            },
        )
        store.save_turn(teach, "Explanation", [])
    if help_first:
        with store.transaction():
            store.record_assistance(
                context(store, scope, session, "help", "Explain this"),
                exercise["id"],
                [skill_id],
                "explanation",
                "Explained the form.",
            )
    attempt = context(store, scope, session, "answer", "  exact learner text  ")
    with store.transaction():
        result = store.assess_attempt(
            attempt,
            exercise["id"],
            "Correct",
            [{"skill_id": skill_id, "outcome": "success", "rationale": "Correct form"}],
        )
        store.save_turn(attempt, "Correct", [])
    assert result["learner_response"] == "  exact learner text  "
    assert result["observations"][0]["independent_success"] is not help_first
    store.close()
    reopened = Store(path)
    status = reopened.exercise_status(learner, session, exercise["id"])
    assert status["completed"]
    assert status["assisted"] is help_first
    assert status["latest_assessment"]["learner_response"] == "  exact learner text  "
    assert "exact learner text" in json.dumps(reopened.model_history(learner, session))
    reopened.close()


@pytest.mark.parametrize(
    ("outcomes", "completed"),
    [
        ({2: "success"}, False),
        ({0: "success"}, False),
        ({0: "success", 1: "uncertain"}, False),
        ({0: "success", 1: "needs_work"}, False),
        ({0: "success", 1: "success"}, True),
        ({0: "success", 1: "success", 2: "needs_work"}, False),
        ({0: "success", 1: "success", 2: "success"}, True),
    ],
)
def test_completion_requires_all_targets_in_latest_attempt(
    tmp_path, outcomes, completed
):
    store = Store(tmp_path / "completion.db")
    learner = store.owner
    session = store.session(learner)
    scope = store.learning_scope(learner, session)
    seeded = seed_graph(store, scope, session)
    skills = seeded["topic"]["skills"]
    teach = context(store, scope, session, "teach-targets", "Practice")
    with store.transaction():
        store.set_focus(
            teach,
            seeded["topic"]["id"],
            [skill["id"] for skill in skills[:2]],
            [skills[2]["id"]],
            "Practice two target skills together",
        )
        exercise = store.present_exercise(
            teach,
            {
                "title": "Two targets",
                "task": "Use both patterns",
                "context": "Practice",
                "scaffolding": "none",
                "source_ids": [],
                "skills": [
                    {
                        "skill_id": skill["id"],
                        "role": "target" if index < 2 else "supporting",
                        "success_criterion": "Use the pattern correctly",
                    }
                    for index, skill in enumerate(skills)
                ],
            },
        )
        store.save_turn(teach, "Try both patterns", [])
    assert not store.exercise_status(learner, session, exercise["id"])["completed"]
    # Earlier success on one target cannot fill an omission in the latest attempt.
    for turn, observations in enumerate(({1: "success"}, outcomes)):
        attempt = context(store, scope, session, f"attempt-{turn}", "Answer")
        with store.transaction():
            store.assess_attempt(
                attempt,
                exercise["id"],
                "Feedback",
                [
                    {
                        "skill_id": skills[index]["id"],
                        "outcome": outcome,
                        "rationale": "Observed",
                    }
                    for index, outcome in observations.items()
                ],
            )
            store.save_turn(attempt, "Feedback", [])
    assert (
        store.exercise_status(learner, session, exercise["id"])["completed"]
        is completed
    )
    store.close()
