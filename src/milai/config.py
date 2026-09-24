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
    timeout: float = 300
    request_timeout: float = 300
    max_tokens: int = 4096

    @classmethod
    def load(cls) -> Self:
        load_dotenv(Path.cwd() / ".env")
        values = {
            key: os.getenv(key, "").strip()
            for key in ("OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY")
        }
        values["OPENAI_BASE_URL"] = (
            values["OPENAI_BASE_URL"] or "https://api.openai.com/v1"
        )
        values["OPENAI_MODEL"] = values["OPENAI_MODEL"] or "gpt-6-luna"
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValueError("Configure in .env: " + ", ".join(missing))
        url = urlsplit(values["OPENAI_BASE_URL"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("OPENAI_BASE_URL must be HTTPS without credentials")
        if url.query or url.fragment:
            raise ValueError("OPENAI_BASE_URL cannot contain a query or fragment")
        return cls(
            base_url=values["OPENAI_BASE_URL"],
            model=values["OPENAI_MODEL"],
            api_key=values["OPENAI_API_KEY"],
            database=Path(os.getenv("MILAI_DATABASE", ".milai/learning.sqlite3")),
        )


def provider(settings: Settings):
    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient

    client = AsyncOpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.request_timeout,
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(trust_env=False, follow_redirects=False),
    )
    return OpenAIResponsesModel(model=settings.model, openai_client=client)
