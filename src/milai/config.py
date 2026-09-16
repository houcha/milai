"""Explicit provider and resource boundaries."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    database: Path = Path(".milai/learning.sqlite3")
    max_turns: int = 16
    max_tools: int = 20
    timeout: float = 180
    max_tokens: int = 4096

    @classmethod
    def load(cls) -> Self:
        load_dotenv(Path.cwd() / ".env")
        values = {
            key: os.getenv(key, "").strip()
            for key in ("GEMINI_BASE_URL", "GEMINI_MODEL", "GEMINI_API_KEY")
        }
        values["GEMINI_BASE_URL"] = (
            values["GEMINI_BASE_URL"]
            or "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        values["GEMINI_MODEL"] = values["GEMINI_MODEL"] or "gemini-3.5-flash-lite"
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValueError("Configure in .env: " + ", ".join(missing))
        url = urlsplit(values["GEMINI_BASE_URL"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("GEMINI_BASE_URL must be HTTPS without credentials")
        if url.query or url.fragment:
            raise ValueError("GEMINI_BASE_URL cannot contain a query or fragment")
        return cls(
            base_url=values["GEMINI_BASE_URL"],
            model=values["GEMINI_MODEL"],
            api_key=values["GEMINI_API_KEY"],
            database=Path(os.getenv("MILAI_DATABASE", ".milai/learning.sqlite3")),
        )


def provider(settings: Settings):
    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient

    client = AsyncOpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=60,
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(trust_env=False, follow_redirects=False),
    )
    return OpenAIChatCompletionsModel(model=settings.model, openai_client=client)
