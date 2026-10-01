"""Paid, labelled synthetic reviewer comparison; never reads personal learning data."""

import argparse
import asyncio
import hashlib
import json
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from milai.config import Settings, provider
from milai.exercises import serialize_answers
from milai.observability import Telemetry
from milai.reviewer import review, review_input, reviewer_prompt
from milai.store import Store
from milai.tools import AttemptAssessment, Context, persist_assessment


@dataclass(frozen=True)
class Case:
    name: str
    language: str
    criterion: str
    content: dict | None
    answers: list[str]
    correct: list[bool]
    outcome: str = "success"
    severity: str = "none"
    task: str = ""
    assisted: bool = False
    complete_set: bool = False
    legacy_total: int | None = None


def text_item(text, reference, context=""):
    return {"text": text, "context": context, "references": [reference]}


def cases() -> list[Case]:
    haben = "Use a present-tense form of haben agreeing with the subject."
    questions = "Put the finite verb first in a neutral German yes/no question."
    past = "Form the English simple past of regular verbs with -ed."
    return [
        Case(
            "informal_plural",
            "German",
            haben,
            {
                "type": "translate",
                "language": None,
                "items": [
                    text_item("You have", "ihr habt", "Several people, informal")
                ],
            },
            ["ihr habt"],
            [True],
        ),
        Case(
            "valid_alternative",
            "German",
            haben,
            {
                "type": "translate",
                "language": None,
                "items": [text_item("We have time.", "Wir haben Zeit.", "time = Zeit")],
            },
            ["Zeit haben wir."],
            [True],
        ),
        Case(
            "completion",
            "German",
            haben,
            {
                "type": "complete_sentence",
                "items": [text_item("Ihr {{blank}} Zeit.", "habt")],
            },
            ["habt"],
            [True],
        ),
        Case(
            "transformation",
            "German",
            haben,
            {
                "type": "transform",
                "target_form": "the subject ihr",
                "items": [text_item("Wir haben Zeit.", "Ihr habt Zeit.")],
            },
            ["Ihr habt Zeit."],
            [True],
        ),
        Case(
            "open_vocabulary_gap",
            "German",
            haben,
            {
                "type": "short_response",
                "language": None,
                "response_scope": "one sentence",
                "focus": "a present-tense form of haben",
                "items": [
                    text_item(
                        "A possession you and a friend share.", "Wir haben ein Auto."
                    )
                ],
            },
            ["Wir haben ein ... (I don't know the word for car)."],
            [True],
        ),
        Case(
            "incidental_vocabulary",
            "German",
            questions,
            {
                "type": "translate",
                "language": None,
                "items": [
                    text_item(
                        "Are you tired?", "Bist du müde?", "One person, informal"
                    ),
                    text_item("Does he have time?", "Hat er Zeit?"),
                    text_item("Are we ready?", "Sind wir bereit?"),
                ],
            },
            [
                "Bist du mude?",
                "Hat er ... (I don't know the word for time)?",
                "Sind wir ...? (same)",
            ],
            [True, True, True],
        ),
        Case(
            "target_grammar_error",
            "German",
            questions,
            {
                "type": "translate",
                "language": None,
                "items": [
                    text_item(
                        "Are you tired?",
                        "Bist du müde?",
                        "One person, informal; tired = müde",
                    )
                ],
            },
            ["Du bist müde?"],
            [False],
            "needs_work",
            "substantial",
        ),
        Case(
            "minor_slip",
            "English",
            past,
            {
                "type": "complete_sentence",
                "items": [
                    text_item("Yesterday I {{blank}} to school. (walk)", "walked"),
                    text_item("Last week we {{blank}} our aunt. (visit)", "visited"),
                    text_item("Yesterday they {{blank}} football. (play)", "played"),
                ],
            },
            ["walked", "visited", "play"],
            [True, True, False],
            severity="minor",
            complete_set=True,
        ),
        Case(
            "empty_response",
            "German",
            haben,
            {
                "type": "complete_sentence",
                "items": [text_item("Ihr {{blank}} Zeit.", "habt")],
            },
            [""],
            [False],
            "uncertain",
            "unclear",
        ),
        Case(
            "assisted_success",
            "English",
            past,
            {
                "type": "transform",
                "target_form": "the simple past",
                "items": [text_item("We visit our aunt.", "We visited our aunt.")],
            },
            ["We visited our aunt."],
            [True],
            assisted=True,
        ),
        Case(
            "legacy_blanks",
            "English",
            past,
            None,
            ["walked", "visited", "play"],
            [True, True, False],
            severity="minor",
            task=(
                "Fill in the regular past forms.\n1. walk → {{blank}}\n"
                "2. visit → {{blank}}\n3. play → {{blank}}"
            ),
        ),
        Case(
            "legacy_components",
            "German",
            "Recall the German pronouns ich and du and their English meanings.",
            None,
            ["ich = I; du (I forgot its meaning)"],
            [True, True, True, False],
            severity="minor",
            task=(
                "Give each German subject pronoun and its English meaning: "
                "1. first person singular; 2. second person singular informal."
            ),
            legacy_total=4,
        ),
    ]


