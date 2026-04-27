# Contract: IOMediator

**File**: `src/milai/io/mediator.py`
**Type**: Python `Protocol` (structural subtyping)
**Purpose**: Decouple all user-facing input/output from the state machine and LLM logic. The Textual TUI is the temporary v1 implementation; the v2 browser adapter is expected to become the product implementation. Nothing in `src/milai/state/`, `src/milai/llm/`, or `src/milai/srs/` may import Textual, FastAPI, WebSocket, cookie, or browser-specific APIs directly.

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
# src/milai/io/types.py

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

## Implementations

| Version | Implementation class | Location |
|---|---|---|
| v1 TUI scaffolding | `TextualMediator` | `src/milai/io/tui/app.py` |
| v2 Web product UI | `ApiMediator` (future) | `src/milai/io/web/mediator.py` |
| Tests | `ScriptedMediator` | `tests/fakes/mediator.py` |

The concrete implementation is created at the top-level entrypoint (`src/milai/main.py`) and injected into the state handler constructors that need user I/O. No state handler knows which concrete implementation it is using. v2 does not need to preserve the Textual implementation if it is no longer useful.

On launch, `src/milai/main.py` may also use `IOMediator.choose()` before the state machine starts to ask whether an existing saved session should be continued or replaced with a new onboarding flow. This is entrypoint orchestration, not a separate `AppState` variant.
