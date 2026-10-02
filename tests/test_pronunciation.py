import asyncio
from dataclasses import replace
from typing import Any, cast

import pytest

from milai.pronunciation import parse_spans
from milai.speech import SpeechCache, SpeechOptions
from milai.store import Store
from milai.tools import Context
from milai.web import WebApplication
from tests.test_generation import draft


@pytest.mark.parametrize(
    "source,expected,texts",
    [
        (
            "**[[de-DE|Ich möchte einen Kaffee.]]**",
            "**Ich möchte einen Kaffee.**",
            ["Ich möchte einen Kaffee."],
        ),
        (
            "[[ru-RU|Привет!]] [[ru-RU|Как дела?]]",
            "Привет! Как дела?",
            ["Привет!", "Как дела?"],
        ),
        ("😀 [[de-DE|Öl]]", "😀 Öl", ["Öl"]),
        (
            "[[de-DE|Ich]] {{blank}} [[de-DE|Kaffee.]]",
            "Ich {{blank}} Kaffee.",
            ["Ich", "Kaffee."],
        ),
    ],
)
def test_parser(source, expected, texts):
    clean, spans = parse_spans(source)
    assert clean == expected
    assert [s["text"] for s in spans] == texts
    for span in spans:
        assert (
            clean[span["position"] : span["position"] + len(span["text"])]
            == span["text"]
        )


@pytest.mark.parametrize(
    "source",
    [
        "[[de-DE|x",
        "[[de|x]]",
        "[[de-DE|]]",
        "[[de-DE|a [[ru-RU|b]]]]",
        "[[de-DE|{{blank}}]]",
        "[[de-DE|**Hallo**]]",
        "[[de-DE|x]] ]]",
        "[[ru-RU|a\nb]]",
    ],
)
def test_parser_rejects_invalid(source):
    with pytest.raises(ValueError):
        parse_spans(source)


def saved_lesson(store, session):
    scope = store.learning_scope(store.owner, session)
    ctx = Context(store, scope, session, "seed", "Practice", "test")
    source = draft()
    source["document"]["worked_examples"][0]["markdown"] = "**[[de-DE|Ich lerne.]]**"
    exercises = source["exercises"]
    for exercise in exercises:
        exercise["skills"][0].pop("skill_key")
        exercise["skills"][0]["skill_id"] = "@focus"
        exercise["contract"]["content"]["items"][0]["text"] = "[[ru-RU|Я]]"
    with store.transaction():
        lesson = store.start_lesson(
            ctx,
            "German",
            None,
            source["new_skill"],
            [],
            "Test",
            document=source["document"],
            exercises=exercises,
        )
        ctx.lesson_ids.append(lesson["id"])
        store.save_turn(ctx, "Lesson", [])
    return store.lesson_detail(scope, session, lesson["id"])


class FakeSpeech:
    def __init__(self):
        self.calls = []
        self.result: bytes | Exception = b"complete-mp3"
        self.closed = False

    async def synthesize(self, text, locale, options):
        self.calls.append((text, locale, options))
        await asyncio.sleep(0.01)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def close(self):
        self.closed = True


class Writer:
    def __init__(self):
        self.data = bytearray()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass

    def close(self):
        pass

    async def wait_closed(self):
        pass


def test_persistence_clean_grading_and_migration(tmp_path):
    path = tmp_path / "db"
    store = Store(path)
    session = store.session(store.owner)
    lesson = saved_lesson(store, session)
    assert lesson["worked_examples"][0]["markdown"] == "**Ich lerne.**"
    exercise = lesson["exercises"][0]
    assert exercise["format"]["items"][0]["text"] == "Я"
    assert exercise["pronunciation"][0]["field"] == "format.items.0.text"
    contract = store.exercise_contract(
        store.learning_scope(store.owner, session), exercise["id"]
    )
    assert contract is not None
    assert contract.model_dump()["content"]["items"][0]["references"] == ["ich"]
    ids = [span["id"] for span in lesson["pronunciation"]]
    store.close()
    store = Store(path)
    assert [
        span["id"]
        for span in store.lesson_detail(store.owner, session, lesson["id"])[
            "pronunciation"
        ]
    ] == ids
    # Simulate a schema-10 database with already-clean historical content.
    store.db.execute("DROP TABLE pronunciation_spans")
    store.db.execute("UPDATE metadata SET value='10' WHERE key='schema_version'")
    store.close()
    store = Store(path)
    assert (
        store.lesson_detail(store.owner, session, lesson["id"])["pronunciation"] == []
    )
    store.close()