def fixture(store: Store, case: Case) -> Context:
    session = store.session(store.owner)
    scope = store.learning_scope(store.owner, session)
    ctx = Context(store, scope, session, "lesson", "Teach this skill", "evaluation")
    exercise = {
        "scaffolding": "none",
        "source_ids": [],
        "skills": [
            {
                "skill_id": "@focus",
                "role": "target",
                "success_criterion": case.criterion,
            }
        ],
    }
    if case.content:
        exercise["contract"] = {"version": 1, "content": case.content}
    else:
        exercise.update(title="Saved legacy practice", task=case.task, context="")
    with store.transaction():
        store.record_facts(
            ctx,
            [
                {
                    "field": "target_language",
                    "value": case.language,
                    "learner_quote": case.language,
                }
            ],
        )
        lesson = store.start_lesson(
            ctx,
            case.language,
            None,
            {
                "key": case.name,
                "name": case.name.replace("_", " "),
                "definition": case.criterion,
                "success_criteria": [case.criterion],
            },
            [],
            "Synthetic reviewer comparison",
            document={
                "objective": case.criterion,
                "sections": [
                    {"id": "pattern", "title": "Pattern", "markdown": case.criterion}
                ],
                "worked_examples": [
                    {
                        "id": "example",
                        "title": "Example",
                        "markdown": "Synthetic teaching example.",
                    }
                ],
                "recap": case.criterion,
            },
            exercises=[exercise, exercise, exercise],
        )
        store.save_turn(ctx, "Practice", [])
    exercises = store.lesson_detail(store.owner, session, lesson["id"])["exercises"]
    selected = exercises[0]
    message = (
        serialize_answers(case.answers)
        if case.content
        else "\n".join(
            f"Blank {i}: {answer}" for i, answer in enumerate(case.answers, 1)
        )
        if "{{blank}}" in case.task
        else case.answers[0]
    )
    ctx = Context(
        store,
        scope,
        session,
        "answer",
        message,
        "evaluation",
        lesson_id=lesson["id"],
        selected_exercise_id=selected["id"],
        action="answer",
    )
    if case.assisted:
        helped = Context(
            store, scope, session, "help", "Help", "evaluation", lesson_id=lesson["id"]
        )
        with store.transaction():
            store.record_assistance(
                helped,
                selected["id"],
                [lesson["focus_skill_id"]],
                "explanation",
                "Use -ed for a regular past form.",
            )
            store.save_turn(helped, "Hint", [])
    if case.complete_set:
        for i, previous in enumerate(exercises[1:], 1):
            prior = Context(
                store,
                scope,
                session,
                f"prior-{i}",
                serialize_answers(["walked", "visited", "played"]),
                "evaluation",
                lesson_id=lesson["id"],
                selected_exercise_id=previous["id"],
                action="answer",
            )
            assessment = AttemptAssessment.model_validate(
                {
                    "exercise_id": previous["id"],
                    "feedback": "",
                    "item_results": [
                        {"item_number": j, "correct": True, "feedback": ""}
                        for j in range(1, 4)
                    ],
                    "observations": [
                        {
                            "skill_id": lesson["focus_skill_id"],
                            "outcome": "success",
                            "issue_severity": "none",
                            "rationale": "Correct regular past forms.",
                        }
                    ],
                }
            )
            with store.transaction():
                persist_assessment(prior, assessment)
                store.save_turn(prior, "Correct", [])
    return ctx


