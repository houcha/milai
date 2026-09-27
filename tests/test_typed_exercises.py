"""Typed contracts and scores; mocked assessments do not establish language quality."""

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from milai.cli import collect_typed_answers, print_lesson
from milai.exercises import (
    ExerciseContract,
    parse_answers,
    serialize_answers,
)
from milai.store import SCHEMA_VERSION, InvalidReference, Store
from milai.tools import Context, Exercise, _LessonPlan
from milai.tutor import LessonTurnOutput
from tests.test_generation import draft
from tests.test_lesson_conversations import _seed_lesson, _tutor


def contract(kind="translate"):
    item = {
        "text": "You have",
        "context": "Addressing several people informally",
        "references": ["ihr habt"],
    }
    content = {"type": kind, "items": [item]}
    if kind in {"translate", "short_response"}:
        content["language"] = None
    if kind in {"choose_form", "complete_sentence"}:
        item.update(text="Ihr {{blank}} Zeit.", context="")
        if kind == "choose_form":
            item.pop("references")
            item.update(options=["hat", "habt", "haben"], correct_option=2)
        else:
            item["references"] = ["habt"]
    elif kind == "transform":
        content["target_form"] = "the subject ihr"
        item.update(text="Wir haben Zeit.", context="", references=["Ihr habt Zeit."])
    elif kind == "short_response":
        content.update(
            response_scope="one sentence", focus="a present-tense form of haben"
        )
        item.update(
            text="A possession you and a friend share.",
            context="",
            references=["Wir haben ein Auto."],
        )
    return {"version": 1, "content": content}


@pytest.fixture
def learning(tmp_path):
    store = Store(tmp_path / "typed.db")
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    lesson = _seed_lesson(store, session, "seed", "haben", "Present-tense forms")
    yield store, session, scope, lesson
    store.close()


def add(learning, kind="translate", payload=None):
    store, session, scope, lesson = learning
    count = store.db.execute("SELECT count(*) FROM exercises").fetchone()[0]
    ctx = Context(
        store,
        scope,
        session,
        f"practice-{count}",
        "More practice",
        "test",
        lesson_id=lesson["id"],
    )
    value = {
        "contract": payload or contract(kind),
        "scaffolding": "none",
        "source_ids": [],
        "skills": [
            {
                "skill_id": lesson["focus_skill_id"],
                "role": "target",
                "success_criterion": "Use the form",
            }
        ],
    }
    saved_choice = kind == "choose_form" and payload is None
    if saved_choice:
        value["contract"] = contract("complete_sentence")
        value["scaffolding"] = "cues"
    with store.transaction():
        exercise = store.present_exercise(ctx, value)
        if saved_choice:
            # Seed historical data directly: production creation rejects choices.
            saved = ExerciseContract.model_validate(contract("choose_form"))
            store.db.execute(
                "UPDATE exercises SET contract=?, title=?, task=? WHERE id=?",
                (
                    saved.model_dump_json(),
                    "Choose a form",
                    saved.task(),
                    exercise["id"],
                ),
            )
            exercise = store.exercise(scope, exercise["id"])
        store.save_turn(ctx, "Practice", [])
    return exercise


def assess(learning, exercise, answer, results=None, **kwargs):
    store, session, scope, lesson = learning
    ctx = Context(
        store,
        scope,
        session,
        f"answer-{exercise['id']}",
        answer,
        "test",
        lesson_id=lesson["id"],
        selected_exercise_id=exercise["id"],
        action="answer",
    )
    with store.transaction():
        result = store.assess_attempt(
            ctx,
            exercise["id"],
            "",
            [
                {
                    "skill_id": lesson["focus_skill_id"],
                    "outcome": "success",
                    "issue_severity": "none",
                    "rationale": "The target form is correct.",
                }
            ],
            item_results=results
            if results is not None
            else [{"item_number": 1, "correct": True, "feedback": ""}],
            **kwargs,
        )
        store.save_turn(ctx, "Assessed", [])
    return result


