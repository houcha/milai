"""Live synthetic lesson journey; writes a reviewable report, never a mock."""

import argparse
import asyncio
import json
import re
import tempfile
from dataclasses import replace
from pathlib import Path

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import Store
from milai.tutor import Tutor

START = (
    "I speak Spanish and am learning English at about A2 level. I want to describe "
    "simple trips. Please explain in simple English, use short original examples, "
    "and create a complete lesson on one useful past-tense skill with practice. "
    "I prefer brief explanations before attempting exercises. "
    "Include an independent exercise where I write a short trip account."
)

REGULAR_TRIP_SENTENCES = [
    "Last Saturday, I visited a town and walked to a museum.",
    "That afternoon, I explored the square and photographed a bridge.",
    "That evening, I tasted local food and returned home.",
    "Last Sunday, I planned another visit and shared my photos.",
    "Last Monday, I described the trip and thanked my friend.",
    "Yesterday, I organized the pictures and remembered the day.",
]
MIXED_TRIP_SENTENCES = [
    "Last Saturday, I went to a town and visited a museum.",
    "That afternoon, I saw a bridge and walked beside the river.",
    "That evening, I ate local food and explored the square.",
    "Later that night, I took a photo and returned home.",
    "Last Sunday, I met a friend and described the trip.",
    "Yesterday, I wrote a postcard and shared the photos.",
]


def choose_trip_exercise(exercises: list[dict]) -> dict:
    """Choose an open writing task this synthetic answer can actually address."""
    for exercise in exercises:
        task = exercise["task"].lower()
        if (
            exercise.get("scaffolding") == "none"
            and any(word in task for word in ("write", "describe", "tell"))
            and any(word in task for word in ("trip", "journey", "travel", "visit"))
            and not re.search(r"\b(?:blank|blanks|parentheses|complete)\b", task)
        ):
            return exercise
    raise RuntimeError("Generated lesson has no compatible trip-writing exercise")


def trip_answer_for(exercise: dict) -> str:
    """Meet the selected open-writing task's sentence and verb requirements."""
    task = exercise["task"].lower()
    exact_count = re.search(
        r"\b(?:write|compose)\s+(three|four|five|six|[3-6])\s+", task
    )
    counts = {"three": 3, "four": 4, "five": 5, "six": 6}
    if exact_count:
        count = counts.get(
            exact_count[1], int(exact_count[1]) if exact_count[1].isdigit() else 6
        )
    elif re.search(r"\b(?:5|five)\s*[–-]\s*(?:7|seven)\s+sentences\b", task):
        count = 6
    else:
        count = 6
    sentences = MIXED_TRIP_SENTENCES if "irregular" in task else REGULAR_TRIP_SENTENCES
    return " ".join(sentences[:count])


def attempt_count(store: Store, session: str) -> int:
    return int(
        store.db.execute(
            "SELECT count(*) FROM attempts a JOIN turns t ON t.id=a.turn_id "
            "WHERE t.session=?",
            (session,),
        ).fetchone()[0]
    )


