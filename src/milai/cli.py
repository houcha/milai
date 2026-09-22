"""Local single-user interface. The OS account is the authorization boundary."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APITimeoutError, RateLimitError

from milai.config import Settings
from milai.observability import Telemetry
from milai.probe import probe
from milai.store import SCHEMA_VERSION, SchemaMismatch, Store
from milai.tutor import Tutor, TutorReply
from milai.web import serve


async def chat(settings: Settings, session: str | None):
    store = Store(settings.database)
    telemetry = Telemetry()
    tutor = Tutor(settings, store, telemetry)
    try:
        session = store.session(store.owner, session)
        print(f"Milai · session {session}")
        print(
            "/quit to exit · /state to inspect learning · /new for a new conversation"
        )
        if not store.conversation(store.owner, session):
            print(
                "Tutor: What language would you like to learn, "
                "and what would you like to do with it?"
            )
        while True:
            try:
                message = await asyncio.to_thread(input, "You: ")
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
                print(f"New session: {session}; a fresh learning path.")
                continue
            try:
                reply = await tutor.respond(store.owner, session, message)
                print_reply(reply)
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
        print(activity["task"])
        skills = ", ".join(item["name"] for item in activity.get("skills", []))
        if skills:
            print(f"Skills: {skills}")


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