@pytest.mark.parametrize(
    "kind,answer",
    [
        ("choose_form", "2"),
        ("complete_sentence", "habt"),
        ("translate", "ihr habt"),
        ("transform", "Ihr habt Zeit."),
        ("short_response", "Wir haben ein Fahrrad."),
    ],
)
def test_types_persist_grade_and_keep_keys_private(learning, kind, answer, capsys):
    store, session, scope, lesson = learning
    exercise = add(learning, kind)
    encoded = serialize_answers([answer])
    result = assess(learning, exercise, encoded)
    assert result["score"] == {"correct": 1, "total": 1}
    assert result["observations"][0]["independent_success"] is (kind != "choose_form")
    if kind == "choose_form":
        assert exercise["scaffolding"] == "cues"
    with store.read_snapshot() as reopened:
        public = reopened.lesson_detail(store.owner, session, lesson["id"])
        assert public["exercises"][-1] == exercise
        status = reopened.exercise_status(store.owner, session, exercise["id"])
        assert status["first_assessment"]["item_results"] == result["item_results"]
        assert public["practice_results"][-1]["scoring"] == "items"
        assert public["practice_results"][-1]["percentage"] == 100
        print_lesson(public)
    assert exercise["format"]["instruction"] in capsys.readouterr().out
    for public in (
        exercise,
        store.snapshot(scope),
        store.conversation(store.owner, session, lesson_id=lesson["id"]),
    ):
        assert '"references"' not in json.dumps(public)
        assert '"correct_option"' not in json.dumps(public)
    with pytest.raises(ValueError, match="already been submitted"):
        assess(learning, exercise, encoded)


def test_translation_requires_no_repeated_source_and_has_no_extra_points(learning):
    exercise = add(learning)
    assert exercise["format"]["instruction"] == "Translate into German."
    assert exercise["format"]["items"][0]["text"] == "You have"
    result = assess(learning, exercise, serialize_answers(["ihr habt"]))
    assert result["score"] == {"correct": 1, "total": 1}


@pytest.mark.parametrize(
    "results,kwargs",
    [
        ([], {}),
        ([{"item_number": 2, "correct": True, "feedback": ""}], {}),
        ([{"item_number": 1, "correct": True, "feedback": ""}] * 2, {}),
        ([{"item_number": 1, "correct": True, "feedback": "Great!"}], {}),
        ([{"item_number": 1, "correct": False, "feedback": ""}], {}),
        (
            [{"item_number": 1, "correct": True, "feedback": ""}],
            {"score": {"correct": 1, "total": 2}},
        ),
        (
            [{"item_number": 1, "correct": True, "feedback": ""}],
            {"blank_results": [{"blank_number": 1, "correct": True, "feedback": ""}]},
        ),
    ],
)
def test_invalid_assessments_cannot_consume_submission(learning, results, kwargs):
    store, session, _, _ = learning
    exercise = add(learning)
    before = list(store.db.iterdump())
    with pytest.raises(ValueError):
        assess(learning, exercise, serialize_answers(["ihr habt"]), results, **kwargs)
    assert list(store.db.iterdump()) == before
    assert not store.exercise_status(store.owner, session, exercise["id"])["submitted"]


def test_choice_key_and_missing_answers_are_enforced(learning):
    exercise = add(learning, "choose_form")
    with pytest.raises(ValueError, match="saved option key"):
        assess(learning, exercise, serialize_answers(["1"]))
    with pytest.raises(ValueError, match="missing answer"):
        assess(learning, exercise, serialize_answers([""]))
    result = assess(
        learning,
        exercise,
        serialize_answers(["1"]),
        [{"item_number": 1, "correct": False, "feedback": "Use habt with ihr."}],
    )
    assert result["score"] == {"correct": 0, "total": 1}


