import asyncio
import inspect
from typing import get_type_hints


def test_io_mediator_protocol_is_async_and_runtime_checkable() -> None:
    from milai.io.mediator import IOMediator

    assert getattr(IOMediator, "_is_protocol", False)
    assert getattr(IOMediator, "_is_runtime_protocol", False)

    expected_methods = ("show", "prompt", "choose", "confirm", "show_error", "clear")
    for method_name in expected_methods:
        method = getattr(IOMediator, method_name)
        assert inspect.iscoroutinefunction(method), method_name


def test_io_supporting_types_match_contract_defaults() -> None:
    from milai.io.types import Choice, ContentKind, RichContent

    assert ContentKind.TEXT.value == "text"
    assert ContentKind.MARKDOWN.value == "markdown"
    assert ContentKind.HEADER.value == "header"
    assert ContentKind.PROGRESS.value == "progress"

    assert RichContent("hello").kind is ContentKind.TEXT
    assert (
        RichContent("progress", kind=ContentKind.PROGRESS, current=1, total=3).current
        == 1
    )
    assert Choice(label="Continue", value="continue").description == ""


def test_scripted_mediator_conforms_and_records_display_calls() -> None:
    from milai.io.mediator import IOMediator
    from milai.io.types import Choice, RichContent
    from tests.fakes.mediator import ScriptedMediator

    first = Choice(label="First", value="first")
    second = Choice(label="Second", value="second")
    mediator = ScriptedMediator(["  raw answer  ", second, True])

    async def run_script() -> None:
        await mediator.show(RichContent("welcome"))
        assert await mediator.prompt("Name", placeholder="optional") == "raw answer"
        assert await mediator.choose("Pick", [first, second]) == second
        assert await mediator.confirm("Ready?") is True
        await mediator.show_error("problem")
        await mediator.clear()

    asyncio.run(run_script())

    assert isinstance(mediator, IOMediator)
    assert [content.text for content in mediator.shown] == ["welcome"]
    assert mediator.errors == ["problem"]


def test_io_mediator_method_annotations_are_provider_neutral() -> None:
    from milai.io.mediator import IOMediator
    from milai.io.types import Choice, RichContent

    hints = get_type_hints(IOMediator.show)
    assert hints["content"] is RichContent
    assert hints["return"] is type(None)

    hints = get_type_hints(IOMediator.choose)
    assert hints["choices"] == list[Choice]
    assert hints["return"] is Choice