def test_api_cache_restart_ownership_and_tutor_lock(tmp_path):
    async def run():
        store = Store(tmp_path / "db")
        session = store.session(store.owner)
        lesson = saved_lesson(store, session)
        speech = FakeSpeech()
        app = WebApplication(store, cast(Any, object()), session, 8765, speech)
        assert speech.calls == []
        span = lesson["pronunciation"][0]
        payload = {"session": session, "lesson_id": lesson["id"], "span_id": span["id"]}

        async def click(value=payload):
            writer = Writer()
            await app.pronunciation(cast(Any, writer), value)
            return bytes(writer.data)

        async with app.lock:
            responses = await asyncio.wait_for(
                asyncio.gather(*(click() for _ in range(5))), 1
            )
        assert all(
            b"audio/mpeg" in response and response.endswith(b"complete-mp3")
            for response in responses
        )
        assert len(speech.calls) == 1
        await click()
        await app.close()
        assert speech.closed
        app = WebApplication(store, cast(Any, object()), session, 8765, speech)
        await click()
        assert len(speech.calls) == 1
        other = store.session(store.owner)
        for wrong in (
            {**payload, "session": other},
            {**payload, "lesson_id": "wrong"},
            {**payload, "span_id": "wrong"},
            {**payload, "text": "arbitrary"},
        ):
            assert b"400 Bad Request" in await click(wrong)
        assert len(speech.calls) == 1
        assert app.speech
        app.speech.options = replace(app.speech.options, voice="cedar")
        await click()
        app.speech.options = replace(app.speech.options, instructions_version="2")
        await click()
        assert len(speech.calls) == 3
        store.delete_session(store.owner, session)
        assert not (tmp_path / "audio" / session).exists()
        assert b"400 Bad Request" in await click()
        await app.close()
        store.close()

    asyncio.run(run())


def test_failure_empty_partial_retry_and_deletion_in_flight(tmp_path):
    async def run():
        speech = FakeSpeech()
        alive = True
        cache = SpeechCache(tmp_path / "db", speech, lambda _: alive)
        for result in (RuntimeError("failed read after partial bytes"), b""):
            speech.result = result
            with pytest.raises((ValueError, RuntimeError)):
                await cache.clip("session", "Привет!", "ru-RU")
            assert list(tmp_path.rglob("*.mp3")) == []
        speech.result = b"complete-mp3"
        assert await cache.clip("session", "Привет!", "ru-RU") == speech.result
        assert len(speech.calls) == 3
        task = asyncio.create_task(cache.clip("session", "Другой", "ru-RU"))
        await asyncio.sleep(0.001)
        alive = False
        with pytest.raises(ValueError):
            await task
        assert len(list(tmp_path.rglob("*.mp3"))) == 1
        await cache.close()

    asyncio.run(run())


def test_cache_key_includes_all_options():
    options = SpeechOptions()
    base = options.key("Hallo!", "de-DE")
    for field, value in {
        "voice": "cedar",
        "model": "other",
        "instructions_version": "2",
        "speed": 0.9,
        "format": "wav",
    }.items():
        assert replace(options, **{field: value}).key("Hallo!", "de-DE") != base
    assert options.key("Hallo", "de-DE") != base
    assert options.key("Hallo!", "de-AT") != base


