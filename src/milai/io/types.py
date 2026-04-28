"""Provider-neutral user-facing content types."""

from dataclasses import dataclass
from enum import StrEnum


class ContentKind(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    HEADER = "header"
    PROGRESS = "progress"


@dataclass(frozen=True)
class RichContent:
    text: str
    kind: ContentKind = ContentKind.TEXT
    current: int = 0
    total: int = 0


@dataclass(frozen=True)
class Choice:
    label: str
    value: str
    description: str = ""