def test_multi_item_scores_are_calculated_from_results(learning):
    value = contract()
    value["content"]["items"].append(
        {"text": "She has", "context": "", "references": ["sie hat"]}
    )
    exercise = add(learning, payload=value)
    results = [
        {"item_number": 1, "correct": True, "feedback": ""},
        {"item_number": 2, "correct": False, "feedback": "Use sie hat."},
    ]
    result = assess(learning, exercise, serialize_answers(["ihr habt", ""]), results)
    assert result["score"] == {"correct": 1, "total": 2}


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(version=2),
        lambda value: value["content"].update(instructions="Also translate back"),
        lambda value: value["content"].update(items=[]),
        lambda value: value["content"]["items"][0].update(text="{{blank}} {{blank}}"),
        lambda value: value["content"]["items"][0].update(text="{{blank:1}}"),
        lambda value: value["content"]["items"][0].update(correct_option=5),
        lambda value: value["content"]["items"][0].update(options=["hat", "hat"]),
    ],
)
def test_malformed_contracts_rejected_before_writes(learning, change):
    store, _, _, _ = learning
    value = contract("choose_form")
    change(value)
    with pytest.raises(ValueError):
        ExerciseContract.model_validate(value)
    before = list(store.db.iterdump())
    with pytest.raises(ValueError):
        add(learning, payload=value)
    assert list(store.db.iterdump()) == before


def test_new_schema_rejects_freeform_tasks_and_choices(learning):
    with pytest.raises(ValueError):
        Exercise.model_validate(
            {
                "title": "Old",
                "task": "Also explain",
                "context": "",
                "scaffolding": "none",
                "skills": [],
            }
        )
    value = draft()
    for item in value["exercises"]:
        item["contract"] = contract("choose_form")
        item["scaffolding"] = "none"
    with pytest.raises(ValueError):
        _LessonPlan.model_validate(value)
    practice = {
        "contract": contract(),
        "scaffolding": "none",
        "skills": [
            {"skill_id": "skill", "role": "target", "success_criterion": "Use the form"}
        ],
    }
    Exercise.model_validate(practice)
    practice["contract"] = contract("choose_form")
    with pytest.raises(ValueError):
        Exercise.model_validate(practice)
    with pytest.raises(ValueError):
        add(learning, payload=contract("choose_form"))
    for model in (Exercise, _LessonPlan):
        schema = json.dumps(model.model_json_schema())
        assert "choose_form" not in schema
        assert "ChoiceItem" not in schema


@pytest.mark.parametrize("answer", ["x" * 201, "first\nsecond"])
def test_completion_references_must_fit_the_answer_control(answer):
    value = contract("complete_sentence")
    value["content"]["items"][0]["references"] = [answer]
    with pytest.raises(ValueError, match="Reference fills"):
        ExerciseContract.model_validate(value)


def test_private_assessment_context_and_invalid_answers(learning, monkeypatch):
    store, session, scope, lesson = learning
    exercise = add(learning)
    calls = []

    async def run(agent, messages, *, context, **kwargs):
        calls.append(agent.instructions)
        if context.action == "answer":
            result = store.assess_attempt(
                context,
                exercise["id"],
                "",
                [
                    {
                        "skill_id": lesson["focus_skill_id"],
                        "outcome": "success",
                        "issue_severity": "none",
                        "rationale": "Correct",
                    }
                ],
                item_results=[{"item_number": 1, "correct": True, "feedback": ""}],
            )
            context.assessments.append(result)
        return SimpleNamespace(
            final_output=LessonTurnOutput(reply="Done", summary="Reviewed the target."),
            to_input_list=lambda: messages,
        )

    monkeypatch.setattr("milai.tutor.Runner.run", run)
    tutor = _tutor(store)
    asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "Help",
            lesson_id=lesson["id"],
            exercise_id=exercise["id"],
        )
    )
    assert '"assessment_contract"' not in calls[-1]
    assert '"references"' not in calls[-1]
    asyncio.run(
        tutor.respond(
            store.owner,
            session,
            "ihr habt",
            lesson_id=lesson["id"],
            exercise_id=exercise["id"],
            action="answer",
        )
    )
    assert '"assessment_contract"' in calls[-1]
    assert '"references": ["ihr habt"]' in calls[-1]
    other_session = store.session(store.owner)
    other_scope = store.learning_scope(store.owner, other_session)
    with pytest.raises(InvalidReference):
        store.exercise_contract(other_scope, exercise["id"])
    asyncio.run(tutor.close())


