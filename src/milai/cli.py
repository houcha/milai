"""Local single-user interface. The OS account is the authorization boundary."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APITimeoutError, RateLimitError

from milai.config import Settings
from milai.exercise_format import terminal_exercise_task
from milai.observability import Telemetry
from milai.probe import probe
from milai.store import SCHEMA_VERSION, InvalidReference, SchemaMismatch, Store
from milai.tutor import Tutor, TutorReply
from milai.web import serve


async def chat(settings: Settings, session: str | None):
    store = Store(settings.database)
    telemetry = Telemetry()
    tutor = Tutor(settings, store, telemetry)
    try:
        session = store.session(store.owner, session)
        lesson_id: str | None = None
        origin_lesson_id: str | None = None
        print(f"Milai · session {session}")
        print("/lessons to see lessons · /lesson <id> to open · /back for main chat")
        print("/answer <exercise-id> <text> to submit · /state · /new · /quit")
        if not store.conversation(store.owner, session):
            print(
                "Tutor: What language would you like to learn, "
                "and what would you like to do with it?"
            )
        while True:
            try:
                place = "lesson" if lesson_id else "main"
                message = await asyncio.to_thread(input, f"You ({place}): ")
            except EOFError:
                break
            if message.strip() == "/quit":
                break
            if message.strip() == "/state":
                print(
                    json.dumps(
                        store.snapshot(store.learning_scope(store.owner, session)),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                continue
            if message.strip() == "/new":
                session = store.session(store.owner)
                lesson_id = None
                origin_lesson_id = None
                print(f"New session: {session}; a fresh learning path.")
                continue
            if message.strip() == "/lessons":
                scope = store.learning_scope(store.owner, session)
                lessons = store.lessons(scope)
                if not lessons:
                    print("No lessons yet. Use the main conversation to choose one.")
                for lesson in lessons:
                    marker = " (open)" if lesson["id"] == lesson_id else ""
                    print(f"{lesson['title']} · {lesson['id']}{marker}")
                continue
            if message.strip().startswith("/lesson"):
                parts = message.strip().split()
                if len(parts) != 2 or parts[0] != "/lesson":
                    print("Use /lesson <id> from /lessons.")
                    continue
                try:
                    detail = store.lesson_detail(store.owner, session, parts[1])
                    for exercise in detail["exercises"]:
                        exercise["status"] = store.exercise_status(
                            store.owner, session, exercise["id"]
                        )
                    discussion = store.conversation(
                        store.owner, session, limit=3, lesson_id=parts[1]
                    )
                except (InvalidReference, ValueError):
                    print("That lesson is not in this session. Use /lessons.")
                    continue
                lesson_id = parts[1]
                origin_lesson_id = None
                print_lesson(detail)
                if discussion:
                    print("Recent discussion:")
                    for item in discussion:
                        speaker = "You" if item["role"] == "user" else "Tutor"
                        print(f"{speaker}: {item['content']}")
                continue
            if message.strip() == "/back":
                if lesson_id is None:
                    print("Already in the main conversation.")
                else:
                    origin_lesson_id = lesson_id
                    lesson_id = None
                    print(
                        "Main conversation. Your next message can continue "
                        "from the lesson."
                    )
                continue
            answer_parts = message.strip().split(maxsplit=2)
            if answer_parts and answer_parts[0] == "/answer":
                if lesson_id is None:
                    print("Open a lesson with /lesson <id> before answering.")
                    continue
                if len(answer_parts) != 3 or not answer_parts[2].strip():
                    print("Use /answer <exercise-id> <text>.")
                    continue
                exercise_id, answer = answer_parts[1], answer_parts[2]
                try:
                    reply = await tutor.respond(
                        store.owner,
                        session,
                        answer,
                        lesson_id=lesson_id,
                        exercise_id=exercise_id,
                        action="answer",
                    )
                    print_reply(reply)
                except (InvalidReference, ValueError) as exc:
                    print(f"Answer not accepted: {exc}")
                except RateLimitError:
                    print("Provider quota reached; this turn was rolled back.")
                except (APITimeoutError, TimeoutError):
                    print("Model provider timed out; this turn was not saved.")
                except Exception as exc:
                    print(f"Turn failed ({type(exc).__name__}); changes rolled back.")
                continue
            try:
                reply = await tutor.respond(
                    store.owner,
                    session,
                    message,
                    lesson_id=lesson_id,
                    origin_lesson_id=origin_lesson_id if lesson_id is None else None,
                )
                print_reply(reply)
                if lesson_id is None:
                    origin_lesson_id = None
            except RateLimitError:
                print(
                    "Provider quota reached; this turn's learning changes were rolled "
                    "back. Wait for the quota to reset before sending it again. "
                    "No paid fallback was used."
                )
            except (APITimeoutError, TimeoutError):
                print(
                    "Model provider timed out; this turn was not saved. "
                    "Try again shortly."
                )
            except Exception as exc:
                print(
                    f"Turn failed ({type(exc).__name__}); "
                    "learning changes rolled back. Try again."
                )
    finally:
        await tutor.close()
        store.close()


def print_reply(reply: TutorReply) -> None:
    if reply.text.strip():
        print(f"Tutor: {reply.text}")
    for activity in reply.activities:
        print(f"\n[{activity['kind'].upper()}] {activity['title']}")
        if activity.get("context"):
            print(f"Context: {activity['context']}")
        print(terminal_exercise_task(activity["task"]))
        skills = ", ".join(item["name"] for item in activity.get("skills", []))
        if skills:
            print(f"Skills: {skills}")
    for lesson in getattr(reply, "lesson_cards", []):
        print(f"\n[OPEN LESSON] {lesson['title']} · /lesson {lesson['id']}")


def print_lesson(detail: dict) -> None:
    """Print a stored document without changing the session's teaching focus."""
    print(f"\n# {detail['title']}")
    if detail.get("objective"):
        print(f"\nObjective: {detail['objective']}")
    for section in detail.get("sections", []):
        print(f"\n## {section['title']} ({section['id']})")
        print(section.get("markdown", section.get("content", section.get("body", ""))))
    examples = detail.get("worked_examples", [])
    if examples:
        print("\n## Worked examples")
        for example in examples:
            if isinstance(example, dict):
                if example.get("title"):
                    print(f"\n### {example['title']}")
                print(example.get("markdown", example.get("content", "")))
            else:
                print(example)
    if detail.get("recap"):
        print(f"\n## Recap\n{detail['recap']}")
    if detail.get("exercises"):
        print("\n## Exercises")
        for exercise in detail["exercises"]:
            status = exercise.get("status", {})
            if status.get("completed"):
                label = "complete"
            elif status.get("assessments"):
                label = "attempted"
            else:
                label = "ready"
            print(f"\n[{label}] {exercise['title']} · {exercise['id']}")
            print(terminal_exercise_task(exercise["task"]))
        print("\nSubmit with /answer <exercise-id> <text>.")
    print("Ask questions here, or use /back for the main conversation.\n")


