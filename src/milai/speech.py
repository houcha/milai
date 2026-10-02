"""On-demand complete speech clips with a session-local atomic disk cache."""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from milai.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeechOptions:
    model: str = "gpt-4o-mini-tts"
    voice: str = "marin"
    instructions_version: str = "1"
    speed: float = 1.0
    format: str = "mp3"

    def instructions(self, locale: str) -> str:
        return (
            f"Speak in the language and dialect of {locale}, at a natural pace. "
            "Read the exact supplied text, without additions or explanations."
        )

    def key(self, text: str, locale: str) -> str:
        value = {
            **asdict(self),
            "text": text,
            "locale": locale,
            "instructions": self.instructions(locale),
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()


class SpeechService(Protocol):
    async def synthesize(
        self, text: str, locale: str, options: SpeechOptions
    ) -> bytes: ...
    async def close(self) -> None: ...


class OpenAISpeechService:
    def __init__(self, settings: Settings):
        self.client = AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=30,
            max_retries=0,
            http_client=DefaultAsyncHttpxClient(
                trust_env=False, follow_redirects=False
            ),
        )

    async def synthesize(self, text: str, locale: str, options: SpeechOptions) -> bytes:
        # The SDK buffers the complete HTTP response. Truncated transport reads
        # raise before bytes are returned, so partial streams never reach disk.
        response = await self.client.audio.speech.create(
            model=options.model,
            voice=options.voice,
            input=text,
            instructions=options.instructions(locale),
            speed=options.speed,
            response_format="mp3",
        )
        return response.content

    async def close(self) -> None:
        await self.client.close()


class SpeechCache:
    def __init__(
        self,
        database: Path,
        service: SpeechService,
        allowed: Callable[[str], bool],
        options: SpeechOptions | None = None,
    ):
        self.root = database.parent / "audio"
        self.service = service
        self.allowed = allowed
        self.options = options or SpeechOptions()
        self.semaphore = asyncio.Semaphore(4)
        self.pending: dict[tuple[str, str], asyncio.Task[bytes]] = {}

    async def clip(self, session: str, text: str, locale: str) -> bytes:
        if not self.allowed(session):
            raise ValueError("Session no longer exists")
        options = self.options
        key = options.key(text, locale)
        path = self.root / session / f"{key}.mp3"
        if path.is_file():
            audio = path.read_bytes()
            if audio:
                logger.info("pronunciation cache_hit=true")
                return audio
        identity = (session, key)
        task = self.pending.get(identity)
        if task is None:
            task = asyncio.create_task(
                self._generate(session, path, text, locale, options)
            )
            self.pending[identity] = task

            def completed(done: asyncio.Task[bytes]) -> None:
                self.pending.pop(identity, None)
                if not done.cancelled():
                    # Consume failures even if the requester disconnected.
                    done.exception()

            task.add_done_callback(completed)
        return await asyncio.shield(task)

    async def _generate(
        self, session: str, path: Path, text: str, locale: str, options: SpeechOptions
    ) -> bytes:
        started = time.monotonic()
        try:
            async with asyncio.timeout(30):
                async with self.semaphore:
                    if not self.allowed(session):
                        raise ValueError("Session no longer exists")
                    audio = await self.service.synthesize(text, locale, options)
            if not isinstance(audio, bytes) or not audio:
                raise ValueError("Speech provider returned empty audio")
            if not self.allowed(session):
                raise ValueError("Session no longer exists")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            try:
                with os.fdopen(descriptor, "wb") as file:
                    file.write(audio)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            logger.info(
                "pronunciation cache_hit=false duration_ms=%.0f",
                (time.monotonic() - started) * 1000,
            )
            return audio
        except BaseException as exc:
            logger.warning(
                "pronunciation failure=%s duration_ms=%.0f",
                type(exc).__name__,
                (time.monotonic() - started) * 1000,
            )
            raise

    async def close(self) -> None:
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.service.close()
