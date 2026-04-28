"""Protocol for user-facing input and output."""

from typing import Protocol, runtime_checkable

from milai.io.types import Choice, RichContent


@runtime_checkable
class IOMediator(Protocol):
    async def show(self, content: RichContent) -> None:
        """Display non-interactive content."""

    async def prompt(self, label: str, *, placeholder: str = "") -> str:
        """Ask for free-text input."""

    async def choose(self, label: str, choices: list[Choice]) -> Choice:
        """Ask the user to select one of the provided choices."""

    async def confirm(self, label: str) -> bool:
        """Ask a yes/no question."""

    async def show_error(self, message: str) -> None:
        """Display an error message."""

    async def clear(self) -> None:
        """Clear the display surface."""