def main():
    parser = argparse.ArgumentParser(description="Milai local language tutor")
    commands = parser.add_subparsers(dest="command", required=True)
    chat_parser = commands.add_parser("chat")
    chat_parser.add_argument("--session", help="Resume an existing session ID")
    web_parser = commands.add_parser("web", help="Run the local browser interface")
    web_parser.add_argument("--session", help="Resume an existing session ID")
    web_parser.add_argument("--port", type=int, default=8765)
    commands.add_parser("probe", help="Live model tool/continuation check")
    commands.add_parser("inspect", help="Print local learning state and change events")
    reset_parser = commands.add_parser(
        "reset", help="Archive the database and create the current schema"
    )
    reset_parser.add_argument(
        "--yes", action="store_true", help="Required acknowledgement of the reset"
    )
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env")
    try:
        database = Path(os.getenv("MILAI_DATABASE", ".milai/learning.sqlite3"))
        if args.command == "reset":
            if not args.yes:
                parser.exit(
                    2,
                    "Reset requires --yes; the existing database will be archived.\n",
                )
            archived = Store.reset(database)
            if archived:
                print("Archived: " + ", ".join(str(path) for path in archived))
            print(f"Created schema {SCHEMA_VERSION} at {database}")
        elif args.command == "inspect":
            store = Store(database)
            try:
                print(
                    json.dumps(store.inspect(store.owner), indent=2, ensure_ascii=False)
                )
            finally:
                store.close()
        elif args.command == "probe":
            settings = Settings.load()
            print(json.dumps(asyncio.run(probe(settings, Telemetry())), indent=2))
        elif args.command == "web":
            asyncio.run(serve(Settings.load(), args.session, args.port))
        else:
            asyncio.run(chat(Settings.load(), args.session))
    except RateLimitError:
        parser.exit(
            1,
            "Provider quota reached. Wait for the quota to reset; "
            "no automatic retry or paid fallback was used.\n",
        )
    except (ValueError, PermissionError, SchemaMismatch) as exc:
        parser.exit(2, f"{exc}\n")
    except KeyboardInterrupt:
        print("\nGoodbye.")
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        parser.exit(
            1,
            f"Operation failed ({type(exc).__name__}, status={status}). "
            "Check endpoint availability and credentials; no secret details logged.\n",
        )


if __name__ == "__main__":
    main()
