"""Test double for IOMediator."""

from collections.abc import Iterable

from milai.io.types import Choice, RichContent


class ScriptedMediator:
    def __init__(self, responses: Iterable[str | bool | Choice]) -> None:
        self._responses = iter(responses)
        self.shown: list[RichContent] = []
        self.errors: list[str] = []
        self.cleared = 0

    async def show(self, content: RichContent) -> None:
        self.shown.append(content)

    async def prompt(self, label: str, *, placeholder: str = "") -> str:
        _ = (label, placeholder)
        return str(next(self._responses)).strip()

    async def choose(self, label: str, choices: list[Choice]) -> Choice:
        _ = label
        response = next(self._responses)
        if isinstance(response, Choice) and response in choices:
            return response
        if isinstance(response, str):
            for choice in choices:
                if response == choice.value:
                    return choice
        msg = "scripted choice was not one of the provided choices"
        raise AssertionError(msg)

    async def confirm(self, label: str) -> bool:
        _ = label
        return bool(next(self._responses))

    async def show_error(self, message: str) -> None:
        self.errors.append(message)

    async def clear(self) -> None:
        self.cleared += 1
