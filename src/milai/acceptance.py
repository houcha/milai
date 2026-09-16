"""Live synthetic learner scenario; produces a reviewable transcript, never a mock."""

import argparse
import asyncio
import json
import tempfile
from dataclasses import replace
from pathlib import Path

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import Store
from milai.tutor import Tutor

MESSAGES = [
    "Hi, I'd like help learning a language.",
    "English. I speak Spanish, but please explain in simple English. "
    "I think I'm A2. I want to talk about trips and read basic websites. "
    "I like technology and walking. What else do you need to know?",
    "I prefer short public web pages and original exercises. "
    "Please retrieve https://example.com as a short reading warmup, "
    "give me a brief provisional outline, then a tiny lesson with an original "
    "past-tense exercise: Yesterday I ___ to the park (go).",
    "Yesterday I goed to the park.",
    "Why isn't goed right? Give me a hint before I try again.",
    "Yesterday I went to the park.",
    "Let's continue with a fresh exercise based on how I did, without a hint yet.",
]


async def run(settings: Settings, pause: float = 30, report: Path | None = None):
    telemetry = Telemetry()
    transcript = []
    # Isolate synthetic evidence from the real learner database.
    with tempfile.TemporaryDirectory(prefix="milai-acceptance-") as directory:
        config = replace(settings, database=Path(directory) / "acceptance.db")
        store = Store(config.database)
        learner = store.owner
        session = store.session(learner)
        tutor = Tutor(config, store, telemetry)
        try:
            for index, message in enumerate(MESSAGES):
                if index and pause:
                    await asyncio.sleep(pause)
                if index == len(MESSAGES) - 1:
                    await tutor.close()
                    store.close()
                    store = Store(config.database)
                    session = store.session(learner)
                    tutor = Tutor(config, store, telemetry)
                print(f"Learner: {message}", flush=True)
                reply = await tutor.respond(learner, session, message)
                print(f"Tutor: {reply}\n", flush=True)
                transcript.append(
                    {
                        "learner": message,
                        "tutor": reply,
                        "trace_id": telemetry.last_trace_id,
                    }
                )
            snapshot = store.inspect(learner)
            state = snapshot["state"]
            checks = {
                "profile_saved": all(
                    field in state["profile"]
                    for field in (
                        "target_language",
                        "explanation_language",
                        "level",
                        "goals",
                        "interests",
                        "source_preferences",
                    )
                ),
                "provisional_curriculum": bool(state["curriculum"]),
                "live_source_available": any(
                    s["status"] == "available" for s in state["sources"]
                ),
                "exercise_saved": bool(state["exercises"]),
                "needs_work_evidence": any(
                    e["outcome"] == "needs_work" for e in state["evidence"]
                ),
                "assisted_success": any(
                    e["outcome"] == "success" and not e["independent_success"]
                    for e in state["evidence"]
                ),
                "adapted_action_after_restart": any(
                    e["session"] == session and e["kind"] == "teaching_action"
                    for e in snapshot["events"]
                ),
            }
            result = {
                "kind": "live-synthetic",
                "model": settings.model,
                "checks": checks,
                "transcript": transcript,
                "learning": snapshot,
            }
            serialized = json.dumps(result, indent=2, ensure_ascii=False)
            if report:
                report.write_text(serialized + "\n")
            print(serialized)
            if not all(checks.values()):
                raise RuntimeError(
                    "Live acceptance missing capabilities; review transcript"
                )
        finally:
            if report and len(transcript) < len(MESSAGES):
                report.write_text(
                    json.dumps(
                        {
                            "kind": "live-synthetic-incomplete",
                            "model": settings.model,
                            "transcript": transcript,
                            "learning": store.inspect(learner),
                            "failed_trace_id": telemetry.last_trace_id,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            await tutor.close()
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pause",
        type=float,
        default=30,
        help="Seconds between synthetic learner turns (default: 30)",
    )
    parser.add_argument("--report", type=Path, help="Save the synthetic JSON report")
    args = parser.parse_args()
    if not 0 <= args.pause <= 60:
        parser.error("--pause must be between 0 and 60 seconds")
    asyncio.run(run(Settings.load(), args.pause, args.report))


if __name__ == "__main__":
    main()
