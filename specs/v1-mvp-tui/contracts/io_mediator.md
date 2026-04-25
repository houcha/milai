# Contract: IOMediator

**File**: `milai/io/mediator.py`
**Type**: Python `Protocol` (structural subtyping)
**Purpose**: Decouple all user-facing input/output from the state machine and LLM logic. The Textual TUI is one implementation; a future REST API or test double is another. Nothing in `milai/state/`, `milai/llm/`, or `milai/srs/` may import Textual directly.

---

## Protocol Definition

```python
from typing import Protocol, runtime_checkable
from milai.io.types import RichContent, Choice

@runtime_checkable
class IOMediator(Protocol):
    async def show(self, content: RichContent) -> None:
        """Display content to the user. Non-interactive."""

    async def prompt(self, label: str, *, placeholder: str = "") -> str:
        """Ask for free-text input. Returns the raw string the user typed."""

    async def choose(self, label: str, choices: list[Choice]) -> Choice:
        """Present a labelled list of choices. Returns the selected Choice."""

    async def confirm(self, label: str) -> bool:
        """Ask a yes/no question. Returns True for yes."""

    async def show_error(self, message: str) -> None:
        """Display an error message. Non-interactive."""

    async def clear(self) -> None:
        """Clear the display (e.g. before a new state renders)."""
```

---

## Supporting Types

```python
# milai/io/types.py

from dataclasses import dataclass, field
from enum import Enum

class ContentKind(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    HEADER = "header"
    PROGRESS = "progress"

@dataclass
class RichContent:
    text: str
    kind: ContentKind = ContentKind.TEXT
    # progress-specific
    current: int = 0
    total: int = 0

@dataclass
class Choice:
    label: str                       # display text
    value: str                       # machine-readable value returned on selection
    description: str = ""           # optional subtitle
```

---

## Contract Rules

1. **No side effects outside the display surface**: `show`, `show_error`, and `clear` MUST NOT modify `UserState` or emit to stdout/stderr except through the display surface.
2. **`prompt` returns raw input verbatim**: trimmed of leading/trailing whitespace; never `None`; empty string is valid.
3. **`choose` returns exactly one element from the provided `choices` list**: the returned `Choice` object must be identical (by value) to one of the provided choices.
4. **`confirm` returns a strict bool**: no third state, no timeout default — the user must provide an explicit answer.
5. **All methods are `async`**: implementations must not block the event loop.
6. **Implementations must not raise on display errors** (e.g., terminal resize, encoding issues) — they should degrade gracefully (truncate, strip styling).

---

## Test Double (for unit tests)

```python
class ScriptedMediator:
    """
    Deterministic test double. Feed it a script of responses;
    it plays them back and records all show() calls for assertion.
    """
    def __init__(self, responses: list[str | bool | Choice]):
        self._responses = iter(responses)
        self.shown: list[RichContent] = []
        self.errors: list[str] = []

    async def show(self, content: RichContent) -> None:
        self.shown.append(content)

    async def prompt(self, label: str, *, placeholder: str = "") -> str:
        return str(next(self._responses))

    async def choose(self, label: str, choices: list[Choice]) -> Choice:
        return next(self._responses)  # type: ignore[return-value]

    async def confirm(self, label: str) -> bool:
        return bool(next(self._responses))

    async def show_error(self, message: str) -> None:
        self.errors.append(message)

    async def clear(self) -> None:
        pass
```

---

## Implementations (v1 / v2)

| Version | Implementation class | Location |
|---|---|---|
| v1 TUI | `TextualMediator` | `milai/io/tui/app.py` |
| v2 API | `ApiMediator` (future) | `milai/io/api/handler.py` |
| Tests | `ScriptedMediator` | `tests/fakes/mediator.py` |

The concrete implementation is injected at the top-level entrypoint (`milai/main.py`) and passed into the `run()` loop alongside `LLMClient` and `StorageClient`. No state handler knows which implementation it is using.
