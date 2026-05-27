import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from milai.io.tracing import TracingMediator
from milai.io.types import Choice, RichContent
from tests.fakes.mediator import ScriptedMediator


@dataclass
class RecordedSpan:
    name: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None = None

    def update(self, **kwargs: Any) -> None:
        self.output = kwargs.get("output")


class RecordingObservability:
    def __init__(self) -> None:
        self.spans: list[RecordedSpan] = []

    @contextmanager
    def span(self, name: str, *, input: dict[str, Any] | None = None):
        span = RecordedSpan(name=name, input=input)
        self.spans.append(span)
        yield span

    @contextmanager
    def state_dispatch(self, session):
        _ = session
        yield RecordedSpan(name="state", input=None)

    def shutdown(self) -> None:
        pass


def test_prompt_choose_and_confirm_create_clean_user_input_spans() -> None:
    observability = RecordingObservability()
    mediator = TracingMediator(
        ScriptedMediator(["hola", "continue", True]),
        observability,
    )
    choices = [
        Choice("Continue", "continue", "Resume"),
        Choice("Start new", "start_new", "Replace"),
    ]

    async def run_script() -> None:
        assert await mediator.prompt("Answer", placeholder="type here") == "hola"
        assert await mediator.choose("Saved session found", choices) == choices[0]
        assert await mediator.confirm("Try again?") is True

    asyncio.run(run_script())

    assert observability.spans == [
        RecordedSpan(
            name="milai.user.prompt",
            input={"label": "Answer", "placeholder": "type here"},
            output={"answer": "hola"},
        ),
        RecordedSpan(
            name="milai.user.choose",
            input={
                "label": "Saved session found",
                "choices": [
                    {"label": "Continue", "value": "continue"},
                    {"label": "Start new", "value": "start_new"},
                ],
            },
            output={"choice": "continue"},
        ),
        RecordedSpan(
            name="milai.user.confirm",
            input={"label": "Try again?"},
            output={"confirmed": True},
        ),
    ]


def test_show_error_and_clear_do_not_create_observations() -> None:
    observability = RecordingObservability()
    inner = ScriptedMediator([])
    mediator = TracingMediator(inner, observability)

    async def run_script() -> None:
        await mediator.show(RichContent("hello"))
        await mediator.show_error("broken")
        await mediator.clear()

    asyncio.run(run_script())

    assert observability.spans == []
    assert [content.text for content in inner.shown] == ["hello"]
    assert inner.errors == ["broken"]
    assert inner.cleared == 1
