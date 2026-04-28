"""Minimal terminal-backed mediator for the v1 TUI boundary."""

import asyncio

from milai.io.types import Choice, ContentKind, RichContent


class TextualMediator:
    """Small async mediator shim; richer Textual rendering comes in story work."""

    async def show(self, content: RichContent) -> None:
        prefix = "# " if content.kind is ContentKind.HEADER else ""
        print(f"{prefix}{content.text}")

    async def prompt(self, label: str, *, placeholder: str = "") -> str:
        suffix = f" ({placeholder})" if placeholder else ""
        return (await asyncio.to_thread(input, f"{label}{suffix}: ")).strip()

    async def choose(self, label: str, choices: list[Choice]) -> Choice:
        await self.show(RichContent(label, kind=ContentKind.HEADER))
        for index, choice in enumerate(choices, start=1):
            description = f" - {choice.description}" if choice.description else ""
            await self.show(RichContent(f"{index}. {choice.label}{description}"))
        while True:
            raw = await self.prompt("Choose")
            if raw.isdigit():
                index = int(raw) - 1
                if 0 <= index < len(choices):
                    return choices[index]
            for choice in choices:
                if raw == choice.value:
                    return choice
            await self.show_error("Please choose one of the listed options.")

    async def confirm(self, label: str) -> bool:
        while True:
            raw = (await self.prompt(f"{label} [y/n]")).lower()
            if raw in {"y", "yes"}:
                return True
            if raw in {"n", "no"}:
                return False
            await self.show_error("Please answer yes or no.")

    async def show_error(self, message: str) -> None:
        print(f"Error: {message}")

    async def clear(self) -> None:
        print()
