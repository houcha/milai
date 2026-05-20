import asyncio
from typing import cast

import pytest

import milai.main as main_module
from milai.io.mediator import IOMediator
from milai.llm.client import LLMClient


# tmp_path and capsys are built-in pytest fixtures:
# * tmp_path gives the test a unique temporary directory as a pathlib.Path
# * capsys captures writes to stdout/stderr during the test
def test_missing_config_path_exits_with_clear_error(tmp_path, capsys) -> None:
    missing = tmp_path / "missing.yaml"

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(main_module.run(["--config", str(missing)]))

    assert exc_info.value.code == 2
    assert f"config file does not exist: {missing}" in capsys.readouterr().err


def test_missing_default_config_uses_defaults(monkeypatch, tmp_path) -> None:
    class DummyMediator:
        pass

    class DummyStorage:
        def __init__(self, path) -> None:
            self.path = path

        async def load(self):
            return None

        async def save(self, state) -> None:
            self.state = state

        async def delete(self) -> None:
            pass

    class DummyStateMachine:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def run(self) -> None:
            pass

    monkeypatch.setattr(
        main_module, "DEFAULT_CONFIG_PATH", tmp_path / "missing-config.yaml"
    )
    monkeypatch.setattr(main_module, "TuiMediator", DummyMediator)
    monkeypatch.setattr(main_module, "LocalStorage", DummyStorage)
    monkeypatch.setattr(main_module, "StateMachine", DummyStateMachine)
    monkeypatch.setattr(
        main_module,
        "load_config",
        lambda path: pytest.fail(f"unexpected config load from {path}"),
    )

    asyncio.run(main_module.run([]))


def test_build_handler_map_registers_lesson_practice_state() -> None:
    from milai.config import Config
    from milai.state.handlers.lesson_practice import LessonPracticeHandler
    from milai.state.variants import LessonPracticeState

    class DummyMediator:
        pass

    class DummyClient:
        async def complete(self, *args, **kwargs):
            raise AssertionError("unexpected LLM call")

        async def chat(self, *args, **kwargs):
            raise AssertionError("unexpected LLM call")

    handlers = main_module.build_handler_map(
        config=Config(),
        mediator=cast(IOMediator, DummyMediator()),
        clients={"light": cast(LLMClient, DummyClient())},
    )

    assert isinstance(handlers[LessonPracticeState], LessonPracticeHandler)