def test_answer_mapping_preserves_multiline_and_rejects_invalid_choices():
    public = ExerciseContract.model_validate(contract()).resolved("German").public()
    public["items"] *= 2
    values = ['ihr habt\nItem 2: "quoted"\u2028kept in this answer', "sie hat"]
    assert parse_answers(serialize_answers(values), public) == values
    with pytest.raises(ValueError):
        parse_answers("unmapped answers", public)
    with pytest.raises(ValueError):
        parse_answers('Item 2: "x"\nItem 1: "y"', public)
    choice = ExerciseContract.model_validate(contract("choose_form")).public()
    with pytest.raises(ValueError, match="available option"):
        parse_answers("7", choice)


def test_invalid_typed_submission_is_rejected_before_model_execution(
    learning, monkeypatch
):
    store, session, _, lesson = learning
    exercise = add(learning, "choose_form")

    async def unexpected(*args, **kwargs):
        pytest.fail("Invalid option reached the model")

    monkeypatch.setattr("milai.tutor.Runner.run", unexpected)
    tutor = _tutor(store)
    before = list(store.db.iterdump())
    with pytest.raises(ValueError, match="available option"):
        asyncio.run(
            tutor.respond(
                store.owner,
                session,
                "9",
                lesson_id=lesson["id"],
                exercise_id=exercise["id"],
                action="answer",
            )
        )
    assert list(store.db.iterdump()) == before
    asyncio.run(tutor.close())


def test_failed_typed_turn_rolls_back_assessment_and_can_retry(learning, monkeypatch):
    store, session, _, lesson = learning
    exercise = add(learning)

    async def fail(agent, messages, *, context, **kwargs):
        store.assess_attempt(
            context,
            exercise["id"],
            "",
            [
                {
                    "skill_id": lesson["focus_skill_id"],
                    "outcome": "success",
                    "issue_severity": "none",
                    "rationale": "Correct",
                }
            ],
            item_results=[{"item_number": 1, "correct": True, "feedback": ""}],
        )
        raise RuntimeError("Failure after assessment")

    monkeypatch.setattr("milai.tutor.Runner.run", fail)
    tutor = _tutor(store)
    before = list(store.db.iterdump())
    with pytest.raises(RuntimeError, match="Failure after assessment"):
        asyncio.run(
            tutor.respond(
                store.owner,
                session,
                "ihr habt",
                lesson_id=lesson["id"],
                exercise_id=exercise["id"],
                action="answer",
            )
        )
    assert list(store.db.iterdump()) == before
    assert not store.exercise_status(store.owner, session, exercise["id"])["submitted"]
    assert (
        assess(learning, exercise, serialize_answers(["ihr habt"]))["score"]["correct"]
        == 1
    )
    asyncio.run(tutor.close())


def test_schema_eight_upgrade_preserves_legacy_content_and_scores(learning):
    store, session, scope, lesson = learning
    before = store.lesson_detail(store.owner, session, lesson["id"])
    store.db.execute("ALTER TABLE exercises DROP COLUMN contract")
    store.db.execute("ALTER TABLE attempts DROP COLUMN item_results")
    store.db.execute("ALTER TABLE turns DROP COLUMN completion_summary")
    store.db.execute("UPDATE metadata SET value='8' WHERE key='schema_version'")
    reopened = Store(store.path)
    try:
        assert reopened.lesson_detail(store.owner, session, lesson["id"]) == before
        assert (
            reopened.db.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()[0]
            == SCHEMA_VERSION
        )
    finally:
        reopened.close()


def test_terminal_collects_numbered_choices_and_preserves_answers(monkeypatch, capsys):
    public = ExerciseContract.model_validate(contract("choose_form")).public()
    public["items"] = [*public["items"], copy.deepcopy(public["items"][0])]
    inputs = iter(["9", "2", "3"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    response = asyncio.run(collect_typed_answers({"format": public}))
    assert parse_answers(response, public) == ["2", "3"]
    output = capsys.readouterr().out
    assert "Choose the correct form." in output
    assert "available option" in output