async def run(settings: Settings, pause: float = 0, report: Path | None = None):
    telemetry = Telemetry()
    transcript: list[dict] = []
    phase = "setup"
    completed_report = False
    with tempfile.TemporaryDirectory(prefix="milai-acceptance-") as directory:
        config = replace(settings, database=Path(directory) / "acceptance.db")
        store = Store(config.database)
        learner = store.owner
        session = store.session(learner)
        scope = store.learning_scope(learner, session)
        tutor = Tutor(config, store, telemetry)

        async def turn(label: str, message: str, **references):
            nonlocal phase
            phase = label
            if transcript and pause:
                await asyncio.sleep(pause)
            print(f"[{label}] Learner: {message}", flush=True)
            reply = await tutor.respond(learner, session, message, **references)
            print(f"Tutor: {reply.text}", flush=True)
            entry = {
                "phase": label,
                "learner": message,
                "references": references,
                "tutor": reply.model_dump(mode="json"),
                "trace_id": telemetry.last_trace_id,
            }
            transcript.append(entry)
            return reply

        try:
            opening = await turn("main_generation", START)
            lessons = store.lessons(scope)
            if not lessons:
                raise RuntimeError("The opening request did not create a lesson")
            lesson_id = lessons[-1]["id"]
            detail = store.lesson_detail(learner, session, lesson_id)
            sections = detail["sections"]
            exercises = detail["exercises"]
            if not sections or not exercises:
                raise RuntimeError("The generated lesson has no sections or exercises")
            section_id = sections[0]["id"]
            selected_exercise = choose_trip_exercise(exercises)
            exercise_id = selected_exercise["id"]

            await turn(
                "section_question",
                "Can you explain this section with another short example?",
                lesson_id=lesson_id,
                section_id=section_id,
                selected_text=sections[0]["title"],
            )
            attempts_before_question = attempt_count(store, session)
            await turn(
                "exercise_question",
                "What is this exercise asking me to do? Please do not assess me yet.",
                lesson_id=lesson_id,
                exercise_id=exercise_id,
                selected_text=selected_exercise["title"],
            )
            question_added_no_attempt = (
                attempt_count(store, session) == attempts_before_question
            )

            attempts_before_answer = attempt_count(store, session)
            await turn(
                "answer_submission",
                trip_answer_for(selected_exercise),
                lesson_id=lesson_id,
                exercise_id=exercise_id,
                action="answer",
            )
            answer_was_assessed = attempt_count(store, session) > attempts_before_answer
            await turn(
                "main_continuation",
                "Continue learning from that lesson using my attempt. If a review is "
                "due, recommend it; otherwise choose a useful next step.",
                origin_lesson_id=lesson_id,
            )

            phase = "restart"
            focus_before_reopen = store.active_lesson(scope)
            before_restart = store.lesson_detail(learner, session, lesson_id)
            local_before_restart = store.conversation(
                learner, session, lesson_id=lesson_id
            )
            main_before_restart = store.conversation(learner, session)
            await tutor.close()
            store.close()
            store = Store(config.database)
            session = store.session(learner, session)
            scope = store.learning_scope(learner, session)
            tutor = Tutor(config, store, telemetry)
            after_restart = store.lesson_detail(learner, session, lesson_id)
            local_after_restart = store.conversation(
                learner, session, lesson_id=lesson_id
            )
            main_after_restart = store.conversation(learner, session)
            after_restart_reply = await turn(
                "lesson_after_restart",
                "What is the most useful thing to remember from this lesson?",
                lesson_id=lesson_id,
            )

            local_users = [
                item for item in local_before_restart if item["role"] == "user"
            ]
            main_users = [
                item for item in main_before_restart if item["role"] == "user"
            ]
            preference = store.profile(scope).get("teaching_preferences", {})
            latest_summary = store.discussion_summary(scope, lesson_id)
            checks = {
                "lesson_card": any(
                    card["id"] == lesson_id for card in opening.lesson_cards
                ),
                "complete_document": bool(
                    detail.get("objective")
                    and detail.get("recap")
                    and detail.get("worked_examples")
                    and sections
                ),
                "exercise_contract": 3 <= len(exercises) <= 6
                and sum(e.get("scaffolding") == "none" for e in exercises) >= 2,
                "section_question_scoped": any(
                    item.get("section_id") == section_id
                    and item.get("selected_text") == sections[0]["title"]
                    for item in local_users
                ),
                "exercise_question_scoped": any(
                    item.get("exercise_id") == exercise_id
                    and item.get("action") == "message"
                    and item.get("selected_text") == selected_exercise["title"]
                    for item in local_users
                ),
                "question_without_attempt": question_added_no_attempt,
                "answer_assessed": answer_was_assessed,
                "main_continuation_scoped": any(
                    item.get("origin_lesson_id") == lesson_id for item in main_users
                ),
                "discussion_summary_saved": bool(
                    before_restart.get("discussion_summary")
                ),
                "summary_updated_after_restart": bool(
                    latest_summary
                    and latest_summary["updating_turn_id"]
                    == after_restart_reply.turn_id
                    and len(latest_summary["summary"]) <= 2000
                ),
                "explicit_preference_saved": bool(
                    preference.get("value")
                    and "brief explanations" in preference.get("learner_quote", "")
                ),
                "histories_isolated": all(
                    item.get("lesson_id") == lesson_id for item in local_users
                )
                and all(item.get("lesson_id") is None for item in main_users),
                "viewing_preserved_focus": focus_before_reopen
                == store.active_lesson(scope),
                "document_persisted_after_restart": before_restart == after_restart,
                "discussions_persisted_after_restart": (
                    local_before_restart == local_after_restart
                    and main_before_restart == main_after_restart
                ),
                "post_restart_lesson_turn": len(
                    store.conversation(learner, session, lesson_id=lesson_id)
                )
                > len(local_after_restart),
            }
            result = {
                "kind": "live-synthetic-lesson",
                "models": {
                    "chat": config.model,
                    "lesson": config.lesson_model,
                },
                "model_compatibility": {
                    "generation_completed": checks["complete_document"],
                    "processing_tier": (
                        "See the separate live probe; requested Fast is not a "
                        "tier guarantee."
                    ),
                },
                "application_contracts": checks,
                "teaching_quality": {
                    "reviewed": False,
                    "note": (
                        "Review the transcript for accuracy, useful feedback, "
                        "and suitable pacing."
                    ),
                },
                "lesson": detail,
                "transcript": transcript,
                "learning": store.inspect(scope),
            }
            serialized = json.dumps(result, indent=2, ensure_ascii=False)
            if report:
                report.write_text(serialized + "\n")
            completed_report = True
            print(serialized)
            if not all(checks.values()):
                raise RuntimeError("Live acceptance missing contracts; review report")
        except Exception:
            if report and not completed_report:
                failure = {
                    "kind": "live-synthetic-lesson-incomplete",
                    "phase": phase,
                    "models": {
                        "chat": config.model,
                        "lesson": config.lesson_model,
                    },
                    "transcript": transcript,
                    "failed_trace_id": telemetry.last_trace_id,
                }
                report.write_text(
                    json.dumps(failure, indent=2, ensure_ascii=False) + "\n"
                )
            raise
        finally:
            await tutor.close()
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pause",
        type=float,
        default=0,
        help="Seconds between synthetic learner turns (default: 0)",
    )
    parser.add_argument("--report", type=Path, help="Save the synthetic JSON report")
    args = parser.parse_args()
    if not 0 <= args.pause <= 60:
        parser.error("--pause must be between 0 and 60 seconds")
    asyncio.run(run(Settings.load(), args.pause, args.report))


if __name__ == "__main__":
    main()