def test_security_headers_and_origin_checks(tmp_path):
    import json

    async def run():
        store = Store(tmp_path / "db")
        session = store.session(store.owner)
        lesson = saved_lesson(store, session)
        speech = FakeSpeech()
        app = WebApplication(store, cast(Any, object()), session, 8765, speech)
        payload = {
            "session": session,
            "lesson_id": lesson["id"],
            "span_id": lesson["pronunciation"][0]["id"],
        }
        body = json.dumps(payload).encode()
        for host, origin, expected in (
            ("evil:8765", "http://127.0.0.1:8765", 400),
            ("127.0.0.1:8765", "http://evil:8765", 403),
            ("127.0.0.1:8765", "http://127.0.0.1:8765", 200),
        ):
            reader = asyncio.StreamReader()
            reader.feed_data(
                (
                    f"POST /api/pronunciation HTTP/1.1\r\nHost: {host}\r\n"
                    f"Origin: {origin}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode()
                + body
            )
            reader.feed_eof()
            writer = Writer()
            await app.handle(reader, cast(Any, writer))
            assert bytes(writer.data).startswith(f"HTTP/1.1 {expected}".encode())
        assert len(speech.calls) == 1
        assert b"media-src 'self' blob:" in writer.data
        await app.close()
        store.close()

    asyncio.run(run())


def test_synthesis_concurrency_limit_and_shutdown(tmp_path):
    async def run():
        active = maximum = 0
        release = asyncio.Event()

        class Speech(FakeSpeech):
            async def synthesize(self, text, locale, options):
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                try:
                    await release.wait()
                    return b"audio"
                finally:
                    active -= 1

        speech = Speech()
        cache = SpeechCache(tmp_path / "db", speech, lambda _: True)
        tasks = [
            asyncio.create_task(cache.clip("session", str(i), "de-DE"))
            for i in range(8)
        ]
        await asyncio.sleep(0.01)
        assert active == maximum == 4
        release.set()
        await asyncio.gather(*tasks)
        assert maximum == 4
        release.clear()
        pending = asyncio.create_task(cache.clip("session", "last", "de-DE"))
        await asyncio.sleep(0.01)
        await cache.close()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert speech.closed

    asyncio.run(run())


def test_new_practice_in_historical_lesson_and_instruction_spans(tmp_path):
    store = Store(tmp_path / "db")
    session = store.session(store.owner)
    lesson = saved_lesson(store, session)
    # Preserve the historical document while allowing annotated new practice.
    store.db.execute("DELETE FROM pronunciation_spans")
    scope = store.learning_scope(store.owner, session)
    ctx = Context(
        store,
        scope,
        session,
        "practice",
        "More practice",
        "test",
        lesson_id=lesson["id"],
    )
    exercise = {
        "contract": {
            "version": 1,
            "content": {
                "type": "transform",
                "target_form": "[[de-DE|ihr]]",
                "items": [
                    {
                        "text": "[[de-DE|Ich lerne.]]",
                        "context": "",
                        "references": ["Ihr lernt."],
                    }
                ],
            },
        },
        "scaffolding": "none",
        "skills": [
            {
                "skill_id": lesson["focus_skill_id"],
                "role": "target",
                "success_criterion": (
                    "Choose the matching subject pronoun for a named subject."
                ),
            }
        ],
        "source_ids": [],
    }
    with store.transaction():
        public = store.present_exercise(ctx, exercise)
        store.save_turn(ctx, "Extra practice", [])
    assert public["format"]["instruction"] == "Rewrite using ihr."
    assert public["format"]["items"][0]["text"] == "Ich lerne."
    assert {span["field"] for span in public["pronunciation"]} == {
        "format.instruction",
        "format.items.0.text",
    }
    assert store.lesson_detail(scope, session, lesson["id"])["pronunciation"] == []
    private = store.exercise_contract(scope, public["id"])
    assert private is not None
    assert private.model_dump()["content"]["items"][0]["references"] == ["Ihr lernt."]
    store.close()


def test_speech_sdk_complete_response_and_no_retries(tmp_path):
    import json

    import httpx2 as httpx
    from openai import APIConnectionError, AsyncOpenAI

    from milai.config import Settings
    from milai.speech import OpenAISpeechService

    async def run():
        requests = []

        class PartialResponse(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"partial-mp3"
                raise httpx.ReadError("Truncated response")

        async def handle(request):
            requests.append(json.loads(request.content))
            if len(requests) > 1:
                return httpx.Response(200, stream=PartialResponse())
            return httpx.Response(
                200, content=b"complete-mp3", headers={"content-type": "audio/mpeg"}
            )

        service = OpenAISpeechService(
            Settings(
                base_url="https://speech.invalid/v1", api_key="test-only", model="mock"
            )
        )
        assert service.client.max_retries == 0
        assert service.client.timeout == 30
        await service.client.close()
        service.client = AsyncOpenAI(
            api_key="test-only",
            base_url="https://speech.invalid/v1",
            max_retries=0,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(handle), trust_env=False
            ),
        )
        service.client._platform = "Linux"
        cache = SpeechCache(tmp_path / "db", service, lambda _: True)
        assert await cache.clip("session", "Привет!", "ru-RU") == b"complete-mp3"
        assert await cache.clip("session", "Привет!", "ru-RU") == b"complete-mp3"
        assert len(requests) == 1
        assert requests[0] == {
            "model": "gpt-4o-mini-tts",
            "voice": "marin",
            "input": "Привет!",
            "instructions": SpeechOptions().instructions("ru-RU"),
            "speed": 1.0,
            "response_format": "mp3",
        }
        with pytest.raises(APIConnectionError):
            await cache.clip("session", "Hallo!", "de-DE")
        assert len(requests) == 2
        assert len(list(tmp_path.rglob("*.mp3"))) == 1
        assert list(tmp_path.rglob("*.tmp")) == []
        await cache.close()

    asyncio.run(run())


def test_api_speech_failure_restores_explicit_retry(tmp_path):
    async def run():
        store = Store(tmp_path / "db")
        session = store.session(store.owner)
        lesson = saved_lesson(store, session)
        speech = FakeSpeech()
        app = WebApplication(store, cast(Any, object()), session, 8765, speech)
        payload = {
            "session": session,
            "lesson_id": lesson["id"],
            "span_id": lesson["pronunciation"][0]["id"],
        }
        for failed in (b"", RuntimeError("partial response failed")):
            speech.result = failed
            writer = Writer()
            await app.pronunciation(cast(Any, writer), payload)
            assert b"502 Bad Gateway" in writer.data
            assert b"Click again to retry" in writer.data
            assert not list(tmp_path.rglob("*.mp3"))
        assert len(speech.calls) == 2
        speech.result = b"complete-mp3"
        writer = Writer()
        await app.pronunciation(cast(Any, writer), payload)
        assert b"200 OK" in writer.data
        assert len(speech.calls) == 3
        await app.close()
        store.close()

    asyncio.run(run())


def test_completion_sentences_reject_annotations_but_context_is_playable():
    from milai.exercises import GeneratedExerciseContract

    content = {
        "type": "complete_sentence",
        "items": [
            {
                "text": "Ich {{blank}} Kaffee.",
                "context": "Vocabulary: [[de-DE|Kaffee]]",
                "references": ["trinke"],
            }
        ],
    }
    contract = GeneratedExerciseContract.model_validate(
        {"version": 1, "content": content}
    )
    assert contract.content.items[0].references == ["trinke"]
    content["items"][0]["text"] = "[[de-DE|Ich]] {{blank}} [[de-DE|Kaffee.]]"
    with pytest.raises(ValueError, match="Fill-in sentence text"):
        GeneratedExerciseContract.model_validate({"version": 1, "content": content})


@pytest.mark.parametrize("typed", [True, False])
def test_existing_gap_spans_cannot_be_played_even_after_submission(tmp_path, typed):
    import json

    async def run():
        store = Store(tmp_path / "db")
        session = store.session(store.owner)
        lesson = saved_lesson(store, session)
        exercise = lesson["exercises"][0]
        contract = {
            "version": 1,
            "content": {
                "type": "complete_sentence",
                "items": [
                    {
                        "text": "Ich {{blank}} Kaffee.",
                        "context": "Vocabulary: Kaffee",
                        "references": ["trinke"],
                    }
                ],
            },
        }
        store.db.execute(
            "DELETE FROM pronunciation_spans WHERE exercise_id=?", (exercise["id"],)
        )
        store.db.execute(
            "UPDATE exercises SET task=?, context=?, contract=? WHERE id=?",
            (
                "Ich {{blank}} Kaffee.",
                "Vocabulary: Kaffee",
                json.dumps(contract) if typed else None,
                exercise["id"],
            ),
        )
        field = "format.items.0.text" if typed else "task"
        context_field = "format.items.0.context" if typed else "context"
        store._save_pronunciation(
            lesson["id"],
            exercise["id"],
            [
                {
                    "id": "old-fragment",
                    "field": field,
                    "position": 0,
                    "text": "Ich",
                    "locale": "de-DE",
                },
                {
                    "id": "vocabulary",
                    "field": context_field,
                    "position": 12,
                    "text": "Kaffee",
                    "locale": "de-DE",
                },
            ],
        )
        scope = store.learning_scope(store.owner, session)
        assert [
            span["id"]
            for span in store.exercise(scope, exercise["id"])["pronunciation"]
        ] == ["vocabulary"]
        speech = FakeSpeech()
        app = WebApplication(store, cast(Any, object()), session, 8765, speech)
        payload = {
            "session": session,
            "lesson_id": lesson["id"],
            "span_id": "old-fragment",
        }
        writer = Writer()
        await app.pronunciation(cast(Any, writer), payload)
        assert b"400 Bad Request" in writer.data
        assert speech.calls == []
        payload["span_id"] = "vocabulary"
        await app.pronunciation(cast(Any, Writer()), payload)
        assert len(speech.calls) == 1
        assert speech.calls[0][0] == "Kaffee"
        # Completed fills must not turn the saved prompt into playable fragments.
        store.db.execute(
            "INSERT INTO attempts (id, learner, exercise_id, turn_id, "
            "learner_response, feedback, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "answer",
                scope,
                exercise["id"],
                "answer-turn",
                "trinke",
                "",
                "2026-10-01T00:00:00Z",
            ),
        )
        assert [
            span["id"]
            for span in store.exercise(scope, exercise["id"])["pronunciation"]
        ] == ["vocabulary"]
        writer = Writer()
        await app.pronunciation(
            cast(Any, writer), {**payload, "span_id": "old-fragment"}
        )
        assert b"400 Bad Request" in writer.data
        assert len(speech.calls) == 1
        await app.close()
        store.close()

    asyncio.run(run())
