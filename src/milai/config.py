"""Explicit provider and resource boundaries."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Self
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
    lesson_model: str = "gpt-6-sol"
    lesson_reasoning_effort: Literal[
        "none", "minimal", "low", "medium", "high", "xhigh", "max"
    ] = "low"
    lesson_service_tier: str = "fast"
    lesson_max_output_tokens: int = 32768

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
        values["OPENAI_MODEL"] = values["OPENAI_MODEL"] or "gpt-6-sol"
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValueError("Configure in .env: " + ", ".join(missing))
        url = urlsplit(values["OPENAI_BASE_URL"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("OPENAI_BASE_URL must be HTTPS without credentials")
        if url.query or url.fragment:
            raise ValueError("OPENAI_BASE_URL cannot contain a query or fragment")
        lesson_model = os.getenv("OPENAI_LESSON_MODEL", "gpt-6-sol").strip()
        lesson_effort = os.getenv("OPENAI_LESSON_REASONING_EFFORT", "low").strip()
        lesson_tier = os.getenv("OPENAI_LESSON_SERVICE_TIER", "fast").strip()
        lesson_budget = os.getenv("MILAI_LESSON_MAX_OUTPUT_TOKENS", "32768").strip()
        if not lesson_model:
            raise ValueError("OPENAI_LESSON_MODEL must not be empty")
        if lesson_effort not in {
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("OPENAI_LESSON_REASONING_EFFORT is unsupported")
        if not lesson_tier or len(lesson_tier) > 40:
            raise ValueError("OPENAI_LESSON_SERVICE_TIER must be 1–40 characters")
        try:
            lesson_max_output_tokens = int(lesson_budget)
        except ValueError as exc:
            raise ValueError(
                "MILAI_LESSON_MAX_OUTPUT_TOKENS must be an integer"
            ) from exc
        if lesson_max_output_tokens < 1:
            raise ValueError("MILAI_LESSON_MAX_OUTPUT_TOKENS must be positive")
        return cls(
            base_url=values["OPENAI_BASE_URL"],
            model=values["OPENAI_MODEL"],
            api_key=values["OPENAI_API_KEY"],
            database=Path(os.getenv("MILAI_DATABASE", ".milai/learning.sqlite3")),
            lesson_model=lesson_model,
            lesson_reasoning_effort=lesson_effort,
            lesson_service_tier=lesson_tier,
            lesson_max_output_tokens=lesson_max_output_tokens,
        )


def provider(settings: Settings, *, model_name: str | None = None, client=None):
    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient

    selected_model = settings.model if model_name is None else model_name
    if not selected_model:
        raise ValueError("Model name must not be empty")
    if client is None:
        client = AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.request_timeout,
            max_retries=0,
            http_client=DefaultAsyncHttpxClient(
                trust_env=False, follow_redirects=False
            ),
        )
    return OpenAIResponsesModel(model=selected_model, openai_client=client)


def providers(settings: Settings):
    """Return interactive and lesson models using one authenticated API client."""
    chat_model = provider(settings)
    lesson_model = provider(
        settings, model_name=settings.lesson_model, client=chat_model._client
    )
    return chat_model, lesson_model
