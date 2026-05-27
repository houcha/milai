"""Tracing decorator for user-facing input mediation."""

from milai.io.mediator import IOMediator
from milai.io.types import Choice, RichContent
from milai.observability import Observability


class TracingMediator:
    def __init__(self, inner: IOMediator, observability: Observability) -> None:
        self._inner = inner
        self._observability = observability

    async def show(self, content: RichContent) -> None:
        await self._inner.show(content)

    async def prompt(self, label: str, *, placeholder: str = "") -> str:
        with self._observability.span(
            "milai.user.prompt",
            input={"label": label, "placeholder": placeholder},
        ) as span:
            answer = await self._inner.prompt(label, placeholder=placeholder)
            span.update(output={"answer": answer})
            return answer

    async def choose(self, label: str, choices: list[Choice]) -> Choice:
        input_payload = {
            "label": label,
            "choices": [
                {"label": choice.label, "value": choice.value} for choice in choices
            ],
        }
        with self._observability.span("milai.user.choose", input=input_payload) as span:
            choice = await self._inner.choose(label, choices)
            span.update(output={"choice": choice.value})
            return choice

    async def confirm(self, label: str) -> bool:
        with self._observability.span(
            "milai.user.confirm", input={"label": label}
        ) as span:
            confirmed = await self._inner.confirm(label)
            span.update(output={"confirmed": confirmed})
            return confirmed

    async def show_error(self, message: str) -> None:
        await self._inner.show_error(message)

    async def clear(self) -> None:
        await self._inner.clear()