class _Rollback(Exception):
    """Validate one model's output without changing the other model's context."""


def check(case: Case, ctx: Context, output) -> list[str]:
    if ctx.lesson_id is None:
        raise ValueError("Evaluation requires a lesson")
    problems = []
    try:
        with ctx.store.transaction():
            result = persist_assessment(ctx, output.assessment)
            ctx.store.save_turn(
                ctx, output.reply, [], completion_summary=output.completion_summary
            )
            ctx.store.save_discussion_summary(ctx, output.summary)
            expected_score = {
                "correct": sum(case.correct),
                "total": case.legacy_total or len(case.correct),
            }
            if result["score"] != expected_score:
                problems.append("score")
            fields = result["item_results"] or result["blank_results"]
            if fields and [item["correct"] for item in fields] != case.correct:
                problems.append("correctness_flags")
            observations = result["observations"]
            target = next(
                (
                    obs
                    for obs in observations
                    if obs["skill_id"]
                    == ctx.store.lesson(ctx.learner, ctx.lesson_id)["focus_skill_id"]
                ),
                None,
            )
            if target is None or (target["outcome"], target["issue_severity"]) != (
                case.outcome,
                case.severity,
            ):
                problems.append("target_evidence")
            if target and target["independent_success"] != (
                case.outcome == "success" and not case.assisted
            ):
                problems.append("independence")
            if case.complete_set and not output.completion_summary:
                problems.append("completion_recap")
            if not case.complete_set and output.completion_summary is not None:
                problems.append("premature_recap")
            raise _Rollback
    except _Rollback:
        pass
    except (ValueError, PermissionError) as exc:
        problems.append(f"storage_validation: {exc}")
    finally:
        ctx.assessments.clear()
        ctx.event_ids.clear()
    return problems


async def evaluate(settings: Settings, report_path: Path) -> dict:
    # Disable all remote trace exporters; the saved report contains synthetic data.
    Telemetry(enabled=False)
    luna = provider(settings, model_name=settings.review_model)
    sol = provider(settings, model_name=settings.model, client=luna._client)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "prompt_hash": hashlib.sha256(reviewer_prompt().encode()).hexdigest()[:16],
        "reasoning_effort": settings.review_reasoning_effort,
        "service_tier": "default",
        "max_output_tokens": settings.review_max_output_tokens,
        "models": [settings.review_model, settings.model],
        "label_source": (
            "Predefined expected correctness and evidence; "
            "Sol is a comparator, not ground truth."
        ),
        "results": [],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="milai-review-") as directory:
            for i, case in enumerate(cases()):
                store = Store(Path(directory) / f"case-{i}.db")
                try:
                    ctx = fixture(store, case)
                    data = review_input(ctx)
                    for name, model in zip(report["models"], (luna, sol), strict=True):
                        started = time.perf_counter()
                        entry = {
                            "case": case.name,
                            "model": name,
                            "input": data,
                            "expected": {
                                "correct": case.correct,
                                "outcome": case.outcome,
                                "severity": case.severity,
                                "assisted": case.assisted,
                            },
                        }
                        try:
                            output, usage = await review(ctx, settings, model)
                            entry.update(
                                output=output.model_dump(),
                                usage=TypeAdapter(type(usage)).dump_python(
                                    usage, mode="json"
                                ),
                                problems=check(case, ctx, output),
                            )
                        except Exception as exc:
                            entry.update(
                                problems=[type(exc).__name__], error=str(exc)[:500]
                            )
                        entry["seconds"] = round(time.perf_counter() - started, 3)
                        entry["passed"] = not entry["problems"]
                        report["results"].append(entry)
                        report_path.write_text(
                            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
                        )
                        print(
                            f"{case.name}: {name}: "
                            f"{'passed' if entry['passed'] else entry['problems']} "
                            f"({entry['seconds']}s)",
                            flush=True,
                        )
                finally:
                    store.close()
    finally:
        await luna._client.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report", type=Path, default=Path("docs/reviewer-comparison.json")
    )
    args = parser.parse_args()
    report = asyncio.run(evaluate(Settings.load(), args.report))
    if any(not result["passed"] for result in report["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
